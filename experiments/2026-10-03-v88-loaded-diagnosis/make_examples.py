"""Crop/thumbnail existing JPEGs; no simulated or generated image content."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

from diagnose import RAW, native
from harness.own_beam_edge import edge_line


def main(dest):
    dest.mkdir(parents=True,exist_ok=False)
    sources=[]
    frames={}
    for profile, root in RAW.items():
        for rid in ('r1','r2'):
            folder=root/'zone_wide_two_doors_final_v3'
            frames[profile,rid]=(folder,[json.loads(l) for l in
                (folder/f'robots/{rid}/frames.jsonl').read_text().splitlines()])

    def sample(profile,rid,sec,crop=False):
        folder,records=frames[profile,rid]
        row=min(records,key=lambda r:abs(r['sim_time']-records[0]['sim_time']-sec))
        path=folder/row['path'];blob=path.read_bytes()
        digest=hashlib.sha256(blob).hexdigest()
        assert digest==row['sha256']
        im=Image.open(path).convert('RGB')
        hsv=np.asarray(im.convert('HSV')).astype(int)
        h,s,v=hsv.transpose(2,0,1)
        mask=(h>25)&(h<90)&(s>100)&(v>60)
        roi=np.asarray(im)[40:300,140:500]
        sources.append({'profile':profile,'robot':rid,'relative_s':sec,'frame_id':row['frame_id'],
            'pose':','.join(str(row['commanded_servo'][str(k)]) for k in (3,4,5,6)),
            'path':str(path),'sha256':digest,'crop_xyxy':[140,40,500,300] if crop else None,
            'whole_mask_pixels':int(mask.sum()),'roi_mask_pixels':int(mask[40:300,140:500].sum()),
            'roi_mean_rgb':roi.mean(axis=(0,1)), 'roi_std_rgb':roi.std(axis=(0,1)),
            'edge':edge_line(im)})
        return im.crop((140,40,500,300)) if crop else im

    def sheet(name,rows,*,crop=False):
        w,h=(360,260) if crop else (320,240)
        sheet=Image.new('RGB',(len(rows[0])*w,len(rows)*(h+24)),(255,255,255))
        draw=ImageDraw.Draw(sheet)
        for y,row in enumerate(rows):
            for x,(profile,rid,t) in enumerate(row):
                im=sample(profile,rid,t,crop=crop)
                if not crop:im=im.resize((w,h),Image.Resampling.LANCZOS)
                sheet.paste(im,(x*w,y*(h+24)+24))
                draw.text((x*w+4,y*(h+24)+5),f'{profile} {rid} t={t:g}s',fill=(0,0,0))
        sheet.save(dest/name,quality=90)

    sheet('loaded-hover.jpg',[[('loaded',rid,t) for t in (15.,178.,320.)] for rid in ('r1','r2')])
    sheet('loaded-grasp.jpg',[[('loaded',rid,t) for t in (.2,2.,4.)] for rid in ('r1','r2')])
    sheet('same-pose-comparison.jpg',[[ (profile,'r1',t) for t in (330.2,331.6,333.)]
        for profile in ('unloaded','fine')])
    sheet('grasp-comparison.jpg',[[ (profile,'r1',t) for t in (333.2,334.6,336.)]
        for profile in ('unloaded','fine')])
    sheet('roi-crops.jpg',[[('loaded','r1',178.),('loaded','r2',178.)],
        [('unloaded','r1',331.6),('fine','r1',331.6)]],crop=True)
    sheet('loaded-pan.jpg',[[('loaded',rid,t) for t in (338.6,341.6,344.6)] for rid in ('r1','r2')]+
        [[('loaded',rid,t) for t in (347.6,350.6,353.6)] for rid in ('r1','r2')])
    sheet('r2-baseline.jpg',[[('unloaded','r2',185.),('fine','r2',185.)]])
    sweep=[]
    for rid in ('r1','r2'):
        folder,records=frames['loaded',rid]
        for row in records[::25]:
            path=folder/row['path'];blob=path.read_bytes();assert hashlib.sha256(blob).hexdigest()==row['sha256']
            im=Image.open(path).convert('RGB');h,s,v=np.asarray(im.convert('HSV')).astype(int).transpose(2,0,1)
            count=int(((h>25)&(h<90)&(s>100)&(v>60)).sum())
            sweep.append({'robot':rid,'frame_id':row['frame_id'],'relative_s':row['sim_time']-records[0]['sim_time'],
                'mask_pixels':count,'edge':edge_line(im),'sha256':row['sha256']})
    outputs={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in dest.iterdir()}
    (dest/'manifest.json').write_text(json.dumps({'method':'recorded JPEG thumbnails and exact ROI crops; no rendering',
        'examples':sources,'every_25th_loaded_frame':sweep,'outputs':outputs},indent=2,default=native)+'\n')


if __name__=='__main__':
    main(Path(sys.argv[1]))
