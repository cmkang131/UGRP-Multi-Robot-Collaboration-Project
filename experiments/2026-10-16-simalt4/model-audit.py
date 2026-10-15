import hashlib,json,sys,pathlib
import numpy as np,mujoco
root=pathlib.Path('/home/ugrp/ugrp-sim/runs/simalt4')
m=mujoco.MjModel.from_xml_path(str(root.parent/'simalt3/fixture/scene.xml'))
keys='body_mass body_inertia body_pos body_quat body_ipos body_iquat geom_type geom_size geom_pos geom_quat geom_friction geom_solref geom_solimp geom_margin geom_gap geom_condim geom_contype geom_conaffinity geom_solmix geom_priority pair_dim pair_friction pair_solref pair_solimp pair_margin pair_gap jnt_pos jnt_axis jnt_type jnt_range jnt_solref jnt_solimp dof_damping dof_armature dof_frictionloss dof_M0 dof_invweight0 actuator_gainprm actuator_biasprm actuator_gear actuator_forcerange actuator_ctrlrange actuator_lengthrange qpos0'.split()
values={k:np.asarray(getattr(m,k)).copy() for k in keys if hasattr(m,k)}
np.savez_compressed(root/f'model-{mujoco.__version__}.npz',**values)
report={'version':mujoco.__version__,'source_XML_sha256':hashlib.sha256((root.parent/'simalt3/fixture/scene.xml').read_bytes()).hexdigest(),'arrays':{k:{'shape':v.shape,'dtype':str(v.dtype),'sha256':hashlib.sha256(v.tobytes()).hexdigest()} for k,v in values.items()},'actuators':[m.actuator(i).name for i in range(m.nu)],'bias_velocity':m.actuator_biasprm[:,2].tolist(),'options':{k:float(getattr(m.opt,k)) for k in ('timestep','iterations','ls_iterations','tolerance','noslip_iterations','noslip_tolerance','solver','integrator','cone','impratio','ccd_iterations','ccd_tolerance')}}
(root/f'model-{mujoco.__version__}.json').write_text(json.dumps(report,indent=2)+'\n')
