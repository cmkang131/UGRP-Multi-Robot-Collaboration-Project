"""Independent warm artifact audit. Run on gcp2 only; no physics or renderer."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve()
    if not str(root).startswith('/home/ugrp/ugrp-sim/runs/'):
        p.error('remote original artifacts only; no Mac physics/artifact analysis')
    if a.out.exists():p.error('new output only')
    raw=json.loads((root/'summary.json').read_text())
    if raw['status']!='complete' or [r['nworld'] for r in raw['cases']]!=[64,256]:
        raise ValueError('both N64/N256 qualified cases required')
    rows=[];hosts=[]
    for r in raw['cases']:
        folder=Path(r['raw']).resolve();n=r['nworld']
        if folder.parent!=root:raise ValueError('case escaped original root')
        full=json.loads((folder/'summary.json').read_text())
        if sha(folder/'summary.json')!=r['summary_sha256']:raise ValueError('summary SHA changed')
        inventory={str(x.relative_to(folder)) for x in folder.rglob('*') if x.is_file() and x!=folder/'summary.json'}
        if inventory!=set(full['raw_sha256']):raise ValueError('raw manifest inventory mismatch')
        mismatches=[rel for rel,s in full['raw_sha256'].items() if sha(folder/rel)!=s]
        if mismatches:raise ValueError('raw file SHA mismatch: '+repr(mismatches))
        if not r['qualified_unshared'] or r['foreign_gpu_pids'] or r['foreign_compute'] or r['compiled_during_timing']:
            raise ValueError('shared or compiling measurement')
        for sample in r['foreign_samples']:
            if sample['foreign'] or sample['foreign_compute']:raise ValueError('nonempty foreign load sample')
        if not r['foreign_samples']:raise ValueError('no foreign load observation samples')
        logpath=root/(folder.name+'.log');log=logpath.read_text()
        if log.count('WARM_MEASURE_BEGIN')!=1 or log.count('WARM_MEASURE_END')!=1:raise ValueError('missing timing markers')
        middle=log.split('WARM_MEASURE_BEGIN',1)[1].split('WARM_MEASURE_END',1)[0]
        if '(compiled)' in middle:raise ValueError('JIT compilation inside timed window')
        if full['status']!='complete' or full['HOST_ERROR']!=0 or full['cap_end']!=n:raise ValueError('incomplete bounded load')
        if len(full['world_results'])!=n or full['independent_gate_episodes']!=0 or not full['replicas_are_load']:
            raise ValueError('replica population mismatch')
        if full['controller_source']!='f0db6b1abb842ea65b71c433738210254f300a7c':raise ValueError('controller changed')
        if full['teacher_source']!='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8':raise ValueError('teacher changed')
        if full['seed']!=8317104 or full['scenario']!='s1_normal_mixed_v4':raise ValueError('different scenario')
        if full['warmup_sim_s']!=3. or full['timed_sim_range']!=[3.,6.] or len(full['interval_wall_s'])!=30:
            raise ValueError('different warm/timing protocol')
        if full['camera_native']!='640x480/10Hz original K,D/FOV/mount' or full['training_rgb'] or full['weld']!='off':
            raise ValueError('camera or weld condition changed')
        phases=collections.Counter()
        for w in full['world_results']:
            if w['status']!='cap_end' or not w['cap_end']:raise ValueError('replica did not reach6SIM cap')
            audit=w['input_audit']
            if audit['invisible_measurements'] or audit['held_world_reads']:raise ValueError('input boundary violation')
            phases.update(audit['measurements_by_phase'])
        rate=n*3./full['timed_wall_s']
        if rate!=r['sim_s_per_wall_s'] or rate!=full['sim_s_per_wall_s']:raise ValueError('rate arithmetic mismatch')
        hosts.append(r['host'])
        rows.append(dict(nworld=n,host=r['host'],mujoco=full['mujoco'],source=full['source_sha'],
            raw=str(folder),summary_sha256=sha(folder/'summary.json'),log_sha256=sha(logpath),
            raw_files=len(inventory),hash_mismatch=0,load_samples=len(r['foreign_samples']),
            foreign_load_samples=0,new_JIT_during_timing=False,timed_SIM=n*3.,timed_wall_s=full['timed_wall_s'],
            SIM_s_per_wall_s=rate,SIM_s_per_USD_published_on_demand=rate*3600/1.096224308,
            first10_median=statistics.median(full['interval_wall_s'][:10]),
            last10_median=statistics.median(full['interval_wall_s'][-10:]),interval_p90_recorded=full['interval_p90'],
            timed_components=full['timed_components'],phase_measurements=dict(phases),cap_end=n,HOST_ERROR=0,
            invisible_measurements=0,held_world_reads=0,independent_teacher_N=0))
    if hosts[0]!=hosts[1]:raise ValueError('N64/N256 hosts differ')
    result=dict(passed=True,scope='bounded warm SIM3..6 approach prefix, not full mission or training throughput',
        root=str(root),summary_sha256=sha(root/'summary.json'),boot_id=raw['boot_id'],cases=rows,
        price_basis='Seoul published on-demand compute1.096224308USD/h; not actual bill or credit balance',
        reproduce=['python3',str(Path(__file__).resolve()),'--root',str(root),'--out','NEW_OUTPUT.json'])
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
