"""418-view coarse-start-prior adapter; every stream needs an operator region.

No prior may be selected/rounded from eval-only states or exact spawn.
Prediction and scoring remain separate processes in mapbuild9_sparse.
"""
import argparse
from pathlib import Path
import platform
from mapbuild9_sparse import predict, score


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['predict','score'],required=True)
    for name in ('input','owner','output','calibration','requirements','queue','stack-check','initial-prior'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp3'):raise ValueError('GCP3_ONLY')
    (predict if a.stage=='predict' else score)(a)
