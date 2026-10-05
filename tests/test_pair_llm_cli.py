"""CLI routing/clock provenance only: no physics, rendering or network."""
import json
from types import SimpleNamespace

import pytest

from harness import pair_llm_case, pair_llm_live
from scripts import run_pair_llm as cli
from scripts import agent_sim_slots
from sim import final_pair_highpose_clock as clock
from tests.pair_llm_fakes import FakeBackend, FakeRuntime, offline_only, run_arm  # noqa: F401


@pytest.mark.parametrize('condition,live', [('rule', False), ('no_comm', False), ('peer_nl', False),
                                            ('no_comm', True), ('peer_nl', True)])
@pytest.mark.parametrize('dev', [False, True, 'loaded_rest_v104'])
def test_cli_routes_every_arm_to_integer_clock_and_records_it(tmp_path, monkeypatch, condition, live, dev):
    primary = tmp_path / 'primary'
    out = primary / 'outputs' / 'case'
    monkeypatch.setattr(cli, 'primary_checkout', lambda: primary)
    monkeypatch.setattr(cli, 'check_source', lambda sha: None)
    monkeypatch.setattr(cli.shutil, 'disk_usage', lambda path: SimpleNamespace(free=20 * 1024**3))
    monkeypatch.setattr(agent_sim_slots, 'require_sim_slot', lambda *a, **k: {'test': True})
    if live:
        monkeypatch.setattr(cli, 'cohort_budget', lambda *a: SimpleNamespace(usage=lambda cohort: {}))
    seen = []

    def result_for(kwargs):
        seen.append(kwargs['backend_factory'])
        assert kwargs['backend_factory'] is clock.PhysicsBackend
        if dev:
            assert kwargs['calibration'] == cal and kwargs['calibration_sha'] == cal_sha
            assert kwargs['provider_factory'] is None
        if live:
            assert kwargs['admission_mode'] == ('DEV_PILOT' if dev else 'MEASURED_SIM')
        return {'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True,
                'metrics': {'success': True}, 'host_clock': clock.record()}

    monkeypatch.setattr(pair_llm_case, 'run_pair_case', lambda *a, **k: result_for(k))
    monkeypatch.setattr(pair_llm_live, 'run_pair_live', lambda *a, **k: (result_for(k), []))
    argv = ['--condition', condition, '--expected-source-sha', 'a'*40, '--output', str(out),
            '--synthetic-plumbing-calibration', '--sim-slot', 'sim-test-clock', '--lock-owner', 'codex', '--execute']
    if dev:
        from tests.test_highpose_dev_pilot import dev_file, admit
        from harness import zone_pair_highpose_contract as high
        if dev == 'loaded_rest_v104':
            from tests.test_highpose_dev_pilot import V104_PATH, V104_SHA
            cal, cal_sha = V104_PATH, V104_SHA
            assert high.base.sha(cal) == cal_sha
        else:
            cal, _ = dev_file(tmp_path)
            cal_sha = high.base.sha(cal)
            admit(monkeypatch, cal_sha)
        argv.remove('--synthetic-plumbing-calibration')
        argv += ['--admission', 'dev-pilot', '--calibration', str(cal), '--calibration-sha256', cal_sha]
    if live:
        argv += ['--live', '--proxy-pid', '1', '--budget-db', str(primary/'outputs'/'budget.sqlite'),
                 '--create-budget', '--cohort-id', 'DEV-test-clock', '--cohort-token-cap', '1100000']
    if condition == 'rule':
        argv += ['--budget-db', str(primary/'outputs'/'budget.sqlite'), '--create-budget',
                 '--cohort-id', 'DEV-test-clock', '--cohort-token-cap', '1100000']
    assert cli.main(argv) == 0
    if condition == 'rule':
        completion = json.loads((out/'admission_completion.json').read_text())
        assert completion['status'] == 'completed' and completion['rule_success'] is True
    assert seen == [clock.PhysicsBackend]
    from sim.final_pair_highpose_nearclip import NearClip   # floor_light_nearclip_v1 render profile (v105)
    assert clock.PhysicsBackend.__mro__[1] is NearClip and clock.PhysicsBackend.__mro__[2] is clock.IntegerClock
    from sim.final_pair_v3 import PhysicsBackend as V3Backend
    assert clock.PhysicsBackend.__bases__ == (NearClip, clock.IntegerClock, V3Backend)  # no acceleration wrapper
    for filename in ('plan.json', 'result.json'):
        row = json.loads((out/filename).read_text())
        assert row['host_clock'] == clock.record()
        assert row['admission_mode'] == ('DEV_PILOT' if dev else 'MEASURED_SIM')
        if dev:
            assert row['run_status'] == 'FUNCTIONAL_DEV' and row['promotable'] is False
            assert row['confirmation_sample'] is False and row['measured_sim_evidence'] is False


@pytest.mark.parametrize('condition', ['rule', 'no_comm', 'peer_nl'])
def test_v103_loaded_calibration_reaches_both_runtime_providers_without_overrides(condition):
    """Construct the actual controller/PF only; do not step, render, or request a model."""
    from harness import pair_llm_contract as contract
    from harness import zone_pair_highpose_contract as high
    from harness.pair_llm_runtime import GatedHighRuntime
    from harness.zone_pair_highpose_runtime import Runtime
    from tests.test_highpose_dev_pilot import V104_PATH, V104_SHA
    bundle = contract.bundle(condition, admission_mode=high.DEV_PILOT,
                             calibration={'path': V104_PATH, 'sha256': V104_SHA})
    expected = high.student_calibration(high.calibration_for(high.DEV_PILOT, V104_PATH, V104_SHA, bundle['map_id']))
    static = high.resolve(bundle['map_id'])[0]
    runtime = (Runtime if condition == 'rule' else GatedHighRuntime)(static, V104_PATH, V104_SHA, seed=911)
    try:
        for port in runtime.providers.values():
            provider = port.provider
            assert provider.runtime_contract['calibration_sha256'] == V104_SHA
            assert provider.calibration['params'] == expected['params']
            assert provider.loc.params['motion_loaded'] == expected['params']['motion_loaded']
            assert provider.loc.params['motion_loaded']['rest_noise'] is False
            assert all(v > 0 for v in provider.loc.params['motion_loaded']['deadband']['u0'][:2])
        assert bundle['timing'] == contract.physics_bundle(admission_mode=high.DEV_PILOT)['timing']
        assert bundle['shared_top_camera'] is False and bundle['weld'] == 'off'
    finally:
        runtime.close()


@pytest.mark.parametrize('clock_id', [None, clock.ID])
def test_case_records_actual_backend_clock_even_on_host_error(tmp_path, clock_id):
    class Broken(FakeBackend):
        host_clock = clock_id
        def reset(self, cap):
            raise RuntimeError('test reset failure before any step')

    result, out, _ = run_arm(tmp_path, 'rule', backend=Broken, runtime_factory=FakeRuntime, cap_s=1.)
    expected = None if clock_id is None else clock.record()
    assert result['status'] == 'HOST_ERROR'
    assert result['host_clock'] == expected
    assert json.loads((out/'result.json').read_text())['host_clock'] == expected


def test_dev_case_uses_same_admission_and_keeps_nonpromotable_labels(tmp_path, monkeypatch):
    from harness import pair_llm_contract as contract
    from harness import zone_pair_highpose_contract as high
    from tests.test_highpose_dev_pilot import dev_file, admit
    cal, _ = dev_file(tmp_path)
    digest = high.base.sha(cal)
    admit(monkeypatch, digest)
    bundle = contract.bundle('rule', admission_mode=high.DEV_PILOT,
                             calibration={'path': cal, 'sha256': digest})
    kwargs = dict(condition='rule', seed=911, backend_factory=FakeBackend,
                  calibration=cal, calibration_sha=digest, runtime_factory=FakeRuntime, cap_s=.1)
    out = tmp_path/'dev-case'
    result = pair_llm_case.run_pair_case(bundle, out, **kwargs)
    assert result['status'] == 'COLLECTED_UNQUALIFIED'
    for filename in ('bundle.json', 'result.json'):
        row = json.loads((out/filename).read_text())
        for key, value in high.DEV_PILOT_LABELS.items():
            assert row[key] == value
        with pytest.raises(ValueError, match=high.NOT_PROMOTABLE):
            high.require_promotable(row)
    expected = contract.physics_bundle(admission_mode=high.DEV_PILOT)
    expected['case']['sim_cap_s'] = .1
    assert result['physics_bundle_sha256'] == high.base.digest(expected)
    refused = tmp_path/'refused'
    with pytest.raises(ValueError, match='not admitted'):
        pair_llm_case.run_pair_case(bundle, refused, **{**kwargs, 'calibration_sha': '0'*64})
    assert not refused.exists()
    with pytest.raises(ValueError):
        pair_llm_case.run_pair_case(bundle, refused, **{**kwargs, 'seed': 912})
    assert not refused.exists()
    with pytest.raises(ValueError, match='not synthetic plumbing'):
        contract.bundle('rule', admission_mode=high.DEV_PILOT, synthetic_calibration=True)


def test_cli_measured_default_still_refuses_dev_file_before_start(tmp_path, monkeypatch):
    from harness import zone_pair_highpose_contract as high
    from tests.test_highpose_dev_pilot import dev_file, admit
    cal, _ = dev_file(tmp_path)
    sha = high.base.sha(cal)
    admit(monkeypatch, sha)
    out = tmp_path/'never-created'
    argv = ['--condition', 'rule', '--seed', '911', '--expected-source-sha', 'a'*40,
            '--output', str(out), '--calibration', str(cal), '--calibration-sha256', sha, '--execute']
    monkeypatch.setattr(cli, 'check_source', lambda *a: pytest.fail('source check reached after bad calibration'))
    with pytest.raises(ValueError):
        cli.main(argv)
    assert not out.exists()
