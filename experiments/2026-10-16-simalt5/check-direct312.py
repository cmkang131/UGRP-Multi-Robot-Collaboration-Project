"""Probe whether the pinned Warp API accepts the original C312 MjModel."""
import json
from pathlib import Path
import sys
import traceback

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt5')
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/62563f51/scripts')
from simalt_host import gcp2_identity
host=gcp2_identity()
import mujoco
assert mujoco.__version__=='3.12.0'
model=mujoco.MjModel.from_xml_path(str(ROOT.parent/'simalt3/fixture/scene.xml'))
sys.path.append(str(ROOT.parent/'simalt3/warp-env/lib/python3.12/site-packages'))
result={'host':host,'C_version':mujoco.__version__,'physics_steps':0,'method':'C312 model object directly into pinned MJWarp'}
try:
    import mujoco_warp as mjw
    import warp as wp
    wp.init()
    wm=mjw.put_model(model)
    result['status']='import_only_pass'
except Exception as error:
    result.update(status='unsupported',error=str(error),traceback=traceback.format_exc())
with (ROOT/'direct312-import.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result,indent=2))
