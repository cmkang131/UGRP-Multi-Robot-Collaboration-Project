"""Remote: summarize a finished batch into light JSON (no images): timings, hashes, file sha256 inventory."""
import json, hashlib, subprocess, statistics, sys
from pathlib import Path
base = Path.home()/'ugrp-sim/runs'
def raw(p):
    p = Path(p)
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-qdc', str(p)+'.zst'])
def sha(b): return hashlib.sha256(b).hexdigest()
out = {}
for bdir in sorted(base.glob(sys.argv[1] + '-*-batch')):
    start = json.loads((bdir/'START.json').read_text()); end = json.loads((bdir/'END.json').read_text())
    samples = [json.loads(l) for l in (bdir/'samples.jsonl').read_text().splitlines()]
    runs = {}
    for name in start['names']:
        root = base/name; r = root/'raw'
        m = json.loads((r.parent/'measurement.json').read_text())
        res = json.loads((r/'result.json').read_text())
        ht = json.loads((r/'host-timing.json').read_text())['timers']
        cam = json.loads((r/'camera-render.json').read_text())
        robots = {}
        for rid in ('r1', 'r2', 'r3'):
            rr = r/'robots'/rid
            frames = raw(rr/'frames.jsonl')
            imgs = []
            for line in frames.splitlines():
                row = json.loads(line); imgs.append(row['path'] + ':' + row['sha256'])
            robots[rid] = dict(commands_sha256=sha(raw(rr/'commands.jsonl')), frames_sha256=sha(frames),
                               ownmap_sha256=sha(raw(rr/'ownmap.jsonl')), image_list_sha256=sha('\n'.join(imgs).encode()), images=len(imgs))
        # steady-state slope wall vs sim from sampler (10..60 SIM s)
        pts = [(s['unix'], s['progress'][name].get('sim_s', s['progress'][name].get('t'))) for s in samples if name in s['progress']]
        pts = [(u, t) for u, t in pts if isinstance(t, (int, float)) and 10 <= t <= 60]
        slope = None
        if len(pts) >= 3:
            mu = statistics.fmean(p[0] for p in pts); mt = statistics.fmean(p[1] for p in pts)
            den = sum((t-mt)**2 for _, t in pts)
            slope = sum((u-mu)*(t-mt) for u, t in pts)/den if den else None
        llm = sum(res.get('response_wall_s') or [])
        files = {}
        for p in sorted(root.rglob('*')):
            if p.is_file(): files[str(p.relative_to(root))] = sha(p.read_bytes())
        (root/'ALL-hashes.json').write_text(json.dumps(files, indent=1) + '\n')
        runs[name] = dict(status=res.get('status'), failure=res.get('failure'), exit=json.loads((root/'EXIT').read_text()),
            sim_s=m['sim_s'], wall_s=m['wall_s'], cpu_s=m['cpu_s'], wall_per_sim=m['wall_per_sim'], cpu_per_sim=m['cpu_per_sim'],
            rbpf_hash_wall_s=m['rbpf_hash_wall_s'], llm_wait_s=llm, model_calls=res.get('model_calls'),
            wall_per_sim_minus_rbpf_llm=(m['wall_s']-m['rbpf_hash_wall_s']-llm)/m['sim_s'],
            steady_slope_wall_per_sim=slope, steady_points=len(pts),
            physics_advance_s=ht['physics_advance']['wall_s'], capture_s=ht['capture_including_render_io']['wall_s'],
            render_s=cam.get('render_wall_s'), rest_s=m['wall_s']-ht['physics_advance']['wall_s']-ht['capture_including_render_io']['wall_s'],
            rbpf_sha256=sha(raw(root/'rbpf-sha256.json')), robots=robots,
            all_hashes_sha256=sha((root/'ALL-hashes.json').read_bytes()), files=len(files),
            bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()))
    la = [s['loadavg'][0] for s in samples]; busy = [s['cpu_busy_frac'] for s in samples if s['cpu_busy_frac'] is not None]
    out[bdir.name] = dict(start=start, end=end, loadavg1_median=statistics.median(la), loadavg1_max=max(la),
                          cpu_busy_frac_median=statistics.median(busy), samples=len(samples), runs=runs)
print(json.dumps(out, indent=1))
