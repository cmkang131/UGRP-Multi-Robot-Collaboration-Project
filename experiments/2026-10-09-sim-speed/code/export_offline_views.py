from pathlib import Path
import hashlib, json, subprocess

ROOT=Path('/Users/changmin/projects/ugrp/outputs/simspeed-20261009')
VIEWS=ROOT/'tensorboard-offline-views'
VIEWS.mkdir(exist_ok=True)
def read(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(name, source, sha, scope, values, passed=None):
    d=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
        offline_source=dict(path=str(source),sha256=digest(source)),offline_scalar_scope=scope,
        family='simspeed',policy='offline_diagnostic',condition=name,case='no_physics',seed=49001,
        source_sha=sha,run_id=name,outcome='diagnostic',model_calls=0,
        offline_scalars=values,hparam_metrics=list(values)[:3])
    if passed is not None:
        d.update(success=passed,success_definition=scope+'; not robot mission success')
    p=VIEWS/name;p.mkdir(exist_ok=True);(p/'result.json').write_text(json.dumps(d,indent=2)+'\n')
for name,folder,sha in [
    ('saved-egomap49','saved-egomap49-profile','fc5164806c5216e08e7cbeddc27e9a87d377470c'),
    ('saved-teach-mismatch','saved-profile','7b1d1e4c1f9032adc695b63557fa5ae57d1e81a4'),
    ('relay-profile','relay-profile','fc5164806c5216e08e7cbeddc27e9a87d377470c')]:
    src=ROOT/folder/'profile.json';r=read(src)
    vals={'offline/physics_steps':0}
    if 'profile_total_s' in r:vals['offline/profile_self_s']=r['profile_total_s']
    if 'calls' in r:vals['offline/relay_calls']=r['calls']
    for i,f in enumerate(r['top10'][:3],1):vals[f'offline/hotspot_{i}_percent']=f['percent']
    if 'frames' in r:vals.update({'offline/rows':r['frames'],'offline/matched_rows':r['identical_traces']})
    emit(name,src,sha,'cProfile diagnostic during other research; no wall/SIM timing comparison; '+r['scope'],vals)
src=ROOT/'saved-egomap49-profile/raw-byte-verification.json'
emit('raw-byte-check',src,'fc5164806c5216e08e7cbeddc27e9a87d377470c',
     '51 saved-input controller rows; original bytes equal; no physics',
     {'gate/bytes_identical':1,'offline/rows':51,'offline/bytes':183606},True)
for name,folder,scope in [
    ('source-guard','managed-run','Abbreviated SHA rejected before simulation'),
    ('queued-cancelled','managed-abba','Own waiting driver stopped to update native dependency guard; no physics'),
    ('setup-error','managed-abba-final','Sparse texture missing before model construction; originals restored after failure')]:
    src=ROOT/folder/'manifest.json';r=read(src)
    emit(name,src,r['source']['source_sha'],scope,{'offline/physics_steps':0},False)
cmd=['/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python','scripts/export_offline_audit.py']
for p in sorted(VIEWS.iterdir()):cmd+=['--source',str(p)]
cmd+=['--output','/Users/changmin/projects/ugrp/outputs/tensorboard/1009-simspeed-offline']
subprocess.run(cmd,check=True)
