"""Explicit clean-start MJWarp diagnostic; old capture defaults stay unchanged."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mapbuild2_capture import run,dump


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('queue','renderer-source','fixture','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mapbuild3-v1',action='store_true');a=p.parse_args()
    if not a.mapbuild3_v1:p.error('default off; explicit --mapbuild3-v1 required')
    try:run(a)
    except BaseException as exc:
        if a.output.is_dir() and not (a.output/'summary.json').exists():
            dump(a.output/'summary.json',dict(status='HOST_ERROR',frames=0,error=dict(category='HOST_ERROR',
                reason=repr(exc),blocked_object='recorder_initialization',minimum_gap_m=None,gap_status='not_measured')))
        raise


if __name__=='__main__':main()
