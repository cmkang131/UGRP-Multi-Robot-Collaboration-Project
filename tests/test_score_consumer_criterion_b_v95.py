"""v95 B scoring adapter: synthetic fixtures + local-only v88 training data.

The v95 held-out raw is never opened here (autouse guard).
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness import kinematic_overlap as ko
from harness import zone_final_pair_new_starts as v
from scripts import score_consumer_criterion_b_v95 as s
from scripts import validate_consumer_criterion_b as frozen

V88 = Path('/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/'
           'calibration-unloaded/zone_wide_two_doors_final_v3')
T0, START_UNIX = 1.3, 1_800_000_000.0


@pytest.fixture(autouse=True)
def never_open_v95_raw(monkeypatch):
    original = Path.read_bytes
    original_open = Path.open

    def check(path):
        assert 'final-pair-v95-heldout-' not in str(Path(path).resolve()), 'v95 raw must stay closed'

    def read_bytes(self):
        check(self)
        return original(self)

    def open_(self, *a, **kw):
        check(self)
        return original_open(self, *a, **kw)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    monkeypatch.setattr(Path, 'open', open_)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


def host(offset=0.):
    holder = {'owner': 'claude', 'pid': 1, 'acquired_unix': START_UNIX + offset}
    return {'loadavg': [1., 1., 1.], 'concurrent_holders': [dict(holder)], 'physics_holder': dict(holder)}


def simulate(plan, start, n=7400, dt=.05):
    """Toy first-order body-velocity response; only needs to be a valid trajectory."""
    u, _ = frozen.plan_arrays(plan, n, dt)
    x, y, yaw = start
    vel = np.zeros(3)
    rows = []
    for i in range(n + 1):
        c, sn = np.cos(yaw), np.sin(yaw)
        rot = [[c, -sn, 0.], [sn, c, 0.], [0., 0., 1.]]
        rows.append({'t': round(T0 + i*dt, 10), 'sample_index': i, 'base_position_m': [x, y, .03],
                     'base_rotation': rot, 'requested_check': v.CHECK,
                     'wall_clearance_lower_bound_m': .7})
        if i == n:
            break
        vel += (np.array([3., 3., 30.])*u[i] - vel)*.25
        x += (vel[0]*c - vel[1]*sn)*dt
        y += (vel[0]*sn + vel[1]*c)*dt
        yaw += vel[2]*dt
    return rows


def build_map(root, mid, commitment, negate_r2=False):
    case_dir = root / mid
    bundle = {**v.bundle(mid), 'case': v.cases(v.CHECK, mid)[0], 'source_sha': s.SOURCE}
    dump(case_dir / 'bundle.json', bundle)
    events = v.schedule(v.CHECK, mid)
    dump(case_dir / 'inputs/schedule.json', events)
    for rid in v.ROBOTS:
        sign = -1. if (negate_r2 and rid == 'r2') else 1.
        commands = []
        for e in events:
            if e['robot_id'] != rid:
                continue
            action = dict(e['action'])
            if action['kind'] == 'mecanum':
                for k in ('forward', 'left', 'turn'):
                    action[k] = sign*action[k] if action[k] else action[k]
            commands.append({'t': round(T0 + e['t'], 10), **action})
        jsonl(case_dir / f'robots/{rid}/commands.jsonl', commands)
        jsonl(case_dir / f'eval_only/{rid}/pose.jsonl',
              simulate(bundle['measurement_by_robot'][rid], v.STARTS[mid][rid]))
    case_result = {'check': v.CHECK, 'case': bundle['case'], 'status': 'COLLECTED_UNQUALIFIED',
                   'protocol_complete': True, 'physical_success': None, 'check_sim_s': 370.,
                   'reset_sim_s': T0, **v.ROLE, 'host_start': host(5.), 'failure': None}
    dump(case_dir / 'result.json', case_result)
    dump(case_dir / 'artifacts.sha256.json',
         {str(p.relative_to(case_dir)): sha(p.read_bytes()) for p in sorted(case_dir.rglob('*'))
          if p.is_file() and p.name != 'artifacts.sha256.json'})
    plan = {**v.ROLE, 'execution_bundle_id': s.BUNDLE, 'status': 'DRAFT_UNSEALED', 'check': v.CHECK,
            'execution_started': True, 'cases': [bundle['case']], 'denominator': 1, 'runnable': True,
            'blocked_on': [], 'source_sha': s.SOURCE, 'seed': 911,
            'bundles_sha256': [ko.digest(bundle)], 'host_start': host(),
            'started_utc': '2026-10-03T11:13:06+00:00', 'commitment': commitment}
    dump(root / 'plan.json', plan)
    dump(root / 'result.json', {'status': 'COLLECTED_UNQUALIFIED', **v.ROLE, 'cases': [case_result],
                                'unattempted': [], 'denominator': 1, 'host_start': host(),
                                'source_unchanged': True})
    return root


class World:
    """Synthetic precheck + two map collections + mocked #219 comments."""

    def __init__(self, tmp, monkeypatch, *, negate_r2=False):
        self.tmp, self.mp = tmp, monkeypatch
        self.comments = {}
        commitment_ref = {'id': 101, 'created_at': '2026-10-03T11:12:35Z'}
        self.raws = [build_map(tmp / 'raw' / mid, mid, commitment_ref, negate_r2) for mid in v.MAPS]
        motion, bundles, schedules = {}, {}, {}
        for raw, mid in zip(self.raws, v.MAPS):
            case = raw / mid
            b = json.loads((case / 'bundle.json').read_text())
            bundles[mid] = ko.digest({k: x for k, x in b.items() if k not in ('source_sha', 'case')})
            schedules[mid] = sha((case / 'inputs/schedule.json').read_bytes())
            motion[mid] = {'motion': {rid: {'kinematic_sha256': ko.read_trace(
                case / f'eval_only/{rid}/pose.jsonl').sha256} for rid in v.ROBOTS}}
        pre = tmp / 'heldout-v95-precheck-x'
        binding = dump(pre / 'binding.json', {'bundle_sha256': bundles, 'schedule_sha256': schedules,
                                              'frozen_sha256': dict(s.FROZEN_FULL)})
        precheck = dump(pre / 'precheck.json', {
            'schema': 'ugrp.heldout_v95_precheck.v1', 'status': 'PRECHECK_PASS', 'collection': False,
            'rendering': False, 'criterion_B_pass': None, 'maps': motion,
            'binding_sha256': sha(binding.read_bytes())})
        dump(pre / 'SHA256SUMS.json', {'binding.json': sha(binding.read_bytes()),
                                       'precheck.json': sha(precheck.read_bytes())})
        for raw in self.raws:
            p = json.loads((raw / 'plan.json').read_text())
            p['precheck_sha256'] = sha(precheck.read_bytes())
            dump(raw / 'plan.json', p)
        self.precheck = pre
        commit_body = 'V95_PRE_COLLECTION_COMMITMENT ' + ' '.join(
            sha((pre / n).read_bytes()) for n in ('precheck.json', 'binding.json', 'SHA256SUMS.json'))
        gate_body = 'gate ' + ' '.join(sha((raw / mid / n).read_bytes()) for raw, mid in zip(self.raws, v.MAPS)
                                       for n in ('result.json', 'artifacts.sha256.json'))
        self.snap('commitment', 101, commit_body, '2026-10-03T11:12:35Z')
        self.snap('gate', 102, gate_body, '2026-10-03T11:40:41Z')
        own = sha(Path(s.__file__).resolve().read_bytes())
        self.comments[103] = self.comment(103, 'adapter ' + own, '2026-10-03T12:00:00Z')
        far = ko.trace([{'t': i*.05, 'base_position_m': [50.+i*.01, 50., .03],
                         'base_rotation': np.eye(3).tolist()} for i in range(10)], 'far-prior')
        monkeypatch.setattr(s.gate95, 'load_prior', lambda: [far])
        monkeypatch.setattr(s, 'now_utc', lambda: '2026-10-03T13:00:00+00:00')

    @staticmethod
    def comment(cid, body, created):
        return {'id': cid, 'html_url': f'https://github.com/x/issues/219#issuecomment-{cid}',
                'issue_url': 'https://api.github.com' + s.ISSUE_SUFFIX, 'created_at': created,
                'updated_at': created, 'body': body}

    def snap(self, role, cid, body, created):
        value = {**self.comment(cid, body, created), 'body_sha256': sha(body.encode())}
        path = dump(self.tmp / f'{role}_comment.json', value)
        self.comments[cid] = self.comment(cid, body, created)
        snaps = dict(s.SNAPSHOTS)
        snaps[role] = (path, cid, sha(path.read_bytes()))
        self.mp.setattr(s, 'SNAPSHOTS', snaps)

    def recommit(self):
        """Re-bind a mutated precheck so the NEXT link (not the commitment) is tested."""
        pre = self.precheck
        precheck = json.loads((pre / 'precheck.json').read_text())
        precheck['binding_sha256'] = sha((pre / 'binding.json').read_bytes())
        dump(pre / 'precheck.json', precheck)
        dump(pre / 'SHA256SUMS.json', {n: sha((pre / n).read_bytes()) for n in ('binding.json', 'precheck.json')})
        for raw in self.raws:
            plan = json.loads((raw / 'plan.json').read_text())
            plan['precheck_sha256'] = sha((pre / 'precheck.json').read_bytes())
            dump(raw / 'plan.json', plan)
        body = 'V95_PRE_COLLECTION_COMMITMENT ' + ' '.join(
            sha((pre / n).read_bytes()) for n in ('precheck.json', 'binding.json', 'SHA256SUMS.json'))
        self.snap('commitment', 101, body, '2026-10-03T11:12:35Z')

    def fetch(self, cid):
        if cid not in self.comments:
            raise ValueError('unavailable')
        return copy.deepcopy(self.comments[cid])

    def run(self, raws=None):
        return s.validate(raws or self.raws, self.precheck, 103, fetch=self.fetch)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def forbid_scoring(monkeypatch):
    monkeypatch.setattr(frozen, 'evaluate_axis', lambda *a, **k: pytest.fail('scoring reached'))


def test_full_chain_scores_four_cases_per_map_and_robot(world):
    report = world.run()
    assert report['ordering_evidence']['verified'] is True, report.get('eligibility_reason')
    assert report['scope'] == 'HELD_OUT_VALIDATION'
    assert report['validation_kind'] == s.VALIDATION_KIND
    keys = sorted((c['map_id'], c['robot_id']) for c in report['cases'])
    assert keys == sorted((m, r) for m in v.MAPS for r in v.ROBOTS)
    for case in report['cases']:
        assert case['axes']['rotate']['pass'] is None  # r4 rotate stays null
        for name in ('forward', 'left'):
            axis = case['axes'][name]
            assert axis['pass'] in (True, False) and set(axis['split_pass']) == {'steps', 'prbs'}
            assert axis['pass'] == all(axis['split_pass'].values())
    rot = report['rotation_addendum']['cases']
    assert sorted((c['map_id'], c['robot_id']) for c in rot) == keys
    assert all(c['pass'] in (True, False) for c in rot)
    gate = report['ordering_evidence']['kinematic_gate']
    assert gate['status'] == 'DISJOINT' and gate['mutual_pairs'] == 6 and gate['prior_comparisons'] == 4
    assert report['ordering_evidence']['rotation_ordering'] == 'PRE_COLLECTION'
    text = json.dumps(report, ensure_ascii=False)
    assert '새 시작점 검증' in text and '지도 일반화' not in text


def test_r1_loader_equals_frozen_load_case(world):
    folder = world.raws[0] / v.MAPS[0]
    gate = s.loader_gate(frozen.criterion())
    assert s.same_case(s.load_robot(folder, gate, 'r1'), frozen.load_case(folder, gate))


def test_r2_loader_uses_its_own_files_and_plan(world):
    folder = world.raws[0] / v.MAPS[0]
    gate = s.loader_gate(frozen.criterion())
    r1, r2 = (s.load_robot(folder, gate, rid) for rid in ('r1', 'r2'))
    assert r2['pose_sha256'] == sha((folder / 'eval_only/r2/pose.jsonl').read_bytes())
    assert not np.array_equal(r1['u'], r2['u'])  # different axis order / PRBS phase
    expected, _ = frozen.plan_arrays(v.design(v.CHECK, v.MAPS[0], 'r2'), len(r2['pose'])-1, .05)
    assert np.array_equal(r2['u'], expected)


def test_no_r2_sign_flip_negated_commands_rejected(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, negate_r2=True)
    forbid_scoring(monkeypatch)
    report = w.run()
    assert report['pass'] is None and 'issued commands differ' in report['eligibility_reason']
    source = Path(s.__file__).read_text()
    assert 'motion_events' not in source and '-1 if rid' not in source


EXPECTED = {
    'edited_commitment': 'GitHub commitment comment changed', 'other_issue': 'GitHub gate comment changed',
    'gate_missing_hash': 'not in #219 gate record', 'late_commitment': 'commitment is not strictly before',
    'adapter_hash_missing': 'does not list this adapter', 'adapter_after_read': 'adapter comment is not strictly',
    'github_unavailable': 'unavailable', 'bundle_altered': 'raw bundle differs',
    'trace_mismatch': 'trajectory differs from the committed precheck', 'previously_seen': 'PREVIOUSLY_SEEN_KINEMATICS',
    'one_map_only': 'both v95 map collections', 'precheck_hash_missing': 'not in #219 commitment',
    'frozen_hash_missing': 'committed binding lacks frozen hash'}


@pytest.mark.parametrize('fault', ['edited_commitment', 'other_issue', 'gate_missing_hash',
                                   'late_commitment', 'adapter_hash_missing', 'adapter_after_read',
                                   'github_unavailable', 'bundle_altered', 'trace_mismatch',
                                   'previously_seen', 'one_map_only', 'precheck_hash_missing',
                                   'frozen_hash_missing'])
def test_each_provenance_link_fails_closed_before_scoring(world, monkeypatch, fault):
    forbid_scoring(monkeypatch)
    raws = None
    if fault == 'edited_commitment':
        world.comments[101]['updated_at'] = '2026-10-03T12:00:00Z'
    if fault == 'other_issue':
        world.comments[102]['issue_url'] = world.comments[102]['issue_url'].replace('/219', '/218')
    if fault == 'gate_missing_hash':
        world.snap('gate', 102, 'gate without hashes', '2026-10-03T11:40:41Z')
    if fault == 'late_commitment':
        body = world.comments[101]['body']
        world.snap('commitment', 101, body, '2026-10-03T11:14:00Z')
        for raw in world.raws:
            p = json.loads((raw / 'plan.json').read_text())
            p['commitment']['created_at'] = '2026-10-03T11:14:00Z'
            dump(raw / 'plan.json', p)
    if fault == 'adapter_hash_missing':
        world.comments[103]['body'] = 'adapter ' + 'f'*64
    if fault == 'adapter_after_read':
        world.comments[103]['created_at'] = world.comments[103]['updated_at'] = '2999-01-01T00:00:00Z'
    if fault == 'github_unavailable':
        world.comments.pop(102)
    if fault == 'bundle_altered':
        path = world.raws[0] / v.MAPS[0] / 'bundle.json'
        b = json.loads(path.read_text())
        b['start_xy_yaw']['r1'][0] += .5
        dump(path, b)
    if fault == 'trace_mismatch':
        pre = json.loads((world.precheck / 'precheck.json').read_text())
        pre['maps'][v.MAPS[1]]['motion']['r2']['kinematic_sha256'] = '0'*64
        dump(world.precheck / 'precheck.json', pre)
        world.recommit()
    if fault == 'previously_seen':
        own = ko.read_trace(world.raws[1] / v.MAPS[1] / 'eval_only/r2/pose.jsonl')
        monkeypatch.setattr(s.gate95, 'load_prior', lambda: [own])
    if fault == 'one_map_only':
        raws = world.raws[:1]
    if fault == 'precheck_hash_missing':
        world.snap('commitment', 101, 'V95 commitment without hashes', '2026-10-03T11:12:35Z')
    if fault == 'frozen_hash_missing':
        b = json.loads((world.precheck / 'binding.json').read_text())
        b['frozen_sha256'].pop('scripts/validate_consumer_criterion_b.py')
        dump(world.precheck / 'binding.json', b)
        world.recommit()
    report = world.run(raws)
    assert EXPECTED[fault] in report['eligibility_reason']
    assert report['scope'] == 'INELIGIBLE' and report['pass'] is None
    assert report['with_rotation_addendum']['pass'] is None
    assert report['ordering_evidence']['verified'] is False


def test_mutual_overlap_between_new_traces_is_ineligible(world, monkeypatch):
    forbid_scoring(monkeypatch)
    real = ko.overlap
    monkeypatch.setattr(s.ko, 'overlap', lambda a, b, **k: {'status': 'PREVIOUSLY_SEEN'}
                        if 'r1' in a.source and 'r2' in b.source else real(a, b, **k))
    report = world.run()
    assert report['eligibility_reason'] == 'PREVIOUSLY_SEEN_KINEMATICS'


def test_committed_snapshots_match_pins_and_wording():
    for path, cid, expected in s.SNAPSHOTS.values():
        snap = json.loads(path.read_text())
        assert sha(path.read_bytes()) == expected and snap['id'] == cid
        assert snap['created_at'] == snap['updated_at'] and snap['issue_url'].endswith(s.ISSUE_SUFFIX)
    commitment = json.loads(s.SNAPSHOTS['commitment'][0].read_text())['body']
    assert commitment == (s.ROOT / 'experiments/2026-10-03-critb-heldout-v95/COMMITMENT.md').read_text()
    for name, digest in s.FROZEN_FULL.items():
        assert sha((s.ROOT / name).read_bytes()) == digest
    source = Path(s.__file__).read_text()
    assert '새 시작점 검증' in source and '지도 일반화' not in source


def test_registered_in_ci():
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    assert collect_test_files(s.ROOT, TEST_PATTERNS).count('tests/test_score_consumer_criterion_b_v95.py') == 1


@pytest.mark.skipif(not (V88 / 'bundle.json').is_file(), reason='local-only v88 training data')
def test_v88_training_data_r1_and_r2_paths_equal_frozen_loader(tmp_path):
    """Already-seen v88 training case; never validation evidence."""
    gate = frozen.criterion()
    reference = frozen.load_case(V88, gate)
    bundle = json.loads((V88 / 'bundle.json').read_bytes())
    bundle['measurement_by_robot'] = {'r1': bundle['measurement'], 'r2': bundle['measurement']}
    dump(tmp_path / 'bundle.json', bundle)
    (tmp_path / 'result.json').write_bytes((V88 / 'result.json').read_bytes())
    for rid in ('r1', 'r2'):  # r2 slot carries r1's recorded files: identical expected output
        for rel in ('eval_only/r1/pose.jsonl', 'robots/r1/commands.jsonl'):
            dest = tmp_path / rel.replace('r1', rid)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((V88 / rel).read_bytes())
    for rid in ('r1', 'r2'):
        assert s.same_case(s.load_robot(tmp_path, gate, rid), reference)
