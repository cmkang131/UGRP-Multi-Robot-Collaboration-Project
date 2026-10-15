"""Saved gate populations, kept separate: episodes, native frames, line proposals, lift events."""
from pathlib import Path
import collections,hashlib,json,subprocess,sys
from PIL import Image
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5'
def read(p):
 if not p.exists():p=Path(str(p)+'.zst')
 if not p.exists():return None
 return json.loads(subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes())
def funnel(items,steps):
 kept=list(items);rows=[]
 for gate,pred in steps:
  N=len(kept);kept=[r for r in kept if pred(r)];rows.append(dict(gate=gate,entered=N,cumulative_passed=len(kept),rejected=N-len(kept)))
 return dict(N=len(items),ordered_funnel=rows)
def build(config,out):
 cfg=read(config);pop={};sources=[];errors=[]
 for r in cfg['runs']:
  raw=R/'runs'/r['name']/'raw';d=read(raw/'result.json')
  if not d:continue
  manifest=read(raw/'manifest.json') or {};frames=[]
  for name,spec in manifest.items():
   if not name.startswith(('eval-lookaround-input/','eval-regrasp-input/')) or not name.endswith('.jpg'):continue
   p=raw/name;verified=p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==spec['sha256'];size=Image.open(p).size if verified else None
   frames.append(dict(path=name,sha_ok=verified,native640x480=size==(640,480)))
   if not verified:errors.append(str(p))
  images=[e for c in d.get('line_rechecks',[]) for e in c['events'] if e['event']=='image']
  attempts={}
  for check in d.get('regrasp_verification',[]):
   for e in check['events']:
    if e['event'] not in ('test_start','confirmed'):continue
    key=(e['epoch'],e['robot'],e['attempt']);row=attempts.setdefault(key,dict(started=False,confirmed=False,no_epoch_failure=check['failure'] is None));row['started']|=e['event']=='test_start';row['confirmed']|=e['event']=='confirmed'
  views=[e for v in (d.get('lookaround_result') or {}).values() for e in v['localizer'].get('views',[])]
  pop[r['name']]=dict(raw=str(raw),cohort=r['candidate'],native_input_frames=funnel(frames,[('original_sha_verified',lambda x:x['sha_ok']),('source_LOOK_RES_640x480',lambda x:x['native640x480'])]),line_image_proposals=funnel(images,[('logged_valid',lambda x:x.get('valid') is True),('logged_unclipped',lambda x:x.get('unclipped') is True),('logged_fov_safe',lambda x:x.get('fov_safe') is True)]),line_reason_distribution=dict(collections.Counter(e.get('reason') or 'source_missing_reason' for e in images)),localization_views=funnel(views,[('source_status_measured',lambda x:x.get('status')=='measured')]),lift_attempt_events=funnel(list(attempts.values()),[('test_start_logged',lambda x:x['started']),('own_rgb_confirmed',lambda x:x['confirmed']),('epoch_no_failure',lambda x:x['no_epoch_failure'])]))
  p=raw/'result.json';actual=p if p.exists() else Path(str(p)+'.zst');sources.append(dict(path=str(actual),sha256=hashlib.sha256(actual.read_bytes()).hexdigest()))
 value=dict(schema='ugrp.gatesv5.release.populations.v1',source_sha=cfg['source_sha'],stage=cfg['stage'],populations_by_run=pop,hash_errors=errors,raw_sources=sources,scope='Native file events, line-image proposals, localization views and own-RGB lift attempts are different populations and never pooled; stages use existing logged booleans/status, no new threshold.',reproduce=str(Path(__file__).resolve())+' '+str(config)+' '+str(out))
 out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(out=str(out),runs=len(pop),native_input_frames=sum(v['native_input_frames']['N'] for v in pop.values()),line_proposals=sum(v['line_image_proposals']['N'] for v in pop.values()),lift_attempts=sum(v['lift_attempt_events']['N'] for v in pop.values()),hash_errors=len(errors))))
if __name__=='__main__':build(Path(sys.argv[1]),Path(sys.argv[2]))
