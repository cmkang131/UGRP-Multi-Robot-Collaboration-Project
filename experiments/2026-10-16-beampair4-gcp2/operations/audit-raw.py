import pathlib,hashlib,json,sys
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/d72efd13957ce450c5cccc3fd93a555a37dd4705')
from scripts.audit_beampair1 import read,verify_manifest
r=pathlib.Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/beampair4-gcp2';rows=[]
raws=sorted((r/'runs').glob('beampair3-gcp2-repro-*-e645b34b/raw'))
raws+=sorted((r/'runs/beampair4-r3-gcp2-d72efd13/round').glob('diagnostic/episode-*/raw'))
for raw in raws:
 x=read(raw/'result.json')
 if x['status']=='running':continue
 a=raw.parent/'adapter';files={str(p.relative_to(raw.parent)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in raw.parent.rglob('*') if p.is_file()}
 path=ops/(raw.parent.name+'-'+str(read(raw/'plan.json')['seed'])+'-hashes.json');path.write_text(json.dumps(files,indent=2)+'\n')
 rows.append(dict(raw=str(raw),seed=read(raw/'plan.json')['seed'],verified_raw_files=verify_manifest(raw),verified_adapter_files=verify_manifest(a),all_files=len(files),all_bytes=sum(f['bytes'] for f in files.values()),full_hash_manifest=str(path),full_hash_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),result_status=x['status'],host=x['execution_host'],scene_xml_sha256=hashlib.sha256((raw/'scene.xml').read_bytes()).hexdigest()))
(ops/'integrity-summary.json').write_text(json.dumps(dict(host='gcp2',runs=rows),indent=2)+'\n')
print(json.dumps(rows)[:2300])
