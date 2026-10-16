"""Lossless evidence archive/restore; source code and other workers are excluded."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--seal',nargs='+',type=Path);mode.add_argument('--restore',action='store_true');a=p.parse_args()
sha=lambda b:hashlib.sha256(b).hexdigest()
if a.restore:
 for r in json.loads(a.receipt.read_text()):
  path=Path(r['original']);z=Path(r['compressed']);blob=subprocess.check_output(['zstd','-q','-d','-c','--',str(z)])
  assert len(blob)==r['original_bytes'] and sha(blob)==r['original_sha256']
  if path.exists():assert sha(path.read_bytes())==r['original_sha256']
  else:
   with path.open('xb') as f:f.write(blob)
else:
 if a.receipt.exists():raise ValueError('NEW_RECEIPT_REQUIRED')
 rows=[]
 for root in a.seal:
  for path in sorted(root.rglob('*')):
   if not path.is_file() or path.suffix not in ('.json','.jsonl') or path.stat().st_size<=64*1024 or path==a.receipt:continue
   raw=path.read_bytes();z=path.with_suffix(path.suffix+'.zst')
   if z.exists():raise ValueError('ARCHIVE_EXISTS:'+str(z))
   subprocess.run(['zstd','-q','-T1','-o',str(z),'--',str(path)],check=True)
   decoded=subprocess.check_output(['zstd','-q','-d','-c','--',str(z)])
   assert decoded==raw
   rows.append(dict(original=str(path),original_bytes=len(raw),original_sha256=sha(raw),compressed=str(z),compressed_bytes=z.stat().st_size,compressed_sha256=sha(z.read_bytes()),decompression_verified=True))
   # Persist recovery information before removing the oversized plain JSON.
   a.receipt.write_text(json.dumps(rows,indent=2)+'\n');path.unlink()
 if not a.receipt.exists():a.receipt.write_text('[]\n')
 print(json.dumps(dict(files=len(rows),original_bytes=sum(r['original_bytes'] for r in rows),compressed_bytes=sum(r['compressed_bytes'] for r in rows))))
