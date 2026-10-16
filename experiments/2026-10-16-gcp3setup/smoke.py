"""GPU infrastructure probe: two worlds, exactly one MJWarp step, no renderer/LLM."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

import mujoco
import mujoco_warp as mjw
import numpy as np
import warp as wp

wp.init()
model = mujoco.MjModel.from_xml_string('''<mujoco><option timestep="0.002"/>
<worldbody><geom type="plane" size="1 1 .1"/>
<body pos="0 0 1"><freejoint/><geom type="sphere" size=".05" mass="1"/></body>
</worldbody></mujoco>''')
device = wp.get_device('cuda:0')
with wp.ScopedDevice(device):
    m = mjw.put_model(model)
    d = mjw.make_data(model, nworld=2)
    before = d.qpos.numpy().copy()
    mjw.step(m, d)
    wp.synchronize()
    after = d.qpos.numpy()
    times = d.time.numpy().tolist()
assert np.isfinite(after).all()
assert np.all(after[:, 2] < before[:, 2])
assert np.allclose(times, model.opt.timestep)
root = Path(mjw.__file__).parent
result = dict(status='PASS', scope='infrastructure only; no teacher/student/mission gate',
              backend='mjwarp', nworld=2, steps=1, sim_time_s=times,
              python=platform.python_version(), platform=platform.platform(), device=str(device),
              gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'], text=True).strip(),
              versions={p: importlib.metadata.version(p) for p in ('mujoco','mujoco-warp','warp-lang','numpy','Pillow','opencv-python-headless')},
              source_files_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('_src/types.py','_src/forward.py','_src/io.py')},
              qpos_before=before.tolist(), qpos_after=after.tolist())
Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
