"""Remove only reloc16 lease after terminal results and no owned workers."""
import datetime,json,os,platform,re
from pathlib import Path
ROOT=Path('/home/ugrp/ugrp-sim')
if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
assert json.loads((ROOT/'runs/reloc16-round3/summary.json').read_text())['status']=='MEASURED'
owned=[];other=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name)==os.getpid():continue
    try:
        argv=p.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0');exe=Path(argv[0]).name
        if not (exe.startswith('python') or exe.startswith('mujoco') or exe=='ffmpeg'):continue
        cwd=os.readlink(p/'cwd');cmd=' '.join(argv)
        if '/home/ugrp/ugrp-sim' not in cmd+cwd:continue
        row=dict(pid=int(p.name),executable=exe,cwd=cwd)
        (owned if 'reloc16-' in cmd+cwd else other).append(row)
    except (OSError,IndexError):continue
leases={p.name:json.loads(p.read_text()) for p in (ROOT/'leases').glob('*.json')}
if owned:raise RuntimeError(f'OWN_WORKERS_REMAIN:{owned}')
assert leases.get('reloc16.json',{}).get('task')=='reloc16'
(ROOT/'leases/reloc16.json').unlink()
remaining={p.name:json.loads(p.read_text()) for p in (ROOT/'leases').glob('*.json')}
record=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),own_workers=owned,other_ugrp_processes=other,
    before_leases=leases,remaining_leases=remaining,removed_only='reloc16.json',vm_action='left_running',
    shutdown_forbidden=bool(remaining or other),reason='other task leases/processes are present; never stopped or killed another task')
assert record['shutdown_forbidden'],'No other task remains; review normal VM STOP procedure separately'
(ROOT/'runs/reloc16-lifecycle.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(removed='reloc16.json',other_leases=list(remaining),other_process_N=len(other),vm_action='left_running')))
