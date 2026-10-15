"""Collect only completed saved evidence; hash after every writer has exited."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

R=Path('/home/ugrp/ugrp-sim/runs/simalt5')
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/62563f51/scripts')
from simalt_host import gcp2_identity
host=gcp2_identity()


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while data:=stream.read(1024*1024):h.update(data)
    return h.hexdigest()


def write(name,value):
    (R/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


audit=json.loads(subprocess.check_output(['python3',str(R/'simalt_lease_audit.py'),'simalt5']))
assert not [p for p in audit['processes'] if p['owned'] and p['pid']!=os.getpid()], 'own writers still running'
write('writer-exit-audit.json',audit)
jobs=[]
rejected_comparator={'c316-legacy-damping312-grip','c316-legacy-damping316-grip',
                    'c316-geometry312-grip','c312-native-port-selfcontrol'}
for path in sorted(R.glob('*/result.json')):
    value=json.loads(path.read_text())
    assert value['status']!='running',str(path)
    assert value['steps_sha256']==sha(path.parent/'steps.npz'),str(path)+' step hash mismatch'
    jobs.append({'name':path.parent.name,'status':value['status'],'source_sha':value['sha'],
        'engine':value['engine'],'mujoco':value['mujoco'],'case':value['case'],
        'sim_s':value['sim_s'],'steps_done':value['steps_done'],
        'rejected_for_version_attribution':path.parent.name in rejected_comparator,
        'reason':'C port arithmetic failed same-version fidelity' if path.parent.name in rejected_comparator else 'recorded diagnostic',
        'raw':str(path.parent),'result_sha256':sha(path),'steps_sha256':value['steps_sha256'],
        'xml_sha256':value['xml_sha256'],'fixture_sha256':value['fixture_sha256']})
assert len(jobs)==16,(len(jobs),'expected16 physical diagnostic calls')
write('physics-jobs.json',jobs)
round1=json.loads((R/'round1-summary.json').read_text())
round3=json.loads((R/'round3-summary.json').read_text())
final=[x for x in round3 if x['name'].startswith('geometry312-')]
grip=next(x for x in final if x['case']=='grip')
assert len(final)==4 and not grip['endpoint_pass'],'do not skip beam if small scene passes'
decomposition=json.loads((R/'version-decomposition-corrected.json').read_text())
reject={'rounds':3,'distribution':[
    {'reason':'base_endpoint_over_5mm','count':1,'blocking_object':'r1__robot / floor',
     'minimum_gap_m':None,'minimum_gap_status':'not_geometric_trajectory_gate','observed_m':grip['base_endpoint_m']},
    {'reason':'unloaded_endpoint_pass','count':3,'blocking_object':'none','minimum_gap_m':None,
     'minimum_gap_status':'trajectory_gate'},
    {'reason':'native_comparator_arithmetic_rejected','count':4,'blocking_object':'Plane–Mesh transform arithmetic',
     'minimum_gap_m':None,'minimum_gap_status':'not_geometric; original math order restored in corrected controls'}],
    'funnel_tapes':[{'gate':'final tapes complete','entered':4,'passed':4,'rejected':0},
      {'gate':'overflow-free','entered':4,'passed':4,'rejected':0},
      {'gate':'endpoint5mm_2deg','entered':4,'passed':3,'rejected':1}],
    'funnel_hold_time_samples':[{'gate':'hold samples','entered':30,'passed':30,'rejected':0},
      {'gate':'bilateral','entered':30,'passed':30,'rejected':0},
      {'gate':'height difference<=2mm','entered':30,'passed':30,'rejected':0}],
    'funnel_profiles':[{'gate':'small scene all requirements','entered':1,'passed':0,'rejected':1},
      {'gate':'beam3s','entered':0,'passed':0,'rejected':0},
      {'gate':'throughput N16/64/256','entered':0,'passed':0,'rejected':0}],
    'threshold_basis':'user2026-10-16 proposal; no relaxation; hold30 is time samples not independent trials',
    'raw':str(R/'warp-geometry312-grip/steps.npz'),
    'reproduce':str(R/'round3-plan.json')}
write('rejection_table.json',reject)
tables=[]
for path in sorted(R.glob('*/summary.json')):
    value=json.loads(path.read_text())
    if 'every_step_table' in value:tables.append({'comparison':path.parent.name,**value['every_step_table']})
write('step-tables.json',tables)
write('collected-summary.json',{'id':'2026-10-16-simalt5','decision':'PARITY_FAIL','ready':False,
    'status':'completed_bounded_diagnostic','host':host,'rounds':3,
    'physics_jobs':{'complete':sum(x['status']=='complete' for x in jobs),
                    'HOST_ERROR':sum(x['status']=='HOST_ERROR' for x in jobs),
                    'cap_end':sum(x['status']=='cap_end' for x in jobs)},
    'jobs_index':'physics-jobs.json','final_cases':final,'round1':round1,
    'decomposition':decomposition,'model_audit':'full-model-differences-C316-compiled312.json',
    'rejected_native_comparator_runs':sorted(rejected_comparator),
    'beam':{'status':'not_submitted','reason':'small scene endpoint gate failed','attempted':0},
    'throughput':{'status':'not_submitted','N':[16,64,256],'physics':None,'RGB':None,
                  'SIM_s_per_USD_vs_n4':None,'reason':'small scene endpoint gate failed'},
    'model_calls':0,'training':False,'Mac_physics_or_render':False,'GUI_apps_opened':False,
    'new_physical_parameters':False,'operating_backend_changed':False,
    'default_off_toggles':['legacy-plane-v1','dense-capacity-v1','compiled-312-v1','compiled-geometry-312-v1'],
    'nonphysics_rejections':[{'reason':'native analysis read running Warp; rejected incomplete input','log':str(R/'native-controls.log')},
        {'reason':'direct C312 MJWarp API lacks mjINT_DISCRETE','record':str(R/'direct312-import.json')},
        {'reason':'initial filtered-reference source materialization and network reference clone failures',
         'logs':['source-materialize.log','clone-510.log']}],
    'rejection_table':str(R/'rejection_table.json'),'raw_root':str(R),
    'originals_backup':'L4 persistent disk only; no external full backup'})
# All outputs above are now stable. The collector's own log and manifests are
# excluded to avoid the self-log race found in simalt4.
excluded={'collect-final.log','SHA256SUMS-final','raw-verification-final.json'}
paths=sorted(p for p in R.rglob('*') if p.is_file() and p.name not in excluded)
manifest=[(str(p.relative_to(R)),sha(p),p.stat().st_size) for p in paths]
(R/'SHA256SUMS-final').write_text(''.join(h+'  '+name+'\n' for name,h,size in manifest))
bad=[name for name,h,size in manifest if sha(R/name)!=h or (R/name).stat().st_size!=size]
write('raw-verification-final.json',{'status':'PASS' if not bad else 'FAIL','files':len(manifest),
    'bytes':sum(size for name,h,size in manifest),'mismatches':bad,'all_writers_exited_before_hash':True,
    'manifest_sha256':sha(R/'SHA256SUMS-final'),'excluded':sorted(excluded)})
assert not bad,bad
print(json.dumps({'files':len(manifest),'bytes':sum(x[2] for x in manifest),'SHA':'PASS','physics_calls':len(jobs)}))
