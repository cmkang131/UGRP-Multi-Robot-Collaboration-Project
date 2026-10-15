"""GCP2-only terminal evidence. Never launches physics or modifies raw runs."""
import argparse,collections,hashlib,importlib.util,json,platform,subprocess
from pathlib import Path
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def lines(p):return (p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)).splitlines()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def failure_media(raw,out):
 p=raw/'failure-rgb/manifest.json'
 if not p.exists() and not Path(str(p)+'.zst').exists():return dict(available=False,reason='saved_buffer_missing')
 frames=obj(p)['frames']
 if not frames:return dict(available=False,reason='saved_buffer_empty')
 out.mkdir(parents=True,exist_ok=True);saved=[]
 for i in range(6):
  f=frames[round(i*(len(frames)-1)/5)];src=p.parent/f['path'];assert digest(src)==f['sha256']
  dst=out/f'failure-{i:02d}.jpg'
  if not dst.exists():dst.write_bytes(src.read_bytes())
  assert digest(dst)==f['sha256']
  saved.append(dict(t=f['t'],raw=str(src),path=str(dst),bytes=dst.stat().st_size,sha256=digest(dst)))
 montage=out/'failure-six.jpg'
 if not montage.exists():
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-framerate','1','-i',str(out/'failure-%02d.jpg'),'-vf','scale=320:240,tile=3x2:nb_frames=6','-frames:v','1',str(montage)],check=True)
 record=dict(available=True,frames=saved,montage=dict(path=str(montage),bytes=montage.stat().st_size,sha256=digest(montage)),
   source_manifest=str(p),scope='six user-requested saved terminal frames; full10Hz buffer retained on gcp2')
 (out/'failure-six-manifest.json').write_text(json.dumps(record,indent=2)+'\n');return record

def main(n,source,analyzer,build=False,media=False):
 assert platform.node().startswith('ugrp-sim-gcp2') and n in (1,2,3)
 b=RUNS/f'reloc19-round{n}';assert (b/'DONE').exists()
 if build:
  m=module('terminal_analysis',analyzer);m.ROOT=source;m.main(n,media=media)
 q=obj(b/'queue.json');summary=obj(b/'summary.json');by={x['name']:x for x in summary['runs']}
 verify=module('raw_integrity',source/'experiments/2026-10-16-reloc17/baseline_analyzer.py').verify
 review=module('media_review',source/'experiments/2026-10-16-reloc18/review.py')
 tables=[];integrity=[];brief=[]
 for t in q['runs']:
  raw=Path(t['raw']);r=by[t['name']];d=obj(raw/'result.json');a=r.get('destination_acquisition') or {}
  proof=verify(raw);assert proof['verified'],(t['name'],proof)
  integrity.append(dict(run=t['name'],raw=str(raw),source_sha=t['source_sha'],integrity=proof,input_audit=d.get('input_audit'),
    failure_media=failure_media(raw,b/'media'/t['name']) if media else None))
  if media and ((raw/'playback/manifest.json').exists() or (raw/'playback/manifest.json.zst').exists()):
   out=b/'media'/t['name']/'playback'
   if not out.exists():review.make(raw.parent,out)
  row=dict(run=t['name'],raw=str(raw),source_sha=t['source_sha'],valid=r.get('valid_for_comparison',False))
  if t['kind']=='carry':
   c=[json.loads(x) for x in lines(raw/'teacher-commands.jsonl')];seen={}
   zone=d['destination_zone'];phase=r.get('phases',{})
   stages=dict(started=1,lift_success=int(d.get('lift_success') is True),travel_entered=int(phase.get('carry_to_zone',0)>0),
      authored_arrival=int(r.get('gate_cumulative',{}).get('authored_arrival',0)),
      acquisition_entered=int(phase.get('destination_acquire',0)>0),detector_colour_acquired=int(a.get('acquired_t') is not None),
      rgb_footprint_confirmed=int(a.get('confirmed_t') is not None),place_view=int(phase.get('zone_place_view',0)>0),
      place_advance=int(phase.get('zone_place_advance',0)>0),lower=int(phase.get('lower',0)>0),
      open=int(phase.get('open',0)>0),evaluator_place_success=int(d.get('zone_placement_success') is True))
   for x in c:
    z=x.get('destination_acquisition',{}).get('last',{})
    if z.get('t') is None:continue
    z=dict(z);z.setdefault('category','visual_acquisition');z.setdefault('blocked_object','zone_'+zone)
    z.setdefault('minimum_gap_m',None);z.setdefault('gap_scope','not_applicable_visual_measurement; no physical blocker inferred')
    z['controller_pixel_sha256']=x.get('map_pose',{}).get('own_frame',{}).get('sha256');seen[z['t']]=z
   frames=list(seen.values());available=bool(frames) or not a.get('views')
   ff=dict(analysis_views=a.get('views',0),persisted_analysis_frame_N=len(frames),
      colour_component_or_direct_footprint=sum(x.get('pixels',0)>=600 or x.get('place_gate',False) for x in frames) if available else None,
      nominal_ground_or_direct_footprint=sum('patch_xy' in x or x.get('place_gate',False) for x in frames) if available else None,
      rgb_full_footprint=sum(bool(x.get('place_gate')) for x in frames) if available else None,
      missing_per_frame_telemetry=bool(a.get('views') and not frames))
   groups={}
   for x in frames:
    if x.get('place_gate'):continue
    key=(x['reason'],x['blocked_object']);v=groups.setdefault(key,dict(category='route' if x['minimum_gap_m'] is not None else x['category'],
      reason=x['reason'],blocked_object=x['blocked_object'],N=0,minimum_gap_m=None,gap_scope=x['gap_scope']))
    v['N']+=1
    if x['minimum_gap_m'] is not None:v['minimum_gap_m']=x['minimum_gap_m'] if v['minimum_gap_m'] is None else min(v['minimum_gap_m'],x['minimum_gap_m'])
   ledger=None
   if frames:
    data=json.dumps(dict(source=str(raw/'teacher-commands.jsonl'),scope='analysis-only metadata; no evaluator fed to controller',frames=frames),separators=(',',':')).encode()
    out=b/(t['name']+'-frame-ledger.json.zst')
    with out.open('wb') as f:subprocess.run(['zstd','-q','-19','-c'],input=data,stdout=f,check=True)
    decoded=subprocess.check_output(['zstd','-dc',str(out)]);assert decoded==data
    ledger=dict(path=str(out),sha256=digest(out),decoded_sha256=hashlib.sha256(data).hexdigest(),N=len(frames))
   row.update(unit='one reached event per run; independent frame family',cumulative=stages,frame_funnel=ff,
      frame_rejections=sorted(groups.values(),key=lambda x:-x['N']),frame_ledger=ledger,
      terminal_rejections=r.get('terminal_rejections',[]),recovery_reasons=r.get('gate_reasons',{}),
      detector_is_not_evaluator_success=True)
  else:
   row.update(unit='selfmap registration frame family',cumulative=r.get('registration_frame_funnel'),
      rejections=r.get('gate_reasons',{}),termination=r.get('termination'))
  tables.append(row)
  brief.append({**{k:r.get(k) for k in ('name','kind','condition','seed','status','termination','place_success','sim_s','errors','drive_errors','registered_errors','tracker','heading','input_audit','raw')},
    'source_sha':t['source_sha'],'destination_acquisition':{k:a.get(k) for k in ('mode','started_t','acquired_t','confirmed_t','acquisition_sim_s','relocalizations','destination_camera_pan_v1')},
    'event_funnel':row.get('cumulative'),'frame_funnel':row.get('frame_funnel')})
 tablepath=b/'rejection-table.json';initial=b/'rejection-table.initial.json'
 if not initial.exists():initial.write_bytes(tablepath.read_bytes())
 (b/'rejection-table.json').write_text(json.dumps(dict(source_queue=str(b/'queue.json'),initial_table=str(initial),initial_sha256=digest(initial),
   analysis_code_sha256=digest(Path(__file__)),reproduce=f'PYTHONPATH={source} python {__file__} --round {n} --source {source} --analyzer {analyzer}',
   missing_telemetry_scope='R1 total views/events known; absent per-frame gates remain null',runs=tables),indent=2)+'\n')
 (b/'final-integrity.json').write_text(json.dumps(dict(verified=True,runs=integrity,files=sum(x['integrity']['files'] for x in integrity)),indent=2)+'\n')
 (b/'brief.json').write_text(json.dumps(dict(round=n,status='NOT_READY' if any(r.get('place_success') is not True for r in brief if r['kind']=='carry') else 'PILOT_ONLY',
   source_sha=q['source_sha'],speed=obj(b/'speed-gate.json'),runs=brief,raw_files_verified=sum(x['integrity']['files'] for x in integrity),hash_mismatches=0),indent=2)+'\n')
 manifest={str(p.relative_to(b)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in b.rglob('*') if p.is_file() and p.name!='retrieval-manifest.json'}
 (b/'retrieval-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(dict(round=n,runs=len(brief),verified_files=sum(x['integrity']['files'] for x in integrity),place=sum(x.get('place_success') is True for x in brief),carry_N=sum(x['kind']=='carry' for x in brief))))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--analyzer',type=Path,required=True);p.add_argument('--build',action='store_true');p.add_argument('--media',action='store_true');a=p.parse_args();main(a.round,a.source,a.analyzer,a.build,a.media)
