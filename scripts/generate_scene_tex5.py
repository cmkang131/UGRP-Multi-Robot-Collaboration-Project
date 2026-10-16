"""Retain v1's 82..85 gray variation as common-mode indigo +/-2 texture."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image
from sim import natural_scene_texture as v1
from sim.scene_contrast_v5 import PROFILES

def main():
    out=Path('sim/assets/scene_contrast_v5');out.mkdir(parents=True,exist_ok=True)
    record=v1.manifest();entries={}
    for name,spec in PROFILES.items():
        if not spec.get('pattern'):continue
        for key,item in record['images'].items():
            if key=='floor':continue
            src=v1.checked_file(key,record,v1.ASSETS)
            rgb=np.asarray(Image.open(src).convert('RGB')).astype(int)
            # Median84 and range82..85 measured from pinned v1 wall assets.
            target=np.clip(np.array(spec['rgb'])+(rgb-84),0,255).astype(np.uint8)
            path=out/name/item['file'];path.parent.mkdir(exist_ok=True)
            Image.fromarray(target).save(path)
            entries[name+'/'+item['file']]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps({'floor':'unchanged','source_sha256':v1.MANIFEST_SHA256,
        'operation':'new_RGB + (old_gray - 84), exact original low-amplitude spatial pattern','images':entries},sort_keys=True,indent=2))
if __name__=='__main__':main()
