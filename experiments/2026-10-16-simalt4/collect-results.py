"""Collect completed gcp2 evidence. Never step physics or mark a running job done."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt4')
OLD=ROOT.parent/'simalt3'
OUT=ROOT/'final-evidence'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--decision',choices=['PARITY_PASS','PARITY_FAIL','NEEDS_PHYSICS_PROFILE'],required=True)
    a=p.parse_args()
    sys.path.insert(0,str(ROOT/'scripts'))
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    OUT.mkdir(exist_ok=False)
    import importlib.metadata as md
    import mujoco,warp,mujoco_warp
    from mujoco_warp._src import io
    direct=json.loads(md.distribution('mujoco-warp').read_text('direct_url.json') or '{}')
    write(OUT/'environment.json',{'host':host,'python':sys.version,'mujoco':mujoco.__version__,
        'warp':warp.__version__,'mujoco_warp_package':md.version('mujoco-warp'),
        'mujoco_warp_commit':direct.get('vcs_info',{}).get('commit_id'),
        'upstream_io_sha256':sha(Path(io.__file__)),
        'credential_path_presence':{str(path):path.exists() for path in [Path.home()/'.config/gcloud/credentials.db',Path.home()/'.kaggle/kaggle.json',Path.home()/'.codex/auth.json',Path.home()/'.claude/.credentials.json']},
        'idle_timer':subprocess.check_output(['systemctl','is-active','ugrp-idle-guard.timer'],text=True).strip()})
    jobs=[]
    for f in sorted(ROOT.glob('*/result.json')):
        d=json.loads(f.read_text())
        if 'engine' not in d:continue
        if d['status']=='running':raise RuntimeError('running result: '+str(f))
        jobs.append({'name':f.parent.name,'status':d['status'],'engine':d['engine'],
          'case':d['case'],'mujoco':d['mujoco'],'sha':d['sha'],'script_sha256':d['script_sha256'],
          'steps_done':d['steps_done'],'sim_s':d['sim_s'],'wall_s':d['wall_s'],
          'error':d.get('error'),'capacities':d['capacities'],'backend_mode':d['backend_mode'],
          'recording_bytes':d['recording_bytes'],'own_RGB_ring':d.get('own_RGB_ring'),
          'raw_result':str(f),'raw_result_sha256':sha(f),'raw_steps':str(f.parent/'steps.npz'),
          'raw_steps_sha256':sha(f.parent/'steps.npz'),'physics_overrides':d['physics_overrides']})
    comparisons={}
    for group,candidate in [('r2','capacity-r2'),('r3','legacy-r3')]:
        for reference in ('c312','c316'):
            for case in ('forward','side','turn','grip'):
                run=ROOT/f'{candidate}-{case}'
                if not (run/'result.json').exists():continue
                info=json.loads((run/'result.json').read_text())
                if info['status']!='complete':continue
                target=ROOT/f'final-{group}-{reference}-{case}'
                cmd=[str(OLD/'warp-env/bin/python'),str(ROOT/'scripts/simalt_step_analysis.py'),
                  '--fixture',str(OLD/'fixture'),'--reference',str(ROOT/f'{reference}-{case}'),
                  '--candidate',str(run),'--out',str(target)]
                with (OUT/f'{target.name}.log').open('w') as log:
                    subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
                comparisons[target.name]=json.loads((target/'summary.json').read_text())
    for f in sorted(ROOT.glob('version*/summary.json')):
        comparisons[f.parent.name]=json.loads(f.read_text())
    for f in sorted(ROOT.glob('backend*/summary.json')):
        comparisons[f.parent.name]=json.loads(f.read_text())
    write(OUT/'comparisons.json',comparisons)
    write(OUT/'jobs.json',jobs)

    baseline=np.load(ROOT/'model-3.12.0.npz');model_audit={}
    for version in ('3.13.0','3.16.0'):
        candidate=np.load(ROOT/f'model-{version}.npz');rows=[]
        for key in baseline.files:
            if key not in candidate:continue
            av,bv=baseline[key],candidate[key]
            if not np.array_equal(av,bv):
                row={'field':key,'reference_shape':list(av.shape),'candidate_shape':list(bv.shape)}
                if av.shape==bv.shape:
                    ids=np.argwhere(av!=bv)
                    row.update(differing_entries=len(ids),max_abs_difference=float(np.abs(av-bv).max()),
                       entries=[{'index':i.tolist(),'C312':float(av[tuple(i)]),'candidate':float(bv[tuple(i)])} for i in ids[:30]])
                rows.append(row)
        ba=np.load(ROOT/'body-frame-meshes-3.12.0.npz');ca=np.load(ROOT/f'body-frame-meshes-{version}.npz')
        geometric=[]
        for name in ba.files:
            if name not in ca:continue
            x,y=ba[name],ca[name]
            def nearest(a,b):
                return max(float(np.sqrt(((a[start:start+256,None,:]-b[None,:,:])**2).sum(axis=-1)).min(axis=1).max())
                           for start in range(0,len(a),256))
            geometric.append({'geom':name,'body_frame_vertex_Hausdorff_m':max(nearest(x,y),nearest(y,x))})
        model_audit[version]={'compared_fields':len(set(baseline.files)&set(candidate.files)),
             'different_fields':rows,'mesh_geoms_compared':len(geometric),
             'mesh_max_vertex_Hausdorff_m':max(r['body_frame_vertex_Hausdorff_m'] for r in geometric),
             'mesh_largest_differences':sorted(geometric,key=lambda x:x['body_frame_vertex_Hausdorff_m'],reverse=True)[:20],
             'interpretation':'compiled size/quaternion differences are representation changes; raw vertex residual reported without a new acceptance constant'}
    write(OUT/'model-version-differences.json',model_audit)

    distributions=[]
    for j in jobs:
        if j['status']=='HOST_ERROR':
            if 'capacity overflow' in (j['error'] or ''):category='constraint_buffer_overflow'
            else:category='diagnostic_implementation_HOST_ERROR'
            distributions.append({'category':category,'count':1,'unit':'diagnostic invocation',
              'run':j['name'],'reason':j['error'],'blocking_object':'MJWarp constraint workspace' if category=='constraint_buffer_overflow' else j['name'],
              'minimum_gap_m':None,'minimum_gap_status':'not_geometric','raw_path':j['raw_result']})
    for name,c in comparisons.items():
        if name.startswith('final-') and '-c312-' in name and c.get('hold'):
            h=c['hold']
            if h['candidate_bilateral']<h['samples']:
                distributions.append({'category':'loaded_hold_bilateral_contact_absent',
                    'count':h['samples']-h['candidate_bilateral'],'unit':'10Hz samples, not independent episodes',
                    'comparison':name,'reason':'frozen tape did not retain both pad-box contacts',
                    'blocking_object':'cargo_cyan_2 / r1__left_finger / r1__right_finger',
                    'minimum_gap_m':float(np.load(Path(c['candidate'])/'steps.npz')['records'][:,5:7].min()),
                    'minimum_gap_status':'see per-step signed pad distance; not path-clearance rejection',
                    'raw_path':c['every_step_table']['path']})
    damping=[r for r in model_audit['3.16.0']['different_fields'] if r['field']=='actuator_biasprm']
    if damping:
        distributions.append({'category':'version_compiled_actuator_damping','count':damping[0]['differing_entries'],
          'unit':'actuator velocity bias entry','reason':'MuJoCo3.15 dampratio compiler change b3dd9e617; no gains modified in these experiments',
          'blocking_object':'r1 arm position actuators','minimum_gap_m':None,'minimum_gap_status':'not_geometric'})
    funnels=[]
    for group in ('warp-v2','capacity-r2','legacy-r3'):
        selected=[j for j in jobs if j['name'].startswith(group+'-')]
        complete=sum(j['status']=='complete' for j in selected)
        endpoints=[v for k,v in comparisons.items() if k.startswith('final-'+('r2' if group=='capacity-r2' else 'r3')+'-c312-')]
        row={'round':{'warp-v2':1,'capacity-r2':2,'legacy-r3':3}[group],
             'candidate':group,'command_cases_entered':len(selected),'command_cases_completed':complete,
             'command_cases_rejected':len(selected)-complete,'C312_endpoint_cases_passed':sum(v['endpoint_pass'] for v in endpoints),
             'hold_10Hz_samples':None,'source_paths':[j['raw_result'] for j in selected]}
        key='final-'+('r2' if group=='capacity-r2' else 'r3')+'-c312-grip'
        if group!='warp-v2' and key in comparisons:row['hold_10Hz_samples']=comparisons[key].get('hold')
        funnels.append(row)
    rejection={'decision':a.decision,'funnel':funnels,'distribution':distributions,
       'physical_identity_gate':{'reference':'C3.12 compiled model','passed':not bool(damping),
          'blocking_field':'actuator_biasprm[:,2]' if damping else None,
          'reason':'same XML is not the same compiled joint damping across these MuJoCo versions; no value overwritten',
          'new_profile_required_before_adoption':bool(damping)},
       'units_must_not_be_added':True,'raw_paths':[str(ROOT)],
       'expansion':{'pair_beam_3s':'not_submitted','N16_64_256_throughput':'not_submitted',
          'reason':'small-scene physical identity / loaded-hold parity has not passed'},
       'reproduction':'exact argv and input hashes in each result.json and every comparison summary'}
    write(OUT/'rejection_table.json',rejection)
    write(OUT/'summary.json',{'id':'2026-10-16-simalt4','status':'complete','decision':a.decision,
      'ready':False,'execution_host':host,'physics_overrides':{},'model_calls':0,'training':False,
      'Mac_physics_or_render':False,'GUI_apps_opened':False,'jobs':Counter(j['status'] for j in jobs),
      'rounds':funnels,'comparisons':list(comparisons),'model_audit':'model-version-differences.json',
      'originals_location':str(ROOT),'originals_backup':'L4 persistent disk only; not an external backup',
      'lifecycle':'L4 stop and cost verification must be added after retrieval',
      'rejection_table':str(OUT/'rejection_table.json')})
    tables=[{'comparison':k,**v['every_step_table']} for k,v in comparisons.items()]
    write(OUT/'step-tables.json',tables)

    # No active writer may remain in raw evidence. Package installation trees
    # and Python caches are environment, not experimental raw outputs.
    files=[x for x in ROOT.rglob('*') if x.is_file() and not x.is_relative_to(OUT)
           and not x.is_relative_to(ROOT/'mujoco313') and '__pycache__' not in x.parts
           and x.name not in ('collector.log','collector.pid')]
    manifest=[{'path':str(x),'bytes':x.stat().st_size,'sha256':sha(x)} for x in sorted(files)]
    failures=[row['path'] for row in manifest if sha(Path(row['path']))!=row['sha256']]
    write(OUT/'raw-verification.json',{'files':len(manifest),'passed':len(manifest)-len(failures),'failed':failures})
    (OUT/'SHA256SUMS').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in manifest))
    write(OUT/'raw-manifest.json',manifest)
    # Lossless compression policy for newly produced large JSON. Preserve the
    # original content hash and verify full restoration before removing it.
    compressed=[]
    for f in sorted(OUT.glob('*.json')):
        if f.stat().st_size<=65536:continue
        original_hash=sha(f)
        subprocess.run(['zstd','-q',str(f)],check=True)
        stored=Path(str(f)+'.zst')
        restored=subprocess.check_output(['zstd','-dc',str(stored)])
        if hashlib.sha256(restored).hexdigest()!=original_hash:raise RuntimeError('compression mismatch')
        compressed.append({'original':str(f),'stored':str(stored),'uncompressed_sha256':original_hash,'stored_sha256':sha(stored),'restored_hash_verified':True})
        f.unlink()
    write(OUT/'compression-map.json',compressed)
    print(json.dumps({'decision':a.decision,'jobs':len(jobs),'raw_files':len(manifest),'hash_failures':failures,'out':str(OUT)}))


if __name__=='__main__':main()
