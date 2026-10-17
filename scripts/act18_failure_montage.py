"""1Hz last-10SIM failure montage for an ACT18 finite stage; raw frames stay on VM."""
import argparse
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

COLS=10          # 1Hz over the last10SIM window
CELL=(160,120)   # 4x downscale of the saved 640x480 self-RGB frames


def font(size=12):
    try:return ImageFont.load_default(size=size)
    except TypeError:return ImageFont.load_default()


def montage(stage,evaluation_dirs,rows,out):
    labels={r['seed']:r for r in rows}
    ordered=[]
    for evaluation in map(Path,evaluation_dirs):
        plans=json.loads((evaluation/'initial-plans.json').read_text())['episodes']
        for index,plan in enumerate(plans):
            frames=sorted((evaluation/'failure-camera-window'/('world-%03d'%index)).glob('*.jpg'),
                          key=lambda p:int(p.stem))
            if len(frames)<COLS:raise ValueError('insufficient last10s frames for world %d'%index)
            step=max(1,(len(frames)-1)//(COLS-1))
            ordered.append(dict(seed=plan['seed'],kind=plan['kind'],frames=[frames[i*step] for i in range(COLS)],
                                reason=labels.get(plan['seed'],{}).get('reason_category','not_recounted'),
                                lift=labels.get(plan['seed'],{}).get('lift_success'),
                                cap_end=labels.get(plan['seed'],{}).get('cap_end')))
    if len(ordered)!=len(rows):raise ValueError('world/recount row count differs')
    ordered.sort(key=lambda r:r['seed'])
    image=Image.new('RGB',(CELL[0]*COLS,CELL[1]*len(ordered)),(16,16,16));draw=ImageDraw.Draw(image)
    for row,item in enumerate(ordered):
        y=row*CELL[1]
        for col,frame in enumerate(item['frames']):
            with Image.open(frame) as source:
                image.paste(source.convert('RGB').resize(CELL,Image.BILINEAR),(col*CELL[0],y))
        text='%d %s%s'%(item['seed'],item['reason'],' lift' if item['lift'] else '')
        draw.rectangle([0,y,220,y+16],fill=(0,0,0));draw.text((2,y+1),text,fill=(230,230,60),font=font())
    out.parent.mkdir(parents=True,exist_ok=True);image.save(out)
    return dict(path=str(out),sha256=__import__('hashlib').sha256(out.read_bytes()).hexdigest(),
                width=image.width,height=image.height,rows=[dict(seed=i['seed'],kind=i['kind'],reason=i['reason'],
                lift_success=i['lift'],cap_end=i['cap_end'],world_frames=str(i['frames'][0].parent)) for i in ordered])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    p.add_argument('--stage-dir',type=Path,required=True);p.add_argument('--recount',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:p.error('failure montage default OFF')
    summary=json.loads((a.stage_dir/'summary.json').read_text())
    if not summary.get('complete'):raise ValueError('complete finite stage required')
    rows=json.loads(a.recount.read_text())['rows']
    report=montage(a.stage_dir,summary['finished'],rows,a.out)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
