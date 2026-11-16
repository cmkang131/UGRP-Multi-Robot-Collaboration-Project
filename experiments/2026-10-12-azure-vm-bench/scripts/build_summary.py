"""Mac: combine per-VM collected JSON into experiments summary.json."""
import json, statistics, sys, hashlib
from pathlib import Path
O = Path('/Users/changmin/projects/ugrp/outputs/azure-vm-bench-20261012')
vms = json.loads((O/'vms.json').read_text())
out = {}
for short, info in vms.items():
    p = O/f'collect-{short}.json'
    if not p.exists(): continue
    col = json.loads(p.read_text()); row = dict(info); price = info['usd_per_hour']
    for bname, b in col.items():
        mode = 'solo' if bname.endswith('solo-batch') else 'concurrent6'
        runs = b['runs']; ok = [r for r in runs.values() if r['status'] == 'EARLY_STOP' and r['failure'] == 'MEASUREMENT_SIM_LIMIT' and abs(r['sim_s']-60) < 1e-6]
        med = lambda k: statistics.median(r[k] for r in ok) if ok else None
        sim_total = sum(r['sim_s'] for r in ok)
        batch_wall = b['end']['wall_s']
        row[mode] = dict(N=len(runs), valid=len(ok), wall_per_sim_median=med('wall_per_sim'), cpu_per_sim_median=med('cpu_per_sim'),
            wall_per_sim_minus_rbpf_llm_median=med('wall_per_sim_minus_rbpf_llm'), steady_slope_median=med('steady_slope_wall_per_sim'),
            physics_s_median=med('physics_advance_s'), capture_s_median=med('capture_s'), render_s_median=med('render_s'), rest_s_median=med('rest_s'),
            rbpf_hash_s_median=med('rbpf_hash_wall_s'), llm_wait_s_median=med('llm_wait_s'),
            loadavg1_median=b['loadavg1_median'], loadavg1_max=b['loadavg1_max'], cpu_busy_frac_median=b['cpu_busy_frac_median'],
            batch_wall_s=batch_wall, sim_s_total=sim_total,
            sim_s_per_usd=(sim_total/(batch_wall/3600*price)) if batch_wall else None,
            runs={k: {kk: v[kk] for kk in v if kk != 'robots'} | {'robots': v['robots']} for k, v in runs.items()})
    out[short] = row
# trajectory comparison
def traj(r): return json.dumps({rid: r['robots'][rid]['commands_sha256'] for rid in ('r1','r2','r3')}, sort_keys=True)
def imgs(r): return json.dumps({rid: r['robots'][rid]['image_list_sha256'] for rid in ('r1','r2','r3')}, sort_keys=True)
cmp = {}
for short, row in out.items():
    allruns = [*row.get('solo', {}).get('runs', {}).values(), *row.get('concurrent6', {}).get('runs', {}).values()]
    cmp[short] = dict(distinct_command_sets=len({traj(r) for r in allruns}), distinct_image_sets=len({imgs(r) for r in allruns}),
                      distinct_rbpf=len({r['rbpf_sha256'] for r in allruns}), runs=len(allruns))
solos = {s: r['solo']['runs'][f'vmb-{s}-solo'] for s, r in out.items() if 'solo' in r}
cmp['cross_vm_solo'] = dict(commands_equal=len({traj(r) for r in solos.values()}) == 1, images_equal=len({imgs(r) for r in solos.values()}) == 1,
    rbpf_equal=len({r['rbpf_sha256'] for r in solos.values()}) == 1, vms=sorted(solos),
    commands=dict((s, traj(r)) for s, r in solos.items()))
allc = [r for row in out.values() for b in ('solo','concurrent6') for r in row.get(b, {}).get('runs', {}).values()]
cmp['all_runs'] = dict(N=len(allc), distinct_command_sets=len({traj(r) for r in allc}), distinct_image_sets=len({imgs(r) for r in allc}), distinct_rbpf=len({r['rbpf_sha256'] for r in allc}))
print(json.dumps(dict(vms=out, trajectory=cmp), indent=1))
