"""Native own-RGB/world assignment snapshots; not failure replay or success proof."""
import argparse
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from act16w_runtime import require_gcp2,frozen_source,sha256
B=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--worlds',default='[[0,0],[0,1],[3,0],[3,1]]')
    p.add_argument('--ticks',default='0,40,80,120');a=p.parse_args()
    worlds=json.loads(a.worlds);ticks=[int(x) for x in a.ticks.split(',')]
    if (len(worlds)!=4 or len(ticks)!=4 or min(ticks)<0
            or any(len(pair)!=2 or any(type(x) is not int or x<0 for x in pair) for pair in worlds)):
        p.error('the4x4 review sheet requires four explicit worlds and four nonnegative capture ticks')
    host=require_gcp2();source=frozen_source(ROOT);a.out.mkdir(parents=True,exist_ok=False)
    lease=B/'leases/act16w-native-snapshots.json';now=datetime.now(timezone.utc)
    with lease.open('x') as f:json.dump(dict(task='act16w-native-snapshots',pid=os.getpid(),start=now.isoformat(),expected_end=(now+timedelta(minutes=2)).isoformat(),concurrency=0,scope='ffmpeg CPU image snapshots only'),f)
    try:
        plans=json.loads((B/'runs/act16w-resume2-record-references/plans.json').read_text())['episodes'];rows=[]
        for group,world in worlds:
            root=B/'runs/act16w-resume2-data-r2'/f'group-{group:02d}';launch=json.loads((root/'launch.json').read_text());plan=plans[launch['world_indices'][world]]
            commands=[json.loads(x) for x in (root/'controller'/f'world-{world:03d}'/'teacher-commands.jsonl').read_text().splitlines() if x.strip()]
            for tick in ticks:
                image=root/'capture'/f'world-{world:03d}'/'capture'/f'{tick:06d}.jpg';target=a.out/f'snapshot-{len(rows):03d}.jpg'
                title=f"g{group} w{world} seed{plan['seed']} {plan['kind']} SIM{tick/10:.1f}"
                vf=f"scale=320:240,drawtext=text='{title}':x=4:y=4:fontsize=12:fontcolor=white:box=1:boxcolor=black"
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(image),'-vf',vf,'-frames:v','1','-q:v','3',str(target)],check=True)
                rows.append(dict(group=group,world=world,seed=plan['seed'],kind=plan['kind'],elapsed_SIM_s=tick*.1,recorded_command_t=commands[tick]['t'],phase_after=commands[tick]['phase'],native_source=str(image),native_sha256=sha256(image),snapshot=str(target),snapshot_sha256=sha256(target)))
        montage=a.out/'native-world-assignment.jpg'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-framerate','1','-i',str(a.out/'snapshot-%03d.jpg'),'-vf','tile=4x4','-frames:v','1','-q:v','3',str(montage)],check=True)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(montage)],text=True))
        report=dict(status='complete',host=host,source_sha=source,scope='4 selected worlds at explicit capture ticks: sparse snapshots for native camera/world assignment only; no motion/failure/success claim, no overview replay',reproduce=sys.argv,rows=rows,montage=dict(path=str(montage),sha256=sha256(montage),bytes=montage.stat().st_size,width=probe['streams'][0]['width'],height=probe['streams'][0]['height']))
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['montage']))
    finally:lease.unlink(missing_ok=True)


if __name__=='__main__':main()
