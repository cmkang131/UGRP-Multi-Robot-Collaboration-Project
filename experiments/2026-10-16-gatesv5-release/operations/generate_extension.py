"""gcp2 only: same v1/v5 texture generator for release24's preserved map geometry."""
import pathlib,sys,json,hashlib,importlib.util
import numpy as np
from PIL import Image
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(root))
from sim import natural_scene_texture as v1
spec=importlib.util.spec_from_file_location('gen',str(pathlib.Path(__file__).with_name('generate_scene_textures.py')));gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
plan=json.loads(pathlib.Path(sys.argv[3]).read_text());mapids={e['map_id'] for e in plan['episodes']}
base=v1.manifest();walls={};images={};colours={};maps={}
for mapid in sorted(mapids):
 paths=list((root/'maps').rglob(mapid+'.json'));assert len(paths)==1,(mapid,paths)
 path=paths[0];maps[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
 for w in json.loads(path.read_text())['obstacles']:
  if not w['id'].startswith('wall_'):continue
  size=[*w['half_extents_m'],w['height_m']/2];key=v1.wall_key('zone_'+w['id'],size)
  if key in base['walls'] or key in walls:continue
  walls[key]={}
  for attr,ui,vi in v1.CUBE_FACES:
   face=key+'_'+attr;im=gen.texture(face,max(32,round(2*size[ui]*512)),max(32,round(2*size[vi]*512)),floor=False).resize((512,512),Image.Resampling.LANCZOS)
   gray=np.clip(np.rint(gen.WALL_MEAN_VALUE+gen.WALL_CONTRAST_SCALE*(np.asarray(im,dtype=float)-132)),82,86).astype(np.uint8)
   filename=face+'.png';p=out/filename;Image.fromarray(gray).save(p,compress_level=9)
   walls[key][attr]=face;images[face]=dict(file=filename,width=512,height=512,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
   # PR527 generate_scene_tex5.py exact recolouring, fixed s80 scene only.
   coloured=np.clip(np.array([90,75,110])+(gray.astype(int)-84),0,255).astype(np.uint8)
   p=out/'walls_floor_contrast_v5_indigo110_s80'/filename;p.parent.mkdir(exist_ok=True);Image.fromarray(coloured).save(p)
   colours['walls_floor_contrast_v5_indigo110_s80/'+filename]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest=dict(schema='ugrp.gatesv5.release_geometry_assets.v1',source_v1_manifest=v1.MANIFEST_SHA256,source_v5='cf447537efe9fd66a01e18aa9f414dcabd8273f662d8dc4c96773bd2c9c96757',maps=maps,walls=walls,images=images,colour_images=colours,floor='original v1 floor PNG unchanged',physics='unchanged',generator='same texture and recolouring algorithm; no new acceptance constants')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(walls=len(walls),images=len(images),manifest_sha256=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest())))
