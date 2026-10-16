"""Explicit opt-in dispatch inside the existing Mac Gemma relay; no key access."""
import json
from harness.task_planner import clean


def task_request(request):
    from harness.e2e_dialogue_decider import unpack
    try:value,_=unpack(request)
    except (ValueError,KeyError,TypeError,IndexError):return None
    if value.get('schema')!='ugrp.task_planner.v1':return None
    clean(value)
    if value.get('planner_backend') not in ('gemma_v1','rule_v1'):raise ValueError('REGISTERED_TASK_PLANNER_BACKEND_REQUIRED')
    return value


def rule_response(context):
    from harness.e2e_task_planner import rule
    return dict(model='ugrp/strong-task-rule-v1',provider='local-code',
        choices=[dict(index=0,finish_reason='stop',message=dict(role='assistant',content=json.dumps(rule(context))))],
        usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0,cost=0.),
        ugrp_task_planner=dict(backend='rule_v1',provider_calls=0))


SOURCE_FILES=('harness/e2e_task_planner.py','harness/e2e_task_planner_relay.py',
    'harness/e2e_task_planner_wire.py','harness/e2e_task_planner_routes.py',
    'harness/task_planner.py','harness/task_planner_evidence.py','harness/task_planner_cost_rules.py')

def source_hashes(root):
    import hashlib
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCE_FILES}
