"""ACT16 private score owner. Public RPC remains own RGB/issued commands only."""
import argparse
import base64
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from act16w_runtime import require_gcp2, frozen_source
sys.path.insert(0, '/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from warp_act_api import Owner
from act16w_instance_metrics import InstanceMetrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--enabled', action='store_true')
    for key in ('qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('evaluation owner default OFF')
    require_gcp2(training=True)
    source = frozen_source(Path(__file__).resolve().parents[1])
    protocol, owner, metrics, reason = sys.stdout, None, None, 'owner_eof'

    def frames():
        values = []
        for i in range(owner.n):
            observation, images = owner.read_actor(i)
            values.append(dict(observation=observation,
                jpegs=[base64.b64encode(image).decode() for image in images]))
        return dict(frames=values, terminal=(~owner.active).tolist())

    try:
        with redirect_stdout(sys.stderr):
            owner = Owner(json.loads(args.plans.read_text())['episodes'], args.out,
                qualified_source=args.qualified_source, teacher_source=args.teacher_source,
                qualification=args.qualification, references=json.loads(args.references.read_text()),
                compiled_reference=args.compiled_reference, compiled_geometry=args.compiled_geometry,
                enabled=True, training=False)
            metrics = InstanceMetrics(owner)
            owner.write('instance-evaluation-source.json', dict(source_sha=source,
                qualified_owner='0362037280c6cbc4677f70366db43b9892b23690', privileged_actor_inputs=0))
        print(json.dumps(frames()), file=protocol, flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if set(request) == {'close'}:
                reason = str(request['close']); break
            with redirect_stdout(sys.stderr):
                if set(request) == {'actions'}:
                    active = owner.active.copy()
                    owner.step(request['actions']); metrics.sample(active)
                elif set(request) == {'instruct', 'skill'}:
                    owner.instruct(request['instruct'], request['skill'])
                else:
                    raise ValueError('evaluation RPC whitelist; no training or privileged response')
            print(json.dumps(frames(), allow_nan=False), file=protocol, flush=True)
    except BaseException as error:
        reason = 'HOST_ERROR'
        if owner is not None:
            owner.write('HOST_ERROR.json', dict(reason=repr(error), traceback=traceback.format_exc()))
        raise
    finally:
        with redirect_stdout(sys.stderr):
            if metrics is not None:
                metrics.close()
            if owner is not None:
                owner.close(reason)


if __name__ == '__main__':
    main()
