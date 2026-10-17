"""Default-off cadence-only ACT evaluation; original policy inputs unchanged.

ACT temporal ensemble coefficient .01 is taken verbatim from Zhao's public
imitate_episodes.py. Replan1 is the no-ensemble receding-horizon ablation.
This wrapper uses the original validated ChunkExecutor; it adds no motion guard.
"""
import argparse
import json
from pathlib import Path
import runpy
import sys

MODES = ('off', 'replan1', 'ensemble1')


def executor_options(mode):
    if mode not in MODES:
        raise ValueError('unknown cadence candidate')
    return {'n_action_steps':8,'temporal_ensemble_coeff':None} if mode=='off' else {
        'n_action_steps':1,'temporal_ensemble_coeff':.01 if mode=='ensemble1' else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--act17-cadence-v1', choices=MODES, default='off')
    args, rest = parser.parse_known_args()
    options = executor_options(args.act17_cadence_v1)
    source = Path(rest[rest.index('--actor-source')+1])
    output = Path(rest[rest.index('--out')+1])
    sys.path.insert(0,str(source))
    from harness import grasp_act_policy
    original = grasp_act_policy.ChunkExecutor
    class CadenceExecutor(original):
        def __init__(self,predict):
            super().__init__(predict,**options)
    grasp_act_policy.ChunkExecutor = CadenceExecutor
    target = Path(__file__).with_name('evaluate_act16w.py')
    sys.argv = [str(target),*rest]
    try:
        runpy.run_path(str(target),run_name='__main__')
    finally:
        grasp_act_policy.ChunkExecutor = original
        if output.exists():
            report=dict(act17_cadence_v1=args.act17_cadence_v1,**options,
                coefficient_source='https://github.com/tonyzhaozh/act/blob/main/imitate_episodes.py#L235',
                policy_inputs_unchanged=True,handwritten_nearfield_fallback=False,
                scope='cadence config receipt; task/physics success is in original summary.json')
            with (output/'act17-cadence.json').open('x') as stream:
                json.dump(report,stream,indent=2)


if __name__=='__main__':
    main()
