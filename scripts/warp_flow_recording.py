"""Recording-only crash-safe own-JPEG ring; no simulator or actor calls."""
import hashlib
import json
import os
from pathlib import Path


class DiskRing:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.sequence=0
        # User10/15: last10 SIM seconds at the unchanged10Hz control clock.
        self.slots=100

    def add(self,world_t,images):
        row=dict(sequence=self.sequence,world_t=world_t,files={})
        for rid,jpg in images.items():
            target=self.root/f'{self.sequence%self.slots:03d}-{rid}.jpg'
            temporary=target.with_suffix('.tmp')
            temporary.write_bytes(jpg);os.replace(temporary,target)
            row['files'][rid]=dict(path=str(target),sha256=hashlib.sha256(jpg).hexdigest(),bytes=len(jpg))
        # Append only after all camera files are in place. Recovery verifies
        # hashes, so a crash midway through replacing a slot never mislabels it.
        with (self.root/'journal.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n');f.flush()
        self.sequence+=1

    @staticmethod
    def recover(root):
        root=Path(root);rows=[]
        path=root/'journal.jsonl'
        if not path.exists():return rows
        for line in path.read_text().splitlines():
            try:row=json.loads(line)
            except json.JSONDecodeError:continue
            if all(Path(v['path']).exists() and hashlib.sha256(Path(v['path']).read_bytes()).hexdigest()==v['sha256']
                   for v in row['files'].values()):rows.append(row)
        return rows
