"""Host process admission only; never imported by the ACT worker."""
from pathlib import Path
import re


def other_run_pids(ps_text, owned_roots):
    rows={}
    for line in ps_text.splitlines():
        parts=line.strip().split(None,2)
        if len(parts)==3 and parts[0].isdigit() and parts[1].isdigit():
            rows[int(parts[0])]=(int(parts[1]),parts[2])
    owned=set(owned_roots)
    while True:
        more={pid for pid,(parent,_) in rows.items() if parent in owned}
        if more<=owned:break
        owned.update(more)
    result=[]
    for pid,(_,args) in rows.items():
        if pid in owned or not Path(args.split()[0]).name.startswith('python'):
            continue
        # Count actual runner processes rather than sim_cli/timeout parents or
        # inference workers. Covers current pair/solo/E2E/reloc task families;
        # declared leases remain the other independent admission bound.
        if re.search(r'(?:-m scripts\.(?:run_|probe_)|/scripts/(?:run_|probe_)|run_round\.py.*--worker|(?:sim|scripts)\.mujoco)',args):
            result.append(pid)
    return sorted(result)
