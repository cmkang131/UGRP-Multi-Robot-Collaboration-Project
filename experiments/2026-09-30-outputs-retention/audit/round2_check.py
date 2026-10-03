from pathlib import Path
import sqlite3,json,csv,time,sys,hashlib,collections
sys.path.insert(0,str(Path.cwd()))
from scripts.outputs_retention_rules import select_samples
from scripts.outputs_prune import protected,relative_path
base=Path('experiments/2026-09-30-outputs-retention');m=json.loads((base/'manifest.json').read_text());s=json.loads((base/'summary.json').read_text());c=sqlite3.connect('/private/tmp/outputs-retention-r2/files.sqlite')
cut=s['cutoff_24h_unix_ns'];violations=[]
for p,stamp in c.execute("select f.path,f.mtime_ns from files f join decisions d on d.path=f.path where d.action='delete'"):
 if stamp>cut or protected(relative_path(p)):violations.append(p)
sealed=json.loads((base/'sealed-cohorts.json').read_text())['preserved']
for row in sealed:
 assert not c.execute("select path from decisions where action='delete' and path like ? limit 1",(row['path']+'/%',)).fetchone()
assert not violations
boundary_conflicts=c.execute("select count(*) from boundaries b join decisions d on d.path=b.path where d.action='delete' and d.rule='D1'").fetchone()[0];assert boundary_conflicts==0
model_conflicts=c.execute("select count(*) from decisions d join model_hashes h on h.sha=d.sha where d.action='delete' and (d.path like '%.jpg' or d.path like '%.png')").fetchone()[0];assert model_conflicts==0
model_path_conflicts=c.execute("select count(*) from decisions d join model_paths p on p.path=d.path where d.action='delete'").fetchone()[0];assert model_path_conflicts==0
assert not c.execute("select d.path from decisions d join files f on f.path=d.path where d.action='delete' and (dev,ino) in (select dev,ino from files group by dev,ino having count(*)>1) limit 1").fetchone()
verified=0
for entry in csv.DictReader((base/'thinning.csv').open()):
 for row in csv.DictReader((base/entry['rules_file']).open()):
  values=c.execute("select path,name,t,action from decisions where folder=? and stream=? and rule='D1' and reason in ('rendered_non_request_frame','D1_sample_or_endpoint')",(row['folder'],row['stream'])).fetchall()
  selected,rule,cadence=select_samples([r[:3] for r in values]);assert selected=={r[0] for r in values if r[3]=='keep'},(row['folder'],row['stream'])
  assert rule==row['rule'];verified+=1
reconstructed=0
for e in csv.DictReader((base/'json-reconstruction.csv').open()):
 for row in csv.DictReader((base/e['mapping_file']).open()):
  a=c.execute('select action,sha from decisions where path=?',(row['deleted_path'],)).fetchone();b=c.execute('select action,sha from decisions where path=?',(row['retained_source'],)).fetchone()
  assert a==('delete',row['sha256']) and b==('keep',row['sha256']);reconstructed+=1
result={'completed_unix':time.time(),'manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest(),'boundary_paths_detected':c.execute('select count(*) from boundaries').fetchone()[0],'retired_D2_boundaries_exempted':c.execute("select count(*) from boundaries b join decisions d on d.path=b.path where d.action='delete' and d.rule='D2'").fetchone()[0],'boundary_deletion_conflicts':boundary_conflicts,'model_payload_hash_conflicts':model_conflicts,'model_path_conflicts':model_path_conflicts,'age_or_infrastructure_conflicts':len(violations),'sealed_prefixes_verified':len(sealed),'hardlink_deletions':0,'thinning_streams_recomputed':verified,'json_reconstruction_mappings_checked':reconstructed,'scope':'Separate consistency check of collected file hashes and rule decisions; real filesystem hashes separately verified by outputs_prune dry-run.'}
(base/'plan-consistency.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
