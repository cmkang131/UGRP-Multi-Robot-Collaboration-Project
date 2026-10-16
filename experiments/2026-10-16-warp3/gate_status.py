"""Read-only progress/attempt inventory. Success here is still provisional."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess


def read(path):
    try:raw=path.read_bytes()
    except FileNotFoundError:
        compressed=Path(str(path)+'.zst')
        if not compressed.exists():return {}
        raw=subprocess.check_output(['zstd','-dc',str(compressed)])
    try:return json.loads(raw)
    except json.JSONDecodeError:return {}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    groups=[];finished=[];reasons=Counter()
    for group in range(7):
        root=a.root/f'teacher-r1-group{group}';summary=read(root/'summary.json');progress=read(root/'progress.json')
        phases=Counter(read(f).get('phase','unknown') for f in root.glob('world-*/progress.json'))
        ticks=progress.get('ticks',[])
        groups.append(dict(group=group,status=summary.get('status'),tick=max(ticks) if ticks else None,
            tick_range=[min(ticks),max(ticks)] if ticks else None,
            active=progress.get('active'),phases=dict(phases),error=summary.get('error')))
        for folder in root.glob('world-*'):
            if not folder.is_dir():continue
            path=folder/'result.json'
            result=read(path)
            if not result or result.get('status')=='running':continue
            plan=read(path.parent/'plan.json');reason=result.get('teacher',{}).get('command_result')
            finished.append(dict(group=group,world=path.parent.name,seed=plan.get('seed'),kind=plan.get('kind'),
                status=result.get('status'),success=result.get('physical_success'),
                cap_end=bool(result.get('cap_end') or reason=='phase_timeout'),reason=reason,
                raw=str(path if path.exists() else Path(str(path)+'.zst')),input_audit=result.get('input_audit')))
            if not result.get('physical_success'):reasons[reason or result.get('error') or result.get('status')]+=1
    report=dict(groups=groups,finished=finished,terminal_records=len(finished),
        provisional_success=sum(x['success'] is True for x in finished),
        cap_end=sum(x['cap_end'] is True for x in finished),reasons=dict(reasons),
        scope='progress only; final gate requires independent raw recount and playback review')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
