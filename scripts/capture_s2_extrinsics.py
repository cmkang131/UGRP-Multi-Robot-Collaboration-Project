"""Finite known-target stationary capture. Default is a read-only plan."""
import argparse
import json
from pathlib import Path
from harness import s2_extrinsic_targets as targets


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--states',choices=('all','loaded','unloaded'),default='all')
    p.add_argument('--pose-set',choices=('default','real_carry_v1'),default='default')
    args=p.parse_args(argv)
    if args.pose_set == 'real_carry_v1' and args.states != 'unloaded':
        raise ValueError('real carry extension permits unloaded capture only')
    if not args.execute:
        print(json.dumps(dict(execution_started=False,poses=len(targets.capture_poses(args.pose_set)),images=3*len(targets.capture_poses(args.pose_set)),
            fixture='level chassis clamp + surveyed checkerboard',sim_cap_s=360,model_calls=0)))
        return
    from scripts.run_final_environment_checks import check_source
    from scripts.agent_lock import status,DEFAULT_ROOT
    check_source(args.expected_source_sha)
    lock=status(DEFAULT_ROOT)
    if not lock or not lock['pid_alive'] or lock['owner']!='codex' or lock['branch']!='codex/s2-realism':
        raise ValueError('owned calibration lock required')
    if args.output is None or not args.output.is_absolute():raise ValueError('absolute new output required')
    from sim.s2_extrinsic_capture import capture
    capture(args.output,args.expected_source_sha,states=args.states,pose_set=args.pose_set)


if __name__=='__main__':main()
