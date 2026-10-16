"""Finite Linux GPU reset/pause contract probe, never a student success gate."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import traceback

from warp_act_api import Owner, QUALIFIED


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for key in ('qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled: p.error('probe is default OFF')
    a.out.mkdir(parents=True, exist_ok=False)
    owners = []
    report = dict(status='running', passed=False, controller_source=QUALIFIED,
                  scope='API wiring/isolation; no independent teacher or full student success counted')
    try:
        plans = json.loads(a.plans.read_text())['episodes']
        options = dict(qualified_source=a.qualified_source, teacher_source=a.teacher_source,
            qualification=a.qualification, references=json.loads(a.references.read_text()),
            compiled_reference=a.compiled_reference, compiled_geometry=a.compiled_geometry, enabled=True)
        A = Owner(plans, a.out/'A', **options); owners.append(A)
        B = Owner(plans, a.out/'B', **options); owners.append(B)
        np = A.np
        before_a, before_b = A.integration(), B.integration()
        report['initial_integration_equal'] = {k: bool(np.array_equal(v, before_b[k])) for k, v in before_a.items()}
        np.savez_compressed(a.out/'initial-A.npz', **before_a)
        np.savez_compressed(a.out/'initial-B.npz', **before_b)
        report['initial_issued'] = [A.previous, B.previous]
        import dataclasses
        def arrays(obj, prefix=''):
            result = {}
            for field in dataclasses.fields(obj):
                value = getattr(obj, field.name); name = prefix+field.name
                if dataclasses.is_dataclass(value): result.update(arrays(value, name+'.'))
                elif hasattr(value, 'numpy'): result[name] = value.numpy()
            return result
        ma, mb = arrays(A.hooks.wm), arrays(B.hooks.wm)
        report['initial_model_array_differences'] = [k for k, v in ma.items() if not np.array_equal(v, mb[k])]
        (a.out/'initial-audit.json').write_text(json.dumps(report, indent=2)+'\n')
        # Fork the COMPLETE GPU data workspace, rather than two independent
        # allocations of upstream wp.empty compact-solver scratch (io.py1819).
        # This changes only the test's baseline, never actor/teacher physics.
        def copy_workspace(source, target):
            copied = []
            for field in dataclasses.fields(source):
                x, y = getattr(source, field.name), getattr(target, field.name)
                if dataclasses.is_dataclass(x): copied += [field.name+'.'+k for k in copy_workspace(x, y)]
                elif hasattr(x, 'numpy'):
                    if x.shape != y.shape or x.dtype != y.dtype: raise RuntimeError('paired workspace layout differs')
                    if x.size: A.hooks.wp.copy(y, x)
                    copied.append(field.name)
            return copied
        report['forked_workspace_fields'] = copy_workspace(A.hooks.wd, B.hooks.wd)
        A.hooks.wp.synchronize()
        def hold(owner, done=None):
            return [dict(command=dict(owner.previous[i], t=owner.origin+owner.tick*.1,
                wheels=[0.]*4, duration_s=[0.]*4), done=bool(done is not None and i == done)) for i in range(owner.n)]
        for owner in owners: owner.step(hold(owner))
        initial_equal = {k: bool(np.array_equal(v, B.integration()[k])) for k, v in A.integration().items()}
        report['baseline_next_step_equal'] = initial_equal
        np.savez_compressed(a.out/'step-A.npz', **A.integration())
        np.savez_compressed(a.out/'step-B.npz', **B.integration())
        if not all(initial_equal.values()): raise RuntimeError('paired identical baselines differ before reset')
        previous = A.integration(); other_obs = A.read_actor(1)
        fresh = deepcopy(plans[0])
        # Existing distinct-start manifest supplies the diagnostic perturbation;
        # no new acceptance tolerance or artificial marker is introduced.
        fresh['spawns']['r1'] = deepcopy(plans[1]['spawns']['r1'])
        fresh['episode_id'] += '-api-reset'
        A.reset([fresh], [0])
        if np.array_equal(previous['qpos'][0], A.integration()['qpos'][0]): raise RuntimeError('reset did not create a new start')
        if other_obs != A.read_actor(1): raise RuntimeError('reset advanced untouched actor history')
        for owner in owners: owner.step(hold(owner))
        next_equal = {k: bool(np.array_equal(v[1], B.integration()[k][1])) for k, v in A.integration().items()}
        report['untouched_next_step_equal'] = next_equal
        if not all(next_equal.values()): raise RuntimeError('reset changed untouched next-step dynamics')
        before = A.integration(); before_obs = [A.read_actor(i) for i in range(A.n)]
        invalid = [deepcopy(fresh), {**plans[1], 'kind': 'unsupported'}]
        try: A.reset(invalid, [0, 1])
        except ValueError: pass
        else: raise RuntimeError('invalid reset accepted')
        atomic = all(np.array_equal(v, A.integration()[k]) for k, v in before.items()) and before_obs == [A.read_actor(i) for i in range(A.n)]
        if not atomic: raise RuntimeError('invalid reset partially changed a world')
        A.step(hold(A, done=0))
        frozen = A.integration(); obs0 = A.read_actor(0); relay = A.hooks.relay_state[0].copy()
        ports = deepcopy({k: v for k, v in vars(A.contexts[0]['port']).items() if k.startswith('_') and not hasattr(v, 'model')})
        A.step(hold(A))
        paused = {k: bool(np.array_equal(v[0], A.integration()[k][0])) for k, v in frozen.items()}
        public_frozen = obs0 == A.read_actor(0) and bool(np.array_equal(relay, A.hooks.relay_state[0]))
        ports_frozen = all(ports[k] == getattr(A.contexts[0]['port'], k) for k in ports)
        if not all(paused.values()) or not public_frozen or not ports_frozen: raise RuntimeError('terminal world advanced')
        obs, jpgs = A.read_actor(1)
        canary = deepcopy(obs); canary['qpos'] = [123456]
        try: A.c.validate_observation(canary)
        except ValueError: pass
        else: raise RuntimeError('privileged canary accepted')
        try: A.read_training(1)
        except RuntimeError: pass
        else: raise RuntimeError('privileged evaluation lane accepted')
        report.update(status='complete', passed=True, initial_pair_equal=initial_equal,
            invalid_reset_atomic=atomic, terminal_integration_equal=paused, terminal_history_clock_frozen=public_frozen,
            terminal_port_frozen=ports_frozen, canary_rejected=True, privileged_evaluation_read_rejected=True,
            native_camera=A.hooks.camera, generations=A.generations,
            own_rgb_sha256=[hashlib.sha256(A.read_actor(i)[1][-1]).hexdigest() for i in range(A.n)])
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        for owner in owners: owner.close()
        (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
