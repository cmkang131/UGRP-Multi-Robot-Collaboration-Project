"""Read every existing TensorBoard event; never starts a viewer or changes outputs."""
import hashlib,json,re,sqlite3
from pathlib import Path
from tensorboard.backend.event_processing.event_file_loader import LegacyEventFileLoader
ROOT=Path('/Users/changmin/projects/ugrp/outputs');TMP=Path('/private/tmp/outputs-retention-r2')
c=sqlite3.connect(TMP/'files.sqlite');hashes={};paths={};errors=[];events=images=texts=0
for rel, in c.execute("select path from files where path like '%events.out.tfevents.%' and mode & 61440=32768"):
 try:
  for ev in LegacyEventFileLoader(str(ROOT/rel)).Load():
   events+=1
   for val in ev.summary.value:
    if val.HasField('image'):
     images+=1;hashes[hashlib.sha256(val.image.encoded_image_string).hexdigest()]=rel+':'+val.tag
    if val.HasField('tensor'):
     for content in val.tensor.string_val:
      if content.startswith((b'\xff\xd8',b'\x89PNG')):
       images+=1;hashes[hashlib.sha256(content).hexdigest()]=rel+':'+val.tag
      elif b'.jpg' in content or b'.png' in content:
       texts+=1
       for value in re.findall(r'(?<![\w./:+%-])[\w./:+%-]{1,500}\.(?:jpg|png)',content.decode('utf8',errors='replace')):
        if '/outputs/' in value:value=value.split('/outputs/',1)[1]
        paths[value]=rel+':'+val.tag
 except Exception as e:errors.append({'path':rel,'error':str(e)})
for rel, in c.execute("select path from files where path like '%tensorboard%/manifest.json'"):
 try:
  value=json.loads((ROOT/rel).read_text());source=value.get('source','')
  if isinstance(source,str) and '/outputs/' in source:source=source.split('/outputs/',1)[1]
  else:source=''
  for p,item in value.get('source_files',{}).items():
   if p.lower().endswith(('.jpg','.png')):
    if isinstance(item,dict) and item.get('sha256'):hashes[item['sha256']]=rel+':'+p
    paths[source+'/'+p if source else p]=rel
 except Exception as e:errors.append({'path':rel,'error':str(e)})
result={'events':events,'images':images,'text_with_paths':texts,'hashes':hashes,'paths':paths,'errors':errors}
(TMP/'tensorboard-r2.json').write_text(json.dumps(result,ensure_ascii=False)+'\n')
print({k:len(v) if isinstance(v,(dict,list)) else v for k,v in result.items()})
