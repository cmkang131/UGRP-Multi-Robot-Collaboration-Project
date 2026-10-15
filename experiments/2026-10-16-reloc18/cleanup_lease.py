"""Remove only the finished reloc18 lease; preserve other users of gcp2."""
import datetime, json, os, platform, shlex, subprocess
from pathlib import Path

ROOT=Path('/home/ugrp/ugrp-sim')


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    assert (ROOT/'runs/reloc18-round3/ANALYSIS_DONE.json').exists()
    jobs=[]
    for line in subprocess.check_output(['ps','-u','ugrp','-o','pid=,ppid=,args='],text=True).splitlines():
        pid,ppid,args=line.strip().split(None,2)
        if int(pid) in (os.getpid(),os.getppid()):continue
        command=Path(shlex.split(args)[0]).name
        if command.startswith('python') or command in ('ffmpeg','mujoco'):
            jobs.append(dict(pid=int(pid),ppid=int(ppid),command=args))
    own=[j for j in jobs if 'reloc18' in j['command'] or '133c12f4cbd5efafba5f94f761d494f45bef075a' in j['command']]
    assert not own, own
    lease=ROOT/'leases/reloc18.json'
    before=json.loads(lease.read_text());assert before['task']=='reloc18'
    others={p.name:json.loads(p.read_text()) for p in lease.parent.glob('*.json') if p!=lease}
    record=dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),own_workers=0,
                own_lease_before=before,other_leases=others,remaining_python_mujoco_ffmpeg=jobs,
                vm_stop_requested=False,reason='other lease/process present; VM shared with active work',
                action='removed only reloc18.json; no process killed; no VM stop')
    assert others or jobs, 'No other task remains: reassess VM shutdown explicitly'
    lease.unlink()
    record['own_lease_removed']=not lease.exists()
    (ROOT/'runs/reloc18-report/cleanup.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(own_workers=0,own_lease_removed=record['own_lease_removed'],other_leases=list(others),other_processes=len(jobs),vm_stop_requested=False)))


if __name__=='__main__':main()
