"""Offline evaluation only: emitted RGB records; stance truth stays in evaluation."""
import json,subprocess,math,collections
from pathlib import Path

def read(path,lines=False):
 p=Path(path)
 if not p.exists():p=Path(str(p)+'.zst')
 if not p.exists():return [] if lines else {}
 data=subprocess.check_output(['zstd','-qdc',str(p)],text=True) if p.suffix=='.zst' else p.read_text()
 return [json.loads(x) for x in data.splitlines() if x] if lines else json.loads(data)

def losses(rows,cutoff,end,seen_before=True):
 """At least 2 s without code body/band evidence defines a loss episode."""
 last_seen=cutoff if seen_before else None;lost_at=None;first=None;episodes=[]
 for x in rows:
  t=x['t'];b=(x.get('own_beam_observation') or {}).get('result',{});visible=bool(b.get('visible') or b.get('band_visible'))
  if last_seen is not None and lost_at is None and t-last_seen>=2.:lost_at=last_seen
  if visible:
   if first is None:first=t-cutoff
   if lost_at is not None:episodes.append(dict(start_s=lost_at-cutoff,end_s=t-cutoff,duration_s=t-lost_at,reacquired=True));lost_at=None
   last_seen=t
 if lost_at is not None:episodes.append(dict(start_s=lost_at-cutoff,end_s=end,duration_s=max(0,cutoff+end-lost_at),reacquired=False))
 return dict(first_stage_seen_s=first,losses=len(episodes),reacquired=sum(e['reacquired'] for e in episodes),lost_sim_s=sum(e['duration_s'] for e in episodes),episodes=episodes)

def tracking(run,source):
 run=Path(run);raw=run/'raw';plan=read(run/'STAGE_PLAN.json');cp=read(Path(source)/plan['checkpoint']);result=read(raw/'result.json');events=read(raw/'transport-trace.json');end=result['sim_s'];out={}
 for rid in ['r1','r2']:
  rows=read(raw/f'robots/{rid}/ownmap.jsonl',True);ever=any(f['expected_beam_sha256']!='74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b' for f in cp['own_inputs'][rid]['frames'])
  v=losses(rows,cp['cutoff_s'],end,ever);gaze=[e for e in events if e.get('event')=='beam_tracking_gaze' and e.get('robot_id')==rid]
  v.update(own_body_observations=sum(bool((x.get('own_beam_observation') or {}).get('result',{}).get('visible')) for x in rows),grasp_observations=sum(bool(x.get('own_beam')) for x in rows),
      pan_record_N=len(gaze),pan_toward_memory_n=sum(e['reachable'] and e['error_deg']<=8 for e in gaze),pan_out_of_range_n=sum(not e['reachable'] for e in gaze),
      skill_choices=dict(collections.Counter(e['choice'] for e in events if e.get('event')=='beam_tracking_skill' and e['robot_id']==rid)),
      model_decisions=sum(e.get('event')=='beam_tracking_skill' and e['robot_id']==rid and e['source']=='judgment_model' for e in events),
      fallback_decisions=sum(e.get('event')=='beam_tracking_skill' and e['robot_id']==rid and e['source']=='fixed_fallback' for e in events),
      coverage_views=sum(e.get('event')=='beam_tracking_coverage' and e['robot_id']==rid for e in events))
  out[rid]=v
 return dict(name=run.name,analysis_set=plan['analysis_set'],condition=plan['condition'],scope='own detector evidence, not every-frame human labels; pan ratio is sampled commanded posture, not measured servo',robots=out,model_calls=result.get('model_calls'),model_receipts=[e['response'] for e in events if e.get('event')=='beam_tracking_model_receipt'])
