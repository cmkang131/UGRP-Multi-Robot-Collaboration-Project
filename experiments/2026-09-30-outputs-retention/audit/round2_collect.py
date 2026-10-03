"""Read-only inventory for the second retention proposal."""
import os, sqlite3, time, json, subprocess, re
from pathlib import Path
ROOT=Path('/Users/changmin/projects/ugrp/outputs')
DB=Path('/private/tmp/outputs-retention-r2/files.sqlite')
DB.parent.mkdir(parents=True,exist_ok=True)
if DB.exists():raise SystemExit('Use a fresh temporary audit database; do not mix inventories')
con=sqlite3.connect(DB)
con.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, top TEXT, unit TEXT, size INTEGER, allocated INTEGER, mtime_ns INTEGER, mode INTEGER, dev INTEGER, ino INTEGER)')
con.execute('DELETE FROM files')
count=0
def scan(p):
    global count
    batch=[]
    with os.scandir(p) as entries:
        for e in entries:
            s=e.stat(follow_symlinks=False)
            rel=str(Path(e.path).relative_to(ROOT)); parts=rel.split('/')
            unit='/'.join(parts[:2]) if parts[0]=='retired-worktrees' else parts[0]
            batch.append((rel,parts[0],unit,s.st_size,s.st_blocks*512,s.st_mtime_ns,s.st_mode,s.st_dev,s.st_ino))
            count+=1
            if e.is_dir(follow_symlinks=False): scan(e.path)
    con.executemany('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)',batch)
scan(ROOT); con.commit()
con.execute('CREATE INDEX IF NOT EXISTS files_unit ON files(unit)')
con.commit()
print(json.dumps({'entries':count, 'finished_unix':time.time()}),flush=True)
