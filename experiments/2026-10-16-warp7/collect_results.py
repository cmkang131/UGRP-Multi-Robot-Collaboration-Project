"""Recount every warp7 submission on gcp2 CPU, including startup failures."""
import argparse,hashlib,json,platform
from pathlib import Path


def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert platform.node().startswith('ugrp-sim-gcp2')
    a.output.mkdir(parents=True,exist_ok=False);attempts=[]
    for name in ('n16-r1','n16-r1b','n16-r1c','n16-r1d','n16-r1e','n16-r2','n16-r3'):
        root=a.root/name;report=load(root/'summary.json');gate=load(root/'rejection-table.json');manifest=load(root/'SHA256SUMS.json');queue=load(root/'queue.json')
        bad=[n for n,h in manifest.items() if sha(root/n)!=h]
        progress=load(root/'progress.json') if (root/'progress.json').exists() else None
        analysis=a.root/(name+'-analysis')/'summary.json'
        groups=report.get('model_groups',[])
        parities=[]
        for f in root.glob('groups/*/camera-demand-parity.json'):
            x=load(f);parities.append(dict(path=str(f),sha256=sha(f),rows=x['rows']))
        attempts.append(dict(name=name,status=report['status'],source_sha=report['source_sha'],physics_host=report['host'],
            composition={c:dict(worlds=sum(r['condition']==c for r in queue['runs']),
                unique_initial_cases=len({r['seed'] for r in queue['runs'] if r['condition']==c and not r.get('replica')}),
                replicas=sum(r['condition']==c and bool(r.get('replica')) for r in queue['runs'])) for c in sorted({r['condition'] for r in queue['runs']})},
            raw=str(root),verified_files=len(manifest),hash_mismatches=bad,source_manifest_sha256=sha(root/'SHA256SUMS.json'),
            gate_stages=gate['stages'],rejections=[{k:e.get(k) for k in ('category','reason','blocked_object','minimum_gap_m','gap_status')} for e in report['errors']],
            progress=progress,model_group_N=len(groups),models=[dict(worlds=g['worlds'],model_batch=g.get('model_batch'),
                capacities=g['capacities'],native_model_adapter=g.get('native_model_adapter')) for g in groups],
            first30_completed=(root/'first30.json').exists(),mission_analysis=load(analysis) if analysis.exists() else None,
            camera_demand_parity=parities))
    write(a.output/'attempts.json',attempts)
    funnel=dict(unit='world within each named submission; exact queue composition recorded per attempt; do not pool attempts',
        attempts=[dict(name=r['name'],source_sha=r['source_sha'],composition=r['composition'],stages=r['gate_stages'],rejections=r['rejections'],raw=r['raw']) for r in attempts],
        first30=dict(requested=True,completed=0),place=dict(eligible=0,success=None),complete=dict(eligible=0,success=None),
        cap_end=0,xy_yaw_p95=None,input_audit='No carried/navigation interval reached; partial startup audits only.',
        reproduction=['python',__file__,'--root',str(a.root),'--output',str(a.output)])
    write(a.output/'rejection-table.json',funnel)
    summary=dict(status='NOT_READY',stop_reason='Repeated throughput symptom in n16-r1e/r2/r3; third round stopped before first30. R2 also has the independent cctv_top cache defect.',
        attempt_N=len(attempts),verified_files=sum(x['verified_files'] for x in attempts),hash_mismatches=sum(len(x['hash_mismatches']) for x in attempts),
        physics_backend='mjwarp_batch_v1',analysis_host=platform.node(),pool_with_cpu=False,
        elapsed_scope='progress.wall_s excludes setup; initial render overhead is included only in per-group timing; none are first30 measurements',
        throughput=[dict(name=x['name'],sim_s=x['progress']['sim_s'],wall_s=x['progress']['wall_s']) for x in attempts if x['progress']],
        LLM_model_calls=0,LLM_first30=None,rejection_table=str(a.output/'rejection-table.json'),raw=str(a.root),
        collector_sha256=sha(Path(__file__)))
    write(a.output/'summary.json',summary)
    write(a.output/'SHA256SUMS.json',{p.name:sha(p) for p in a.output.iterdir() if p.is_file()})
    print(json.dumps(summary))


if __name__=='__main__':main()
