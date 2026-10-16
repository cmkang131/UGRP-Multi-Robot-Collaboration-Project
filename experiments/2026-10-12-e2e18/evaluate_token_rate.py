"""Read-only provider/budget audit; no controller inputs or secret output."""
import argparse, hashlib, json, sqlite3, statistics, subprocess
from pathlib import Path


def read_json(path):
    data = path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path) + '.zst'], timeout=15)
    return json.loads(data), hashlib.sha256(data).hexdigest()


def inspect(run, cut=None):
    raw = run / 'raw'
    progress, progress_hash = read_json(raw / 'e2e-progress.json')
    current = float(progress['sim_s'])
    result_path = raw / 'result.json'
    if result_path.exists():
        result, _ = read_json(result_path)
        if result.get('finalization_complete'):
            current = max(current, float(result.get('sim_s', 0)))
    end = min(current, cut) if cut is not None else current
    with sqlite3.connect(f'file:{raw / "budget.sqlite"}?mode=ro', uri=True, timeout=3) as db:
        cohort = json.loads(db.execute('SELECT record FROM cohorts').fetchone()[0])
        records = [json.loads(x[0]) for x in db.execute('SELECT record FROM requests')]
    samples = []; missing = []; evidence = []
    for record in records:
        path = raw / 'wire' / Path(record['request_path']).name
        try:
            request, sha = read_json(path)
            msg = next(m for m in request['messages'] if m['role'] == 'user')['content']
            text = msg if isinstance(msg, str) else next(c['text'] for c in msg if c['type'] == 'text')
            start = float(json.loads(text)['sim_time_s'])
        except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
            missing.append(record['call_id']); continue
        if start > end: continue
        usage = record.get('provider_usage') or {}
        known = record.get('total_tokens')
        samples.append(dict(sim_s=start, total_tokens=known, charged_tokens=known if known is not None else cohort['unknown_usage_charge_tokens'], prompt_tokens=usage.get('prompt_tokens')))
        evidence.append(dict(call_id=record['call_id'], request_sha256=sha, response_sha256=record.get('response_sha256')))
    total = sum(s['charged_tokens'] for s in samples)
    duration = min(30., end)
    recent = [s for s in samples if max(0., end - 30.) < s['sim_s'] <= end or (end <= 30. and s['sim_s'] == 0)]
    rate = sum(s['charged_tokens'] for s in recent) / duration if duration else None
    cap = cohort.get('token_cap')
    eta = end + max(0., cap - total) / rate if cap is not None and rate else None
    prompts = [s['prompt_tokens'] for s in samples if s['prompt_tokens'] is not None]
    return dict(run=run.name, sim_s=end, calls=len(samples), recent_30_calls=len(recent), provider_prompt_tokens_median=statistics.median(prompts) if prompts else None, provider_prompt_tokens_max=max(prompts, default=None), known_tokens=sum(s['total_tokens'] or 0 for s in samples), unknown_usage_calls=sum(s['total_tokens'] is None for s in samples), charged_tokens=total, cumulative_tokens_per_sim_s=total/end if end else None, recent_30_tokens_per_sim_s=rate, token_cap=cap, cap_expected_sim_s_recent_30=eta, timing_basis='Settled/pending budget charges attributed to request start SIM; historical cuts are not exact ledger snapshots at that time', missing_request_time=missing, progress_sha256=progress_hash, request_response_hashes=evidence)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('runs', nargs='+', type=Path); parser.add_argument('--cut', type=float)
    args = parser.parse_args(); print(json.dumps([inspect(p, args.cut) for p in args.runs]))
