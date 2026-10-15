"""Local saved inventory only; operations must recheck live GCP before admission."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
BASE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
files=list((ROOT/'experiments').rglob('*.json'))+list((BASE/'vm3-queue').glob('*.json'))
hits=[];checked=0
# Match explicit integer seed fields, not arbitrary floating-point digits.
pattern=re.compile(r'"seed"\s*:\s*(796[0-3][0-9])\b')
for p in files:
 if HERE in p.parents:continue
 try:s=p.read_text()
 except (OSError,UnicodeError):continue
 checked+=1
 for m in pattern.finditer(s):hits.append({'path':str(p),'seed':int(m.group(1))})
if hits:raise ValueError(hits)
q={'reserved_range':[79600,79639],'split':'crate15_diagnostic','local_json_files_checked':checked,
 'explicit_seed_conflicts':hits,'scope':'current worktree experiment JSON and existing local queue snapshots only',
 'rejected_candidate_range':{'range':[79500,79539],'reason':'conflicts with four saved solo queues; never submitted'},
 'remote_live_inventory_verified':False,'required_before_admission':'operations checks live GCP inventory and all active queues under shared admission lock'}
(HERE/'seed-reservation.json').write_text(json.dumps(q,indent=2)+'\n');print(q)
