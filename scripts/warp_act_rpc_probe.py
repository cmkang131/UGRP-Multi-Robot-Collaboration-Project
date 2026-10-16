"""Finite paired test through the actual one-owner-per-process public API."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import traceback

from warp_act_rpc import Client


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for key in ('qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled: p.error('probe default OFF')
    import platform
    if platform.system() != 'Linux': p.error('Linux gcp2 only')
    import numpy as np
    a.out.mkdir(parents=True, exist_ok=False)
    clients = []
    report = dict(status='running', passed=False, scope='API boundary/isolation, not task success')
    def state(client):
        with np.load(client.out/'owner/state-latest.npz') as z:
            return {k: z[k].copy() for k in z.files}
    def same(x, y, world=None):
        return {k: bool(np.array_equal(v if world is None else v[world], y[k] if world is None else y[k][world])) for k, v in x.items()}
    def drift(x, y, world=None):
        result = {}
        for k, value in x.items():
            u, v = (value, y[k]) if world is None else (value[world], y[k][world])
            diff = np.abs(np.asarray(u, dtype=float)-np.asarray(v, dtype=float))
            result[k] = dict(different=int(np.count_nonzero(u != v)), max_abs=float(diff.max()) if diff.size else 0.)
        return result
    def hold(client, done=None):
        actions = []
        for i in range(client.nworld):
            obs, _ = client.read_actor(i)
            actions.append(dict(command=dict(obs['issued'][-1], t=obs['t'], wheels=[0.]*4, duration_s=[0.]*4), done=i==done))
        return actions
    try:
        plans = json.loads(a.plans.read_text())['episodes']
        options = {k: getattr(a, k) for k in ('qualified_source','teacher_source','qualification','references','compiled_reference','compiled_geometry')}
        for name in ('A', 'B'):
            client = Client(python=sys.executable, out=a.out/name, nworld=len(plans), enabled=True, audit_state=True, **options)
            clients.append(client); client.reset(plans)
        A, B = clients
        for client in clients: client.step(hold(client))
        baseline = same(state(A), state(B)); report['baseline_next_step_equal'] = baseline
        report['baseline_next_step_drift'] = drift(state(A), state(B))
        (a.out/'baseline-audit.json').write_text(json.dumps(report, indent=2)+'\n')
        before = state(A); other = A.read_actor(1)
        fresh = deepcopy(plans[0]); fresh['spawns']['r1'] = deepcopy(plans[1]['spawns']['r1']); fresh['episode_id'] += '-rpc-reset'
        A.reset([fresh], [0])
        if np.array_equal(before['qpos'][0], state(A)['qpos'][0]): raise RuntimeError('no fresh start')
        immediate = same(before, state(A), 1); report['untouched_reset_equal'] = immediate
        if not all(immediate.values()) or other != A.read_actor(1): raise RuntimeError('reset changed untouched world/history')
        for client in clients: client.step(hold(client))
        next_equal = same(state(A), state(B), 1); report['untouched_next_step_equal'] = next_equal
        report['untouched_next_step_drift'] = drift(state(A), state(B), 1)
        report['deterministic_next_step_verified'] = all(baseline.values()) and all(next_equal.values())
        before = state(A); observations = [A.read_actor(i) for i in range(A.nworld)]
        try: A.reset([fresh, {**plans[1], 'kind':'unsupported'}], [0,1])
        except ValueError: pass
        else: raise RuntimeError('invalid reset accepted')
        atomic = all(same(before, state(A)).values()) and observations == [A.read_actor(i) for i in range(A.nworld)]
        if not atomic: raise RuntimeError('invalid reset partially mutated owner')
        A.step(hold(A, 0)); frozen = state(A); obs0 = A.read_actor(0)
        ports = json.loads((A.out/'owner/ports-latest.json').read_text())[0]
        A.step(hold(A)); paused = same(frozen, state(A), 0)
        public = obs0 == A.read_actor(0)
        port_equal = ports == json.loads((A.out/'owner/ports-latest.json').read_text())[0]
        if not all(paused.values()) or not public or not port_equal: raise RuntimeError('terminal world advanced')
        # Public reset's shared contact counter has a world0 special case in
        # the installed implementation: exercise a NONZERO world explicitly.
        frozen = state(A); obs0 = A.read_actor(0)
        other_fresh = deepcopy(plans[1]); other_fresh['spawns']['r1'] = deepcopy(plans[0]['spawns']['r1'])
        other_fresh['episode_id'] += '-nonzero-reset'
        A.reset([other_fresh], [1])
        nonzero = same(frozen, state(A), 0)
        if not all(nonzero.values()) or obs0 != A.read_actor(0): raise RuntimeError('nonzero reset changed terminal world')
        A.step(hold(A))
        after_nonzero = same(frozen, state(A), 0)
        if not all(after_nonzero.values()) or obs0 != A.read_actor(0): raise RuntimeError('nonzero reset/step resumed terminal world')
        try: A.read_training(0)
        except RuntimeError: pass
        else: raise RuntimeError('privileged evaluation lane exposed')
        # An extra state key is rejected at the wire before histories/physics.
        bad = hold(A); bad[1]['qpos'] = [12345]
        try: A.step(bad)
        except ValueError: pass
        else: raise RuntimeError('privileged action canary accepted')
        report.update(status='complete', passed=True, invalid_reset_atomic=atomic,
            terminal_state_equal=paused, terminal_history_clock_frozen=public, terminal_port_frozen=port_equal,
            nonzero_reset_untouched_equal=nonzero, nonzero_reset_next_step_paused_equal=after_nonzero,
            training_read_rejected=True, privileged_canary_rejected=True)
        report['scope'] = 'exact immediate persistent reset isolation and terminal freeze; next-step numerical drift reported against nondeterministic independent baseline, no bitwise trajectory guarantee or new physics tolerance'
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error), traceback=traceback.format_exc()); raise
    finally:
        for client in clients:
            try: client.close()
            except BaseException as error: report.update(status='HOST_ERROR', close_error=repr(error), passed=False)
        (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
