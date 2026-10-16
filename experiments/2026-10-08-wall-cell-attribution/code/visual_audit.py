from diagnose import *
import cv2
from collections import defaultdict
COLORS={'detector':(0,0,255),'pose':(255,100,0),'range_projection':(0,150,255),'object':(255,0,255),'cell_boundary':(0,200,0),'unresolved':(0,255,255)}
for seed,ep in EPISODES.items():
    labels=Labels(ep);by=defaultdict(list)
    for cell in load(RAW/f'{seed}-false-cells.json'):
        for s in cell['sources']:by[s['frame_id']].append(s)
    images=[]
    for frame,sources in sorted(by.items()):
        f=labels.frames[frame];assert sha(ep/f['path'])==f['sha256']
        und=modules()[0].undistort(cv2.imread(str(ep/f['path'])))
        for s in sources:
            u,v=s['uv']
            if 0<=u<640 and 0<=v<480:cv2.circle(und,(round(u),round(v)),3,COLORS[s['category']],-1)
        im=cv2.resize(und,(320,240));cv2.rectangle(im,(0,0),(320,22),(255,255,255),-1)
        cv2.putText(im,f'{seed} frame{frame} t{f["sim_time"]:.1f}',(5,16),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
        images.append(im)
    for page in range(math.ceil(len(images)/12)):
        ims=images[page*12:(page+1)*12]
        ims.extend([np.full_like(images[0],255)]*(12-len(ims)))
        mosaic=np.vstack([np.hstack(ims[i:i+3]) for i in range(0,12,3)])
        cv2.imwrite(str(RAW/f'audit-{seed}-{page}.jpg'),mosaic,[cv2.IMWRITE_JPEG_QUALITY,85])
