"""Resolve legacy frame clocks and preserve logged episode/leg/job boundaries."""
from pathlib import Path
import sqlite3,json,re,bisect,collections,time,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts.outputs_retention_rules import bracket_indices
ROOT=Path('/Users/changmin/projects/ugrp/outputs');TMP=Path('/private/tmp/outputs-retention-r2')
c=sqlite3.connect(TMP/'files.sqlite')
c.execute('CREATE TABLE IF NOT EXISTS boundaries(path TEXT PRIMARY KEY,source TEXT,reason TEXT)')
resolved=0;boundary_rows=0

def stamp(row):
 return next((float(row[k]) for k in ['t','sim_s','sim_time_s','observed_at_s','sim_time','timestamp_s'] if isinstance(row.get(k),(int,float))),None)

def resolve(rel,row):
 parent=Path(rel).parent
 if not isinstance(row.get('frame'),int) or stamp(row) is None:return None
 rid=row.get('robot_id') or next((s for s in reversed(parent.parts) if re.fullmatch(r'r[123]',s)),None)
 name=f'{row["frame"]:05d}.jpg'
 for par in [parent,*parent.parents]:
  for q in ([par/'frames'/rid/name] if rid else [])+[par/'frames'/name]:
   candidate=str(q)
   if c.execute('select 1 from files where path=?',(candidate,)).fetchone():return candidate
 return None

for rel, in c.execute("select path from files where path like '%/frames.jsonl' and mode & 61440=32768").fetchall():
 seq=[]
 try:
  for line in (ROOT/rel).open():
   if not line.strip():continue
   row=json.loads(line);p=resolve(rel,row)
   if p:
    t=stamp(row);c.execute('INSERT OR REPLACE INTO times VALUES(?,?,?,?)',(p,t,row.get('robot_id',''),rel));resolved+=1
    phase=(row.get('phase'),row.get('skill_phase'))
    seq.append((p,t,phase))
 except (ValueError,OSError):continue
 if seq:
  chosen={0,len(seq)-1}
  for i in range(1,len(seq)):
   if seq[i][2]!=seq[i-1][2]:chosen.update((i-1,i))
  for i in chosen:c.execute('INSERT OR IGNORE INTO boundaries VALUES(?,?,?)',(seq[i][0],rel,'first/last or recorded phase transition'))
  # OwnCamTeamHost's per-robot executor events carry exact job SIM boundaries.
  log=ROOT/Path(rel).parent.parent/'executor/events.jsonl'
  if log.exists():
   times=[x[1] for x in seq]
   for line in log.open():
    if not line.strip():continue
    row=json.loads(line);t=stamp(row)
    if t is None:continue
    i=bisect.bisect_left(times,t)
    for j in bracket_indices(times,t):
     c.execute('INSERT OR IGNORE INTO boundaries VALUES(?,?,?)',(seq[j][0],str(log.relative_to(ROOT)),'bracket recorded executor job/leg event'))
 c.commit()
# Pair-stage probes store a single episode/leg per directory, but integrated
# pair runs may also carry explicit leg/waypoint/phase transitions in records.
for rel, in c.execute("select path from files where path like '%/pair_records.json' and mode & 61440=32768").fetchall():
 parent=Path(rel).parent
 marks=[]
 def walk(value):
  if isinstance(value,list):
   for v in value:walk(v)
  elif isinstance(value,dict):
   t=stamp(value)
   event=' '.join(str(value.get(k,'')) for k in ['event','kind','type','reason'])
   if t is not None and re.search('leg|waypoint|phase|stage|job_started|job_done|job_failed',event,re.I):marks.append(t)
   for v in value.values():
    if isinstance(v,(dict,list)):walk(v)
 try:walk(json.loads((ROOT/rel).read_text()))
 except (OSError,ValueError):continue
 if not marks:continue
 for rid in ['r1','r2','r3']:
  prefix=str(parent/'frames'/rid)+'/'
  seq=c.execute('select path,t from times where path>=? and path<? order by t,path',(prefix,prefix+'\uffff')).fetchall()
  if not seq:continue
  ts=[x[1] for x in seq]
  for t in marks:
   i=bisect.bisect_left(ts,t)
   for j in bracket_indices(ts,t):
    c.execute('INSERT OR IGNORE INTO boundaries VALUES(?,?,?)',(seq[j][0],rel,'bracket recorded pair leg/waypoint/phase event'))
 c.commit()
result={'resolved_frame_rows':resolved,'protected_boundary_paths':c.execute('select count(*) from boundaries').fetchone()[0],'method':'Map frame index+robot+SIM timestamp to actual inventory path; retain first/last, adjacent phase changes and frames bracketing logged executor/pair leg/job events.'}
Path('experiments/2026-09-30-outputs-retention/boundary-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
