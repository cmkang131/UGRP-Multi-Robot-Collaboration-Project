"""Offline renderer comparison; reports distributions, invents no tolerances."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np


def compare(reference,candidate,out):
    ref=json.loads((reference/'result.json').read_text());cand=json.loads((candidate/'result.json').read_text())
    rows=[]
    for i in range(30):
        a=np.load(reference/f'{i:02d}.npz');b=np.load(candidate/f'{i:02d}.npz')
        x=a['rgb'].astype(np.float32);y=b['rgb'].astype(np.float32)
        mae=lambda z:float(np.abs(x-z).mean())
        variants={'identity':mae(y),'flip_vertical':mae(y[::-1]),'flip_horizontal':mae(y[:,::-1])}
        channels={''.join(map(str,p)):mae(y[:,:,p]) for p in itertools.permutations(range(3))}
        am=a['mask'].astype(bool);bm=b['mask'].astype(bool);union=int((am|bm).sum())
        ab=np.all(x==0,axis=2);bb=np.all(y==0,axis=2)
        rows.append({'n':i,'stratum':cand['snapshots'][i]['stratum'],'MAE_RGB_255':variants['identity'],
            'orientation_mae':variants,'best_orientation':min(variants,key=variants.get),
            'channel_mae':channels,'best_channels':min(channels,key=channels.get),
            'mask_IoU':float((am&bm).sum()/union) if union else None,
            'mask_union_pixels':union,'black_xor_pixels':int((ab^bb).sum()),
            'camera_pos_max_abs_m':float(np.abs(a['camera_pos']-b['camera_pos']).max()),
            'camera_rot_max_abs':float(np.abs(a['camera_rot']-b['camera_rot']).max()),
            'rgb_sha_equal':np.array_equal(x,y),
            'reference_file_sha256':hashlib.sha256((reference/f'{i:02d}.npz').read_bytes()).hexdigest(),
            'candidate_file_sha256':hashlib.sha256((candidate/f'{i:02d}.npz').read_bytes()).hexdigest()})
    mae=np.array([r['MAE_RGB_255'] for r in rows]);ious=[r['mask_IoU'] for r in rows if r['mask_IoU'] is not None]
    result={'snapshots_compared':len(rows),'reference_gl':ref['gl'],'candidate_gl':cand['gl'],
        'same_source_states':ref['source_states_sha256']==cand['source_states_sha256'],
        'K_equal':ref['K']==cand['K'],'D_equal':ref['D']==cand['D'],
        'camera_SE3_exact':all(r['camera_pos_max_abs_m']==0 and r['camera_rot_max_abs']==0 for r in rows),
        'MAE_median':float(np.median(mae)),'MAE_max':float(mae.max()),
        'mask_IoU_median':float(np.median(ious)) if ious else None,'mask_IoU_min':min(ious) if ious else None,
        'black_xor_max_pixels':max(r['black_xor_pixels'] for r in rows),
        'identity_orientation_n':sum(r['best_orientation']=='identity' for r in rows),
        'identity_channels_n':sum(r['best_channels']=='012' for r in rows),
        'edge_touch_snapshots':sum(r['edge_pixels']>0 for r in cand['snapshots']),
        'empty_target_mask_snapshots':sum(r['mask_pixels']==0 for r in cand['snapshots']),
        'scope':'same immutable L4 states, existing renderer paths; no trained policy or live teacher result',
        'coverage_limit':'phase-stratified 30; edge and occlusion are measured, not guaranteed five each; single cyan box has no beam end bands',
        'acceptance':'diagnostic only; no pixel tolerance introduced, full B needs explicit edge/occlusion and band coverage review',
        'raw_paths':[str(reference),str(candidate)],'rows':rows}
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    # Pixel difference montage generated on analysis host, no Mac rendering.
    from PIL import Image,ImageDraw
    canvas=Image.new('RGB',(960,30*132),(240,240,240));draw=ImageDraw.Draw(canvas)
    for i in range(30):
        a=np.load(reference/f'{i:02d}.npz')['rgb'];b=np.load(candidate/f'{i:02d}.npz')['rgb']
        diff=np.clip(np.abs(a.astype(int)-b.astype(int))*8,0,255).astype(np.uint8)
        for j,im in enumerate((a,b,diff)):
            canvas.paste(Image.fromarray(im).resize((160,120)),(j*320,i*132+12))
        draw.text((0,i*132),f'{i:02d} {rows[i]["stratum"]} MAE={rows[i]["MAE_RGB_255"]:.3f} IoU={rows[i]["mask_IoU"]}',fill=(0,0,0))
    canvas.save(out.with_suffix('.jpg'),quality=85)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference',type=Path);p.add_argument('candidate',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();compare(a.reference,a.candidate,a.out)
