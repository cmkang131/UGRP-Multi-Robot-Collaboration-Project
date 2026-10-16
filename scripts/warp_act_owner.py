"""Default-off JSON owner process. Simulator objects never cross stdout."""
import argparse
import base64
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from warp_act_api import Owner


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true'); p.add_argument('--training', action='store_true')
    p.add_argument('--audit-state', action='store_true', help='private probe files; never actor response')
    for key in ('qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled: p.error('owner is default OFF')
    protocol = sys.stdout
    owner = None
    def reply():
        frames = []
        for i in range(owner.n):
            obs, jpegs = owner.read_actor(i)
            frames.append(dict(observation=obs, jpegs=[base64.b64encode(j).decode() for j in jpegs]))
        return dict(frames=frames, terminal=(~owner.active).tolist())
    try:
        with redirect_stdout(sys.stderr):
            owner = Owner(json.loads(a.plans.read_text())['episodes'], a.out,
                qualified_source=a.qualified_source, teacher_source=a.teacher_source,
                qualification=a.qualification, references=json.loads(a.references.read_text()),
                compiled_reference=a.compiled_reference, compiled_geometry=a.compiled_geometry,
                enabled=True, training=a.training, audit_state=a.audit_state)
        print(json.dumps(reply(), allow_nan=False), file=protocol, flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if set(request) == {'close'}: break
            try:
                with redirect_stdout(sys.stderr):
                    if set(request) == {'actions'}: owner.step(request['actions']); response = reply()
                    elif set(request) == {'reset', 'indices'}: owner.reset(request['reset'], request['indices']); response = reply()
                    elif set(request) == {'instruct', 'skill'}: owner.instruct(request['instruct'], request['skill']); response = reply()
                    elif set(request) == {'read_training'}:
                        if not owner.training: raise ValueError('privileged lane disabled')
                        response = {'training': owner.read_training(request['read_training'])}
                    else: raise ValueError('owner request whitelist mismatch')
                print(json.dumps(response, allow_nan=False), file=protocol, flush=True)
            except ValueError as error:
                print(json.dumps(dict(error_type=type(error).__name__, error=str(error))), file=protocol, flush=True)
    except BaseException as error:
        if a.out.exists():
            (a.out/'HOST_ERROR.json').write_text(json.dumps(dict(status='HOST_ERROR',
                category='owner_failure', reason=repr(error), traceback=traceback.format_exc()), indent=2)+'\n')
        raise
    finally:
        if owner is not None:
            with redirect_stdout(sys.stderr): owner.close()


if __name__ == '__main__': main()
