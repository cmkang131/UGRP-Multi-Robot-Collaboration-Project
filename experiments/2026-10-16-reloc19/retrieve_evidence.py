"""Mac: retrieve summaries and six terminal frames; raw analysis stays on gcp2."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
names=['brief.json','integrity.json','final-integrity.json','queue.json','rejection-table.json','rejection-table.initial.json','speed-gate.json','retrieval-manifest.json','summary.json','DONE']
def sha(b):return hashlib.sha256(b).hexdigest()
for n in (1,2,3):
 out=ROOT/f'round{n}';out.mkdir(exist_ok=True)
 args=['rsync','-az','--include=*/']+['--include=/'+x for x in names]+['--include=failure-*','--exclude=*',f'gcp2:/home/ugrp/ugrp-sim/runs/reloc19-round{n}/',str(out)+'/']
 subprocess.run(args,check=True)
 manifest=json.loads((out/'retrieval-manifest.json').read_text());checked=[]
 for name,entry in manifest.items():
  p=out/name
  if p.is_file():
   assert p.stat().st_size==entry['bytes'] and sha(p.read_bytes())==entry['sha256'],name
   checked.append(name)
 s=out/'summary.json';data=s.read_bytes()
 subprocess.run(['zstd','-q','-f','-19',str(s)],check=True)
 assert subprocess.check_output(['zstd','-dc',str(s)+'.zst'])==data
 s.unlink()
 receipt=dict(verified=True,files=len(checked),checked=checked,source=f'/home/ugrp/ugrp-sim/runs/reloc19-round{n}',manifest_sha256=sha((out/'retrieval-manifest.json').read_bytes()),summary_compressed_sha256=sha(Path(str(s)+'.zst').read_bytes()),summary_decoded_sha256=sha(data),raw_retrieved=False,scope='selected summaries and six saved terminal frames per run, full raw remains gcp2')
 (out/'retrieval-verified.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(n,len(checked),'verified')
