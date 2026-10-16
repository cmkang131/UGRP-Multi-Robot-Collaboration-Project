"""World-isolated E2E scheduling and asynchronous Mac-relay decision boundary.

The source checkout is pinned separately: no unrelated planner source is copied
into relocation. Live requests remain blocked without an explicit clear Mac
endpoint receipt. rule_v1 executes the existing strong rule in-process, no wire.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import copy,hashlib,json,threading
from pathlib import Path
from urllib.parse import urlparse
from scripts.warp5_episode import Lane,Bridge,prepare_modules
from scripts.warp5_batch import transform_runner


class AsyncDecisions:
    """Caller polls world+robot futures; no other world's physics waits on I/O."""
    def __init__(self,call,*,mac_receipt=None,workers=3):
        self.call=call;self.receipt=mac_receipt;self.pool=ThreadPoolExecutor(max_workers=workers)
        self.pending={};self.epochs={};self.lock=threading.Lock()
    def submit(self,world,robot,request,*,live=False):
        key=(world,robot)
        if live:
            r=self.receipt or {};url=urlparse(r.get('relay_url',''))
            if r.get('endpoint_alert_status')!='clear' or r.get('user_price_decision')!='approved' or url.hostname not in ('127.0.0.1','localhost'):
                raise ValueError('active/unresolved endpoint alert; live LLM batch forbidden')
        with self.lock:
            if key in self.pending:raise ValueError('one pending decision per world/robot')
            epoch=self.epochs.get(world,0)
            self.pending[key]=(epoch,self.pool.submit(self.call,copy.deepcopy(request)))
    def poll(self,world,robot):
        key=(world,robot)
        with self.lock:
            entry=self.pending.get(key)
            if entry is None or not entry[1].done():return None
            del self.pending[key]
        epoch,future=entry
        if epoch!=self.epochs.get(world,0):return None
        return future.result()
    def reset_world(self,world):
        with self.lock:
            self.epochs[world]=self.epochs.get(world,0)+1
            for key in [k for k in self.pending if k[0]==world]:self.pending.pop(key)[1].cancel()
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)


class LocalRuleClient:
    """Existing task-planner rule contract; no fabricated provider receipt."""
    timeout=30.;max_tokens=768;require_json_reply='task_planner_v1'
    last_text=None;last_usage=None;last_completion=None;last_provider_metadata=None
    def complete(self,messages,*,images):
        from harness.e2e_task_planner import rule
        from harness.llm_completion import COMPLETION_POLICY
        context=json.loads(messages[-1]['content'])
        self.last_text=json.dumps(rule(context))
        self.last_usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0,cost=0.)
        self.last_provider_metadata=dict(backend='rule_v1',provider_calls=0)
        self.last_completion=dict(policy=COMPLETION_POLICY,normal_completion=True,finish_reason='stop',
            rejection_reasons=[],upstream_finish_verified=False,source='local_strong_rule',provider_calls=0)
        return self.last_text


def make_e2e(source,bundle,out,receipt,host,*,expected_sha,decision_backend='rule_v1',body_receipt=None):
    import subprocess
    source=Path(source)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    if sha!=expected_sha or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source):raise ValueError('clean pinned E2E dependency required')
    if decision_backend!='rule_v1':
        raise ValueError('live E2E transport/ACT/relay integration is unverified; CoreWeave price alert is resolved, not the integration gate')
    if bundle['e2e_options'].get('planner')!='rule_v1':raise ValueError('rule-only bundle required')
    bridge=Bridge(host)
    def factory():
        prepare_modules(host)
        from scripts import run_e2e_ownmap_live as runner
        from harness import zone_study_llm_driver as driver
        def clients(profile,**kw):
            def make(_http_open):return LocalRuleClient()
            make.settings=dict(profile.get('model',{}),model='ugrp/strong-task-rule-v1')
            return make
        driver.client_factory=clients
        function,audit=transform_runner(Path(runner.__file__).read_text(),runner.__dict__,bridge,'e2e')
        bridge.ast_audit=dict(audit,dependency_sha=sha,decision_backend=decision_backend,
            model_calls=0,Mac_relay='preserved in pinned source; live execution blocked')
        return function(bundle,Path(out),Path(receipt),body_receipt=body_receipt)
    return Lane(factory,source),bridge
