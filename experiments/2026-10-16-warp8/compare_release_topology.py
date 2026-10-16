import datetime as dt, hashlib, json, os
from pathlib import Path
import sys
sys.path.insert(0,'/home/ugrp/ugrp-sim/ops-reviews/warp8')
from warp_flow_model import canonical_xml, free_roots
import xml.etree.ElementTree as ET
r=Path('/home/ugrp/ugrp-sim');lease=r/'leases/warp8-topology-check.json';now=dt.datetime.now(dt.timezone.utc)
with lease.open('x') as f:json.dump(dict(task='warp8-topology-check',pid=os.getpid(),started_at=now.isoformat(),expected_end=(now+dt.timedelta(minutes=5)).isoformat(),scope='CPU XML structure only; no simulator or GPU'),f)
try:
 values=json.load(sys.stdin);out=r/'ops-reviews/warp8/release-xml-pairwise';out.mkdir(exist_ok=False);results=[]
 for name,v in values.items():
  b=v['xml'].encode();assert hashlib.sha256(b).hexdigest()==v['sha256'];(out/(name+'.xml')).write_bytes(b)
 for left,a in values.items():
  for right,b in values.items():
   try:
    _,audit=canonical_xml(a['xml'],b['xml'],world_parameters=True);result={'accepted':True,'audit':audit}
   except ValueError as e:result={'accepted':False,'error':str(e)}
   aa=set(free_roots(ET.fromstring(a['xml'])));bb=set(free_roots(ET.fromstring(b['xml'])))
   results.append(dict(left=left,right=right,left_only=sorted(aa-bb),right_only=sorted(bb-aa),**result))
 v={'utc':now.isoformat(),'simulation_source':'gcp3 canonical XML reference exports','analysis_host':'gcp2_CPU','source_files':{n:{k:v for k,v in x.items() if k!='xml'} for n,x in values.items()},'canonicalizer_sha256':hashlib.sha256(Path('/home/ugrp/ugrp-sim/ops-reviews/warp8/warp_flow_model.py').read_bytes()).hexdigest(),'results':results,'scope':'exact existing canonical XML guard only; not physics, model conversion, rollout or memory proof'}
 (out/'summary.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
finally:
 assert json.loads(lease.read_text())['pid']==os.getpid();lease.unlink()
