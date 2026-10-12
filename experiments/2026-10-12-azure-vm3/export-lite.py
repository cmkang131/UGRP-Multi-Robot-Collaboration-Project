from pathlib import Path
import json,base64,hashlib,sys,math
root=Path(sys.argv[1]);excluded=[];inventory=[]
def strip(x,key=''):
 if isinstance(x,list):return [strip(v) for v in x]
 if isinstance(x,dict):return {k:strip(v,k) for k,v in x.items()}
 if isinstance(x,str):
  if x.startswith('data:image/'):
   raw=base64.b64decode(x.split(',',1)[1]);return 'sha256:'+hashlib.sha256(raw).hexdigest()
  if key in ('jpeg_base64','rgb_base64','image') and len(x)>200:
   try:raw=base64.b64decode(x,validate=True)
   except ValueError:return x
   return {'image_omitted':True,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  if 'data:image/' in x and x.lstrip().startswith(('{','[')):
   return json.dumps(strip(json.loads(x)),ensure_ascii=False)
 return x
for p in list(root.rglob('*')):
 if not p.is_file() or p.suffix not in ('.json','.jsonl') or 'lite-text' in p.parts:continue
 data=p.read_bytes()
 if not any(k in data for k in (b'data:image/',b'jpeg_base64',b'"image": "/9j/')):continue
 rel=str(p.relative_to(root));excluded.append('/'+rel)
 if p.suffix=='.json':value=strip(json.loads(data));text=json.dumps(value,indent=2,ensure_ascii=False)+'\n'
 else:text=''.join(json.dumps(strip(json.loads(l)),ensure_ascii=False)+'\n' for l in data.splitlines() if l.strip())
 assert 'data:image/' not in text
 dest=root/'lite-text'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
 inventory.append(dict(source=rel,source_sha256=hashlib.sha256(data).hexdigest(),text=str(dest.relative_to(root)),text_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
(root/'LITE_IMAGE_EXCLUSIONS.txt').write_text('\n'.join(excluded)+'\n')
(root/'LITE_TEXT_MANIFEST.json').write_text(json.dumps(inventory,indent=2)+'\n')
print(json.dumps(dict(run=root.name,embedded_image_files_excluded=len(excluded),text_copies=len(inventory))))
