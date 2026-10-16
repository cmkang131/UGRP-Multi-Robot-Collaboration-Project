"""gcp2 compile/put_model audit; physics steps zero, no controller inputs."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    if host['instance']!='ugrp-act-l4-gcp2':raise ValueError('L4 required')
    import numpy as np
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from simalt_compiled_compat import apply_reference
    m=mujoco.MjModel.from_xml_path(str(a.fixture/'scene.xml'))
    record=apply_reference(m,a.fixture/'scene.xml',a.reference)
    wp.init()
    wm=mjw.put_model(m)
    actual=wm.actuator_biasprm.numpy()[0]
    np.testing.assert_array_equal(actual,m.actuator_biasprm.astype(np.float32))
    result={'host':host,'mujoco':mujoco.__version__,'physics_steps':0,
        'put_model_exact_float32':True,'compatibility':record,
        'C_compiled_sha256':hashlib.sha256(m.actuator_biasprm.tobytes()).hexdigest(),
        'Warp_import_sha256':hashlib.sha256(actual.tobytes()).hexdigest(),
        'C_bias_velocity':m.actuator_biasprm[:,2].tolist(),
        'Warp_bias_velocity':actual[:,2].tolist(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with a.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print('put_model_exact_float32=True physics_steps=0')


if __name__=='__main__':main()
