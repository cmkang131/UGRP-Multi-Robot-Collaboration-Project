import numpy as np
from scripts.e2e_stage_pose_eval import align


def test_same_rigid_transform_applies_to_position_and_heading():
    t=np.linspace(0,3,31);a=np.c_[t,np.sin(t),t*.2]
    yaw=.7;r=np.array([[np.cos(yaw),-np.sin(yaw)],[np.sin(yaw),np.cos(yaw)]])
    b=np.c_[a[:,:2]@r.T+[2.,-3.],a[:,2]+yaw]
    m=align(a,b)
    assert m['xy_median_m']<1e-12 and m['yaw_median_deg']<1e-10
    b[:,2]+=.3
    assert abs(align(a,b)['yaw_median_deg']-np.degrees(.3))<1e-9


def test_checkpoint_clock_offset_changes_which_trajectory_samples_match():
    cutoff=52.3;physical_start=1.3;elapsed=np.linspace(0,30,301)
    own_t=elapsed+cutoff;gt_t=elapsed+physical_start
    corrected=own_t-cutoff+physical_start
    assert np.allclose(corrected,gt_t)
    # The previous script would clamp every observation beyond the physical end.
    assert np.all(np.searchsorted(gt_t,own_t)==len(gt_t))
