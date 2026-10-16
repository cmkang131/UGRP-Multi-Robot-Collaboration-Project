"""Standalone guest worker. Only launched after Mac coordinator approval checks.

No gcloud, model tokens, VM shutdown, restart policy, or cloud credentials here.
Container is loopback-only; systemd owns the whole process group. HTTP metrics
activity (not the presence of a resident vLLM process) drives the 20 min idle cap.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from urllib.request import urlopen


def counters(raw):
    values = {}
    for line in raw.splitlines():
        match = re.match(r'(vllm:(?:request_success_total|num_requests_running|num_requests_waiting))(?:\{[^}]*\})? ([0-9.eE+-]+)', line)
        if match:
            name, value = match.groups(); values[name] = values.get(name, 0) + float(value)
    return values


def command(cfg, candidate, model_root):
    model = cfg['models'][candidate]
    # 8192 token context is a pilot capacity, NOT silent prompt truncation. Corpus
    # must be measured by the model tokenizer before approval. 0.90 follows vLLM's
    # official recipe; eager avoids unmeasured CUDA-graph residency on the 24GB L4.
    return ['docker', 'run', '--rm', '--name', 'ugrp-llmhost', '--network=host',
            '--gpus', 'all', '--shm-size=4g', '-v', f'{model_root}:/model:ro',
            '-e', 'HF_HUB_OFFLINE=1', '-e', 'TRANSFORMERS_OFFLINE=1',
            '-e', 'HF_HUB_DISABLE_TELEMETRY=1', cfg['image'], '/model',
            '--served-model-name', model['served_model'], '--host', '127.0.0.1',
            '--port', '8000', '--quantization', 'compressed-tensors',
            '--load-format', 'safetensors', '--dtype', 'auto',
            '--max-model-len', '8192', '--gpu-memory-utilization', '0.90',
            '--enforce-eager', '--enable-prefix-caching',
            '--limit-mm-per-prompt', '{"image":1,"audio":0,"video":0}',
            '--reasoning-parser', 'gemma4',
            '--default-chat-template-kwargs', '{"enable_thinking":false}']


def verified_model(cfg, candidate):
    model = cfg['models'][candidate]
    root = Path(cfg['remote_root']) / 'models' / candidate / model['revision']
    import hashlib
    for item in model['files']:
        path = root / item['path']; h = hashlib.sha256()
        with path.open('rb') as f:
            while chunk := f.read(8 * 1024**2): h.update(chunk)
        if path.stat().st_size != item['bytes'] or h.hexdigest() != item['sha256']:
            raise ValueError('weight_hash_mismatch: ' + item['path'])
    return root


def main():
    p = argparse.ArgumentParser(); p.add_argument('config'); p.add_argument('candidate')
    a = p.parse_args(); cfg = json.loads(Path(a.config).read_text())
    root = Path(cfg['remote_root']); lease = root.parent / 'leases/llmhost.json'
    lease.parent.mkdir(parents=True, exist_ok=True)
    # This filesystem claim is exclusive among llmhost launchers. All other leases
    # are checked both before and after claim; the coordinator reserves the GPU.
    if list(lease.parent.glob('*.json')): raise ValueError('other_leases_present')
    began = time.time()
    with lease.open('x') as f:
        json.dump(dict(task='llmhost', pid=os.getpid(), started_unix=began,
                       expected_end_unix=began + cfg['runtime_seconds']), f)
    proc = None; reason = 'HOST_ERROR'
    def terminate(_signum, _frame):
        nonlocal reason
        reason = 'cap_end' if time.time()-began >= cfg['runtime_seconds'] else 'operator_stop'
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    try:
        if any(x != lease for x in lease.parent.glob('*.json')): raise ValueError('other_leases_present')
        gpu = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True)
        if gpu.strip(): raise ValueError('gpu_in_use')
        # Refuse credential-bearing environment even when someone launches the
        # standalone worker outside the Mac lifecycle command.
        if any(os.environ.get(k) for k in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN',
            'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'KAGGLE_KEY')):
            raise ValueError('credentials_not_allowed_on_VM')
        model_root = verified_model(cfg, a.candidate)
        proc = subprocess.Popen(command(cfg, a.candidate, model_root))
        last_activity, last_success, started = time.monotonic(), None, time.monotonic()
        while proc.poll() is None:
            now = time.monotonic()
            if now - started >= cfg['runtime_seconds']:
                reason = 'cap_end'; break
            try:
                with urlopen('http://127.0.0.1:8000/metrics', timeout=5) as response:
                    metrics = counters(response.read().decode())
                success = metrics.get('vllm:request_success_total', 0)
                active = sum(metrics.get(k, 0) for k in ('vllm:num_requests_running', 'vllm:num_requests_waiting'))
                if active or (last_success is not None and success != last_success): last_activity = now
                last_success = success
            except (OSError, ValueError): pass
            if now - last_activity >= cfg['idle_seconds']:
                reason = 'idle_20min'; break
            time.sleep(15)  # watchdog sampling only, never a simulation/action budget
        if proc.poll() is not None: reason = 'HOST_ERROR'
    finally:
        # Touch only our named container. No VM stop and no matching by process name.
        if proc is not None:
            subprocess.run(['docker', 'stop', '--time', '30', 'ugrp-llmhost'], check=False)
            proc.wait(timeout=60)
        (root / 'last-stop.json').write_text(json.dumps(dict(reason=reason, ended_unix=time.time())) + '\n')
        lease.unlink()


if __name__ == '__main__': main()
