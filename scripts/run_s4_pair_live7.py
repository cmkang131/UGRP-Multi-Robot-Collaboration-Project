"""v170: frozen S3 v165 / S4 v168, all-phase heartbeat and evaluation-only COM guard toggles."""
import argparse
import json
import os
from pathlib import Path
from scripts import run_s4_pair_live5_r3 as previous
from scripts import run_s4_pair_live5_r2 as base
from harness import s4_pair_handshake as hs
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT = base.ROOT
RECORD = 'experiments/2026-10-06-s4-llm/s4live7'
PLAN = RECORD+'/README.md'
BUNDLE_ID = 'zone-s4-pair-live-v170'
VERSION = '7.63.0'
WORKFLOW = 'configs/simulation_workflows.d/s4_pair_live_v170.json'


def bundle(source_sha, condition, renewal='off', drop_guard='off'):
    if drop_guard not in ('off', 'contact_com_v1'):
        raise ValueError('unknown beam evaluation guard')
    if renewal not in ('off', hs.PHASE_HEARTBEAT):
        raise ValueError('unknown carry lease renewal')
    b = previous.bundle(source_sha, condition)
    b.update(schema='ugrp.s4_pair_live.v170', execution_bundle_id=BUNDLE_ID,
        workflow_version=VERSION, carry_lease_renewal=renewal, pair_drop_guard=drop_guard, concurrent_limit=8,
        stage_scope='claim-GO/ACK-carry-continuation-registered-goal-lowering DEV')
    paths = set(source_closure(ROOT, ['scripts/run_s4_pair_live7.py', 'sim/s4_pair_live.py', 'sim/s4_beam_drop_guard.py']))
    paths.update((WORKFLOW, PLAN, RECORD+'/plan.json'))
    b['source_sha256'].update({p:base.old.sha(ROOT/p) for p in paths})
    return b


class Extension(base.Extension):
    def __init__(self, out, renewal='off'):
        super().__init__(out)
        self.renewal = renewal
        self.routes = {}

    def components(self):
        return base.old.pair.Link, base.old.pair.Host, {
            'handshake': hs.Handshake(carry_lease_renewal=self.renewal)}

    def record_states(self, runtime, now):
        super().record_states(runtime, now)
        for rid in hs.PAIR:
            ep = runtime.pair.producer.actors[rid]._pair
            if ep is not None and rid not in self.routes:
                # Evaluation provenance, never returned to a policy. This is
                # the actual registered route, not a guessed success radius.
                self.routes[rid] = dict(recorded_t=now, route=ep.controller.v3_plan['route'])
                base.old.live.write(self.out/'pair-route.json', self.routes)


def persistent_output(out):
    # Oracle runner resolves outputs/<job> to persistent runs/<job>. No tmpfs.
    root = (Path.home()/'ugrp-sim/runs').resolve()
    resolved = out.resolve()
    if root not in resolved.parents or any(str(resolved).startswith(p) for p in ('/tmp/', '/dev/shm/')):
        raise ValueError('persistent Oracle runs output required')
    import subprocess
    fs = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '-T', str(out.parent)], text=True).strip()
    if fs in ('tmpfs', 'ramfs'):
        raise ValueError('volatile output filesystem forbidden')


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--condition', choices=base.old.live.stage.CONDITIONS, required=True)
    p.add_argument('--carry-lease-renewal', choices=('off', hs.PHASE_HEARTBEAT), default='off')
    p.add_argument('--relay-receipt', type=Path, required=True)
    p.add_argument('--pair-drop-guard', choices=('off', 'contact_com_v1'), default='off')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, bundle_id=BUNDLE_ID,
            condition=a.condition, seed=601, cap_s=90, carry_lease_renewal=a.carry_lease_renewal, pair_drop_guard=a.pair_drop_guard)))
        return 0
    persistent_output(a.output)
    base.old.live.previous.archive_guard(a.expected_source_sha, a.output)
    if os.environ.get('LP_NUM_THREADS') != '4':
        raise ValueError('LP_NUM_THREADS=4 required')
    base.old.live.write(a.output.parent/'driver.json', dict(pid=os.getpid(), pgid=os.getpgid(0),
        job=a.output.parent.name, source_sha=a.expected_source_sha))
    from sim.s4_pair_live import PhysicsBackend
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        r = bind(base.old.live.run, PLAN=PLAN)(bundle(a.expected_source_sha, a.condition, a.carry_lease_renewal, a.pair_drop_guard),
            a.output, a.relay_receipt, pair_extension=Extension(a.output, a.carry_lease_renewal),
            backend_factory=PhysicsBackend)
        print(json.dumps(r))
        return int(r['status'] == 'HOST_ERROR')
    finally:
        undo()


if __name__ == '__main__':
    raise SystemExit(main())
