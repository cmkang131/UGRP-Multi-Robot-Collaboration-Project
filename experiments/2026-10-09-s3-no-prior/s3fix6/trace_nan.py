"""Trace first invalid floating arithmetic on archived own-input replay only."""
import importlib.util
from pathlib import Path
import numpy as np
from harness.zone_final_pair_binding import bind
from harness.zone_s3_motion_runtime import Runtime as Original
ROOT=Path(__file__).resolve().parents[3]
source=Path(__file__).parents[1]/'s3fix5/recover_smoke.py'
spec=importlib.util.spec_from_file_location('nan_replay',source)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def Runtime(*a,**kw):
    result=Original(*a,**kw)
    # Invalid and divide-by-zero stop at the first producing operation;
    # normal low-weight exponential underflow remains permitted.
    np.seterr(invalid='raise',divide='raise',over='raise',under='ignore')
    return result

if __name__=='__main__':
    bind(m.replay,Runtime=Runtime)(Path('/Users/changmin/projects/ugrp/outputs/s3-odometry-4c9eb3aa-s14201-v150'),
        Path('/Users/changmin/projects/ugrp/outputs/s3fix6-20261010/first-invalid'),False,measure=False)
