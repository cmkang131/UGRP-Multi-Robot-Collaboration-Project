"""Read-only gcp2 lease/process ownership snapshot before a VM stop."""
import hashlib
import json
import os
from pathlib import Path
import sys


def owns_output(args, task):
    """Shared source/teacher paths do not establish process ownership."""
    root=Path('/home/ugrp/ugrp-sim/runs')/task
    if '--out' in args:
        index=args.index('--out')+1
        if index<len(args):
            output=Path(args[index])
            return output==root or output.is_relative_to(root)
    if args and Path(args[0]).name.startswith('ffmpeg') and len(args)>1:
        return Path(args[-1]).is_relative_to(root)
    return False


def main():
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    task=sys.argv[1]
    leases=Path('/home/ugrp/ugrp-sim/leases')
    files=sorted(p.name for p in leases.iterdir() if p.is_file())
    other_leases=[p for p in files if p!=task+'.json']
    processes=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():continue
        try:
            if entry.stat().st_uid!=os.getuid():continue
            args=(entry/'cmdline').read_bytes().split(b'\0')
            if not args or not args[0]:continue
            executable=Path(args[0].decode(errors='replace')).name
            if not executable.startswith(('python','mujoco','ffmpeg')):continue
            owned=owns_output([arg.decode(errors='replace') for arg in args if arg],task)
            # Do not expose arbitrary foreign arguments or credentials.
            processes.append({'pid':int(entry.name),'executable':executable,'owned':owned,
                              'argv_sha256':hashlib.sha256(b'\0'.join(args)).hexdigest()})
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    result={'host':host,'task':task,'lease_files':files,'other_leases':other_leases,
            'processes':processes,'other_processes':[p for p in processes if not p['owned']],
            'may_stop_after_own_work_exits':not other_leases and all(p['owned'] for p in processes)}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
