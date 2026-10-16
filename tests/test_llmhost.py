"""CPU-only serving/transfer guards; never imports CUDA or makes cloud calls."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from scripts import llmhost_benchmark as bench, llmhost_common as common
from scripts import llmhost_ctl as ctl, llmhost_guest as guest, llmhost_weights as weights
from scripts import self_gcp_upstream as upstream


def request():
    return dict(model='gemma-4-31b-it', max_tokens=800, reasoning_effort='none',
        messages=[dict(role='user', content=[dict(type='text', text='Choose act'),
          dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,' + base64.b64encode(b'own-rgb').decode()))])])


def test_disabled_and_pinned_launch():
    cfg = common.settings()
    assert cfg['enabled'] is False
    assert cfg['image'].startswith('vllm/vllm-openai@sha256:')
    for candidate in cfg['models']:
        args = guest.command(cfg, candidate, '/weights')
        assert '--enable-prefix-caching' in args
        assert args[args.index('--host')+1] == '127.0.0.1'
        assert args[args.index('--limit-mm-per-prompt')+1] == '{"image":1,"audio":0,"video":0}'
        assert all('TOKEN=' not in arg and 'restart' not in arg for arg in args)


@pytest.mark.parametrize('url', ['http://example.com/v1/chat/completions',
    'http://localhost:8000/v1/chat/completions', 'http://key@127.0.0.1:8000/v1/chat/completions'])
def test_reject_non_loopback(url):
    with pytest.raises(ValueError): common.loopback(url)


def test_wire_preserves_exact_image_and_messages():
    original = request(); before = copy.deepcopy(original)
    body = upstream.upstream_body(original, '26b_a4b_awq')
    assert body['messages'] == original['messages'] and original == before
    assert body['model'] == common.identity('26b_a4b_awq')['model']
    assert common.images(body) == [common.digest(b'own-rgb')]
    assert 'reasoning_effort' not in body
    body['messages'][0]['content'].pop()
    with pytest.raises(ValueError, match='exactly_one'): common.images(body)


def test_alerts_block_without_api_calls(tmp_path):
    common.write_json(tmp_path/'last-alerts.json', [{'kind': 'price_increase'}])
    with pytest.raises(ValueError, match='active_model'): common.check_alerts(tmp_path)
    (tmp_path/'last-alerts.json').unlink()
    common.write_json(tmp_path/'check-failures.json', {'consecutive':3})
    with pytest.raises(ValueError, match='failed_3'): common.check_alerts(tmp_path)


def test_approval_and_cloud_account_fence(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda args, **kw: calls.append(args))
    ctl.cloud('compute', 'instances', 'list')
    assert calls[0][-4:] == ['--account', 'changmin5781@gmail.com', '--project', 'ugrp-sim-b-1014']
    file = tmp_path/'approval.json'
    common.write_json(file, dict(task='llmhost', candidate='31b_awq', approved=True,
                                gpu_exclusive=True, budget_stop_clear=True, expires_unix=time.time()-1))
    with pytest.raises(ValueError, match='approval'): ctl.approval(file, '31b_awq')


def test_vm_wrong_project_shape_or_cap_rejected():
    vm = dict(name='ugrp-act-l4-gcp2', machineType='g2-standard-8',
              scheduling=dict(maxRunDuration=dict(seconds='28800'), instanceTerminationAction='STOP'))
    ctl.validate_vm(vm)
    vm['scheduling']['maxRunDuration']['seconds'] = '86400'
    with pytest.raises(ValueError, match='mismatch'): ctl.validate_vm(vm)


def test_truncated_generation_and_unknown_cache_are_not_success():
    ok = dict(choices=[dict(finish_reason='stop', message=dict(content='{"act":"wait"}'))])
    assert bench.judge(200, ok) == 'accepted'
    ok['choices'][0]['finish_reason'] = 'length'
    assert bench.judge(200, ok) == 'non_stop_finish'
    rows = [dict(status=200, wall_s=9, reason_category='non_stop_finish', image_sha256=['x'],
                 cached_tokens=None, prompt_tokens=100)]
    result = bench.summarize(rows, 60, 1.2, 600)
    assert result['success'] == 0 and result['over_8s'] == 1
    assert result['cache_ratio'] is None and result['cache_usage_coverage'] == 0
    assert result['benchmark_compute_usd'] == pytest.approx(.02)
    assert result['allocation_compute_usd'] == pytest.approx(.2)


def test_stream_hash_atomic_publication_and_cleanup(tmp_path):
    lease = tmp_path/'lease.json'; root = tmp_path/'model'
    receiver = weights.RECEIVER.replace('/home/ugrp/ugrp-sim/leases/llmhost-stage.json', str(lease))
    chunk = b'weights-without-credentials'; sha = common.digest(chunk)
    header = json.dumps(dict(path='model.safetensors', bytes=len(chunk), sha256=sha)).encode()+b'\n'
    framed = header + json.dumps(dict(n=len(chunk), sha256=sha)).encode()+b'\n' + chunk + b'{"n":0}\n'
    p = subprocess.run([sys.executable, '-c', receiver, str(root)], input=framed, capture_output=True)
    assert p.returncode == 0, p.stderr
    assert (root/'model.safetensors').read_bytes() == chunk and not lease.exists()
    # A resumed transfer verifies and preserves already complete files.
    p = subprocess.run([sys.executable, '-c', receiver, str(root)], input=framed, capture_output=True)
    assert p.returncode == 0 and (root/'model.safetensors').read_bytes() == chunk
    bad_root = tmp_path/'corrupt'
    p = subprocess.run([sys.executable, '-c', receiver, str(bad_root)],
                       input=framed.replace(chunk,b'x'*len(chunk)), capture_output=True)
    assert p.returncode != 0 and not (bad_root/'model.safetensors').exists() and not lease.exists()


def test_manifest_requires_40_matching_hashes(tmp_path):
    file = tmp_path/'request.json'; file.write_text(json.dumps(request()))
    manifest = tmp_path/'corpus.json'
    bench.prepare([file]*40, manifest, 'fixture-only')
    assert len(bench.load_corpus(manifest)[1]) == 40
    file.write_text('{}')
    with pytest.raises(ValueError, match='corpus_hash'): bench.load_corpus(manifest)


def test_relay_self_receipt_is_separate_and_tamper_rejected():
    from harness.s4_live_transport import validate_receipt
    source = common.ROOT/'scripts/self_gcp_upstream.py'
    receipt = dict(schema='ugrp.s4_ssh_proxy.v1', remote_url='http://127.0.0.1:18391/v1/chat/completions',
        proxy=dict(source_sha256=common.digest(source.read_bytes())), checked_unix=time.time(), valid_for_s=60,
        authentication='existing_mac_proxy_no_credentials_transferred', audit_per_post=True,
        driver_profile='study_gemma4_31b_v1', single_model=True, fallback_enabled=False,
        upstream='self_gcp_l4', dev_only=True,
        self_gcp_l4=dict(common.identity('31b_awq'), source_sha256=common.digest(source.read_bytes())))
    validate_receipt(receipt)
    receipt['self_gcp_l4']['revision'] = 'wrong'
    with pytest.raises(Exception, match='pinned self GCP'): validate_receipt(receipt)


def test_metrics_sum_labels():
    assert guest.counters('vllm:request_success_total{reason="stop"} 5\nvllm:request_success_total{reason="length"} 2\nvllm:num_requests_running 3\n') == {
        'vllm:request_success_total': 7, 'vllm:num_requests_running': 3}
    assert bench.prefix_counts('vllm:prefix_cache_hits_total{model_name="x"} 32\nvllm:prefix_cache_queries_total{model_name="x"} 64\n') == {
        'vllm:prefix_cache_hits_total':32, 'vllm:prefix_cache_queries_total':64}


def test_self_adapter_failure_is_not_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr(upstream, 'check_alerts', lambda: None)
    calls = []
    model = common.identity('31b_awq')['model']
    def send(body, endpoint):
        calls.append((body, endpoint))
        response = dict(model='wrong' if len(calls)==1 else model,
                        choices=[dict(finish_reason='stop', message=dict(content='{"act":"wait"}'))])
        return 200, json.dumps(response).encode(), None
    engine = upstream.SelfGCP(tmp_path, '31b_awq', send=send)
    raw = json.dumps(request()).encode()
    assert engine.complete(raw, 'same-call')[0] == 502
    assert engine.complete(raw, 'same-call')[0] == 200
    assert engine.complete(raw, 'same-call')[0] == 200 and len(calls) == 2
    assert all(url == common.settings()['endpoint'] for _, url in calls)


def test_no_coordinator_approval_no_cloud_operation(tmp_path, monkeypatch):
    def denied(*_args, **_kwargs): raise AssertionError('cloud must not run')
    monkeypatch.setattr(ctl, 'describe', denied)
    file = tmp_path/'approval.json'; common.write_json(file, {'approved':False})
    with pytest.raises(ValueError, match='approval'): ctl.start('31b_awq', file)


def test_all_40_mock_replies_failures_and_funnel_are_retained(tmp_path, monkeypatch):
    # Only the test clock's pacing is removed. No real server, GPU, or model call.
    monkeypatch.setattr(bench, 'check_alerts', lambda: None)
    monkeypatch.setattr(bench.time, 'sleep', lambda _: None)
    snapshots = iter(['vllm:prefix_cache_hits_total 0\nvllm:prefix_cache_queries_total 0',
                      'vllm:prefix_cache_hits_total 100\nvllm:prefix_cache_queries_total 200'])
    monkeypatch.setattr(bench, 'metrics_snapshot', lambda _: next(snapshots))
    paths = []
    for i in range(40):
        body = request(); body['messages'][0]['content'][0]['text'] = str(i)
        file = tmp_path/f'{i}.json'; file.write_text(json.dumps(body)); paths.append(file)
    manifest = tmp_path/'corpus.json'; bench.prepare(paths, manifest, 'fixture-only')
    def send(body, _endpoint):
        i = int(body['messages'][0]['content'][0]['text'])
        if i == 1: raise TimeoutError('fixture')
        return 200, json.dumps(dict(model=body['model'],
            choices=[dict(finish_reason='length' if i == 0 else 'stop', message=dict(content='{"act":"wait"}'))],
            usage=dict(prompt_tokens=100, completion_tokens=5, prompt_tokens_details=dict(cached_tokens=50)))).encode(), None
    out = tmp_path/'result'; result = bench.benchmark(manifest, out, '31b_awq', 1, 'fixture', send=send)
    s = result['summary']
    assert s['n'] == 40 and s['success'] == 38
    assert s['images_forwarded'] == 40 and s['image_http_acknowledged'] == 39
    assert s['cache_ratio'] == .5 and s['server_prefix_cache_ratio'] == .5
    assert len(list(out.glob('*-response.json'))) == 40
    assert [r['passed'] for r in json.loads((out/'funnel.json').read_text())['cumulative']] == [39, 39, 38]
    assert s['rejection_distribution'] == {'non_stop_finish':1, 'HOST_ERROR':1}
