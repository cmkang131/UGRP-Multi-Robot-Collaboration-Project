import copy
from scripts.run_active_wall_nav2 import frozen_bundle as previous
from scripts.run_active_wall_rotleft import frozen_bundle


def test_supervised_bundle_only_motion_seed_and_admission_change():
    a,b=previous('new-seed','f'*40),frozen_bundle('new-seed','f'*40)
    assert '5_of_7_UNMET' in b.pop('admission')
    assert b['task']['seed']==32002
    assert b['options']['motion_model']==b['estimator_options']['motion_model']=='s2_pulse_v122_rotL_v1'
    for group,key in [('task','seed'),('options','motion_model'),('estimator_options','motion_model')]:
        b[group][key]=a[group][key]
    for key in ('execution_bundle_id','check'):b[key]=a[key]
    assert a==b
