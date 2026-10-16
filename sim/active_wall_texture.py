"""CC0 photo / seeded DIC multiscale prints, opt-in visual-only dressing."""
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from sim import wall_texture as old

EXP=Path(__file__).resolve().parents[1]/'experiments/2026-10-07-active-wall-map'
VALUES=('off','tape_v1','photo_v1','speckle_v1')


def generate(profile,directory):
    if profile not in VALUES[2:]:
        raise ValueError('EXPLICIT_NEW_TEXTURE_REQUIRED')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    record=copy.deepcopy(json.loads((old.DEFAULT_ASSETS/'layout.json').read_text()))
    record.update(schema='ugrp.wall_texture.'+profile,profile=profile,seed=22001,
                  print_scale='500 pixels/metre, print dimensions from face table; no UV tiling')
    photo=Image.open(EXP/'assets'/json.loads((EXP/'assets/photo-source.json').read_text())['file']).convert('RGB') if profile=='photo_v1' else None
    for face in record['faces']:
        face.pop('tapes',None)
        face.pop('patches',None)
        w,h=max(1,round(face['length_m']*500)),max(1,round(face['height_m']*500))
        rng=np.random.default_rng(int.from_bytes(hashlib.sha256(('22001:'+face['id']).encode()).digest()[:8],'big'))
        if photo is not None:
            # Each wall has one non-tiled crop, recorded for printing. Aspect scaling explicit.
            x,y=map(int,rng.integers(0,128,size=2))
            face['photo_crop_px']=[x,y,x+896,y+896]
            im=photo.crop(face['photo_crop_px']).resize((w,h),Image.Resampling.LANCZOS)
        else:
            im=Image.new('RGB',(w,h),(235,235,235))
            draw=ImageDraw.Draw(im)
            # Poisson disc centres; overlapping discs give 50% expected black coverage.
            diam=np.array([.006,.012,.024])
            mean_area=float(np.mean(math.pi*(diam/2)**2))
            count=round(-math.log(.5)*face['length_m']*face['height_m']/mean_area)
            face['speckles_m']=[]
            for _ in range(count):
                d=float(rng.choice(diam));x=float(rng.uniform(0,face['length_m']));y=float(rng.uniform(0,face['height_m']))
                face['speckles_m'].append([x,y,d])
                draw.ellipse([(x-d/2)*500,(y-d/2)*500,(x+d/2)*500,(y+d/2)*500],fill=(15,15,15))
        path=directory/(face['id']+'.png')
        im.save(path,optimize=True)
        face['png_sha256']=old.sha(path)
    (directory/'layout.json').write_text(json.dumps(record,separators=(',',':'))+'\n')
    return record


def transform_xml(xml,*,wall_texture='off',assets=None):
    if wall_texture in ('off','tape_v1'):
        return old.transform_xml(xml,wall_texture=wall_texture)
    if wall_texture not in VALUES:
        raise ValueError('UNKNOWN_WALL_TEXTURE')
    # Reuse the byte-frozen noncolliding-plane placement and wall-geometry check.
    directory=Path(assets) if assets else Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1/prints')/wall_texture
    return old.transform_xml(xml,wall_texture='tape_v1',assets=directory)
