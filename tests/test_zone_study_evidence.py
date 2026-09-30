"""P06 synthetic evidence only: no world, rendering, inference or network.

Fake raw/event files live exclusively in pytest tmp_path. Existing snapshots and
research outputs are never inputs or destinations of these tests.
"""
import copy
import hashlib
import json
import math
import sys
import time
from types import SimpleNamespace

import pytest

from harness import zone_study_eval as ev
from harness import zone_study_referee as zr
from scripts import run_zone_study_integration as runner
from scripts import zone_study_evidence_writer as evidence_writer
from scripts.tensorboard_tools import export as tb
from scripts.tensorboard_tools.media import media_registry
from tests.test_zone_study_integration import MAP, SCENARIO, run
from tests import test_zone_study_referee as referee_tests
from tests.test_zone_study_referee import at_zone, feed, episode, never, _study_view
from tests.test_zone_study_eval import trial as metric_trial

REFEREE_TRUTH = runner.StudyTeamHost.referee_truth


@pytest.fixture(autouse=True)
def no_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('P06 must not instantiate a world, render or run a physical trial')
    monkeypatch.setattr(runner, 'StudyTeamHost', forbidden)
    monkeypatch.setattr(runner, 'run_trial', forbidden)
    monkeypatch.setattr(runner.zone_eval_top, 'apply_to_world', forbidden)


def order(item='box_00'):
    return [{'order_id': 'order-distinct-from-item', 'kind': 'cyan', 'count': 1,
             'identity': 'specific_item', 'item_ids': [item], 'destination_zone': 'A'}]


def record_for(ref, end=5., reason='sim_horizon', cap=10.):
    rec = metric_trial(orders=ref.orders, end_sim_s=end, end_reason=reason, horizon=cap)
    return zr.apply_to_record(rec, ref)


@pytest.mark.parametrize('bad', [dict(z=zr.ON_FLOOR_MAX_Z_M), dict(speed=zr.SETTLED_SPEED_M_S),
                                 dict(held=True)])
def test_thresholds_break_continuous_settle_window(bad):
    ref = zr.Referee(order(), MAP)
    feed(ref, 0., 1., {'box_00': at_zone('A')})
    ref.observe(1.1, {'box_00': at_zone('A', **bad)})
    feed(ref, 1.2, 3.1, {'box_00': at_zone('A')})
    assert not ref.orders_complete()
    ref.observe(3.2, {'box_00': at_zone('A')})
    assert ref.orders_complete()
    rec = record_for(ref)
    assert ev.efficiency_metrics(rec)['success'] is True
    assert ref.per_order()['order-distinct-from-item']['item_delivered_sim_s'] == {'box_00': 1.2}


def test_missing_truth_is_not_continuous_settling_or_a_standing_delivery():
    ref = zr.Referee(order(), MAP)
    ref.observe(0., {'box_00': at_zone('A')})
    ref.observe(1., {})
    ref.observe(2., {'box_00': at_zone('A')})
    assert not ref.orders_complete()
    ref.observe(4., {'box_00': at_zone('A')})
    assert ref.orders_complete()
    ref.observe(4.1, {})
    assert not ref.orders_complete() and ref.history[-1]['reason'] == 'missing_truth'


@pytest.mark.parametrize('t', [math.nan, math.inf, -1, True])
def test_invalid_truth_clock_is_refused(t):
    with pytest.raises(ValueError):
        zr.Referee(order(), MAP).observe(t, {'box_00': at_zone('A')})


def test_same_colour_other_identity_and_repeated_delivery_do_not_fill_named_order():
    ref = zr.Referee(order(), MAP)
    feed(ref, 0., 5., {'box_01': at_zone('A')})
    assert not ref.orders_complete()
    assert ev.efficiency_metrics(record_for(ref))['surplus_items'] == 1
    feed(ref, 5.1, 7.1, {'box_00': at_zone('A'), 'box_01': at_zone('A')})
    rec = record_for(ref, end=8.)
    rec['referee']['deliveries'] *= 3
    assert ev.efficiency_metrics(rec)['delivered_items'] == 1
    assert ev.efficiency_metrics(rec)['ordered_items'] == 1


@pytest.mark.parametrize('reason,failure', [('api_failure', 'infra:API'), ('host_error', 'infra:HOST_ERROR'),
                                          ('policy_failure', 'other'), ('interrupted', None)])
def test_terminal_failure_cannot_be_promoted_by_referee(reason, failure):
    ref = zr.Referee(order(), MAP)
    feed(ref, 0., 2., {'box_00': at_zone('A')})
    rec = metric_trial(orders=order(), end_sim_s=3., end_reason=reason, horizon=10.)
    rec['failure_class'] = failure
    zr.apply_to_record(rec, ref)
    assert rec['end_reason'] == reason
    assert not ev.efficiency_metrics(rec)['success']
    assert ev.efficiency_metrics(rec)['par_makespan_sim_s'] == 20.


def test_late_confirmation_does_not_backdate_success_inside_cap():
    ref = zr.Referee(order(), MAP)
    feed(ref, 9., 11., {'box_00': at_zone('A')})
    rec = record_for(ref, end=11., cap=10.)
    assert rec['end_reason'] == 'sim_horizon'
    eff = ev.efficiency_metrics(rec)
    assert not eff['success'] and eff['delivered_items'] == 0
    assert eff['deliveries_outside_window'] == 1 and eff['par_makespan_sim_s'] == 20.
    assert not zr.evaluation_block(rec, ref)['orders']['order-distinct-from-item']['complete']


@pytest.mark.parametrize('damage', ['duplicate_order', 'duplicate_item', 'wrong_kind', 'missing_time'])
def test_ambiguous_or_corrupt_delivery_join_never_succeeds(damage):
    rec = metric_trial(orders=order(), deliveries=[{'item_id': 'box_00', 'kind': 'cyan', 'zone': 'A', 'sim_s': 1.}])
    if damage == 'duplicate_order':
        rec['orders'] += copy.deepcopy(rec['orders'])
    elif damage == 'duplicate_item':
        rec['orders'] += [{**rec['orders'][0], 'order_id': 'second-order'}]
    elif damage == 'wrong_kind':
        rec['referee']['deliveries'][0]['kind'] = 'red'
        assert not ev.efficiency_metrics(rec)['success']
        return
    else:
        rec['referee']['deliveries'][0].pop('sim_s')
    with pytest.raises(ev.TrialError):
        ev.efficiency_metrics(rec)


@pytest.mark.parametrize('condition', runner.MAIN_CONDITIONS)
def test_eval_truth_top_configuration_video_and_hidden_events_do_not_reach_inputs(condition, tmp_path, monkeypatch):
    hidden = {'eval': {'hidden_events': [{'event_id': 'synthetic-hold', 'kind': 'robot_hold',
              'trigger': {'kind': 'sim_time', 'at_sim_s': 5.},
              'target': {'robot_id': 'r3', 'duration_s': 1.}, 'discovery': {'kind': 'own_camera_self'}}]}}
    base, *_ = episode(condition, never, horizon=12.)
    original_init = referee_tests.FakeHost.__init__
    def changed_eval(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        altered = copy.deepcopy(MAP)
        altered['top_cameras'][0]['fov_y_deg'] = 70.
        self.eval_static = runner.zone_eval_top.eval_static_map(altered, 'zone_eval_top_v1')
        self.eval_only = {'top_camera': runner.evaluation_top_config(altered)}
        video = tmp_path / 'eval_only/overview.mp4'
        video.parent.mkdir(parents=True)
        video.write_bytes(b'synthetic changed TOP video bytes')
        self.eval_only['video'] = str(video)
    monkeypatch.setattr(referee_tests.FakeHost, '__init__', changed_eval)
    changed, _, _, host, _, _ = episode(condition, lambda t: {**never(t), 'box_00': at_zone('A')},
                                      horizon=12., hidden=zr.HiddenEventSchedule(hidden))
    assert host.eval_only['top_camera']['cameras_sha256'] != runner.evaluation_top_config(MAP)['cameras_sha256']
    assert host.fired and base.requests
    assert base.input_log == changed.input_log
    assert base.requests == changed.requests
    assert base.messages == changed.messages
    assert _study_view(base, 13.) == _study_view(changed, 13.)


def test_referee_truth_adapter_uses_item_ids_and_linear_speed_with_fake_mujoco(monkeypatch):
    # Replace the module itself; no MuJoCo model, forward or velocity API runs.
    def velocity(model, data, object_type, body_id, target, local):
        target[:] = [9., 8., 7., .003, .004, 0.]
    monkeypatch.setitem(sys.modules, 'mujoco', SimpleNamespace(mjtObj=SimpleNamespace(mjOBJ_BODY=1),
                                                             mj_objectVelocity=velocity))
    body = SimpleNamespace(id=4, xpos=[1., 2., .016], xquat=[1., 0., 0., 0.])
    data = SimpleNamespace(ncon=1, contact=[SimpleNamespace(geom1=1, geom2=7)], body=lambda name: body)
    host = SimpleNamespace(world=SimpleNamespace(model=object(), data=data),
                           _fingers={r: ({1}, {2}) for r in runner.ROBOTS},
                           _box_geom={'cyan-distinct': {7}},
                           objects={'cyan-distinct': {'body_name': 'cargo-body', 'kind': 'cyan'}})
    assert REFEREE_TRUTH(host) == {'cyan-distinct': {'kind': 'cyan', 'x': 1., 'y': 2., 'z': .016,
                                                  'yaw': 0., 'held': True, 'speed': .005}}


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    return path


def reseal(src):
    manifest = json.loads((src / 'manifest.json').read_text())
    manifest['files'] = {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in src.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    put(src, 'manifest.json', manifest)


@pytest.fixture
def completed():
    return run('no_comm', horizon=12.)[:2]


def synthetic_source(tmp_path, outcome, completed, *, attempt=1):
    src = tmp_path / (outcome if attempt == 1 else f'{outcome}-attempt{attempt}')
    src.mkdir()
    trial, result = completed
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 2., 4., {'box_00': at_zone('A'), 'box_02': at_zone('B'), 'box_05': at_zone('C')})
    bundle = {'pose_provider': {'label': {'pose_provider': 'synthetic'}},
              'host_spec': {'order_sheet': trial.sheet}}
    failure_class = {'api_failure': runner.llm.API_ERROR, 'host_error': runner.llm.HOST_ERROR,
                     'policy_failure': runner.llm.OTHER}.get(outcome)
    failure = {'type': 'SyntheticFailure', 'failure_class': failure_class} if failure_class else None
    stopped = 'interrupted' if outcome == 'interrupted' else 'horizon'
    if outcome == 'host_error':
        trial = result = None
    elif outcome == 'interrupted':
        result = None
    summary = evidence_writer.write_outputs(src, {'horizon_s': 99.}, {'episode_id': 'fake', 'trial_seed': 700},
                                   'no_comm', bundle, runner.digest(bundle), None, trial, result, stopped,
                                   failure, {'sha': 'synthetic-no-execution'}, time.time(), (0., 0., 0.), True,
                                   referee=None if outcome == 'not_evaluated' else ref, horizon_s=12.,
                                   scenario_id=SCENARIO['scenario_id'], attempt=attempt)
    summary['evidence_kind'] = 'synthetic'
    put(src, 'result.json', summary)
    reseal(src)
    return src


@pytest.fixture
def export_api():
    pytest.importorskip('tensorboard')
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    return EventAccumulator


@pytest.mark.parametrize('outcome', ['success', 'policy_failure', 'api_failure', 'host_error',
                                     'interrupted', 'not_evaluated'])
def test_terminal_chain_roundtrip_and_event_values(tmp_path, completed, export_api, outcome):
    src = synthetic_source(tmp_path, outcome, completed)
    before = {p: p.read_bytes() for p in src.rglob('*') if p.is_file()}
    out = tmp_path / 'events'
    manifest = tb.convert(src, out, allow_synthetic=True, max_images=0)
    ea = export_api(str(out), size_guidance={'scalars': 0}).Reload()
    source = ev.efficiency_metrics(ev.parse_trial(json.loads((src / 'study/trial_record.json').read_text())))
    for tag, key in ev.SCALAR_TAGS.items():
        assert manifest['metadata']['source_metrics'][tag] == source[key]
    for tag, value in manifest['metadata']['source_metrics'].items():
        if value is None:
            assert tag not in ea.Tags()['scalars'], tag
        else:
            assert ea.Scalars(tag)[0].value == pytest.approx(float(value)), tag
    assert ea.Scalars('cohort/trials')[0].value == 1
    assert ea.Scalars('evaluation/reported_success')[0].value == (outcome == 'success')
    assert manifest['metadata']['sim_horizon_s'] == 12.
    assert manifest['metadata']['case'] == SCENARIO['scenario_id']
    if outcome != 'success':
        assert ea.Scalars('result/par_makespan_sim_s')[0].value == 24.
    if outcome == 'interrupted':
        for tag in ('result/model_calls', 'result/tokens_total', 'result/think_sim_cost_s'):
            assert tag not in ea.Tags()['scalars']
        assert ea.Scalars('result/model_calls_lower_bound')[0].value > 0
        assert ea.Scalars('result/tokens_total_lower_bound')[0].value > 0
    assert all(p.read_bytes() == data for p, data in before.items())
    assert set(manifest['source_files']) == set(json.loads((src / 'manifest.json').read_text())['files']) | {'manifest.json'}
    assert not manifest['metadata']['top_rgb_video_registered'] and manifest['videos'] == []
    from tensorboard.plugins.hparams import metadata, plugin_data_pb2
    plugin = plugin_data_pb2.HParamsPluginData()
    plugin.ParseFromString(ea.PluginTagToContent('hparams')[metadata.SESSION_START_INFO_TAG])
    assert plugin.session_start_info.hparams['condition'].string_value == 'no_comm'
    assert plugin.session_start_info.hparams['sim_horizon_s'].string_value == '12.0'
    assert plugin.session_start_info.hparams['record_complete'].string_value == str(manifest['metadata']['record_complete'])
    with pytest.raises(FileExistsError):
        tb.convert(src, out, allow_synthetic=True)


@pytest.mark.parametrize('damage', ['delete', 'tamper', 'unlisted', 'trial_join', 'cap', 'evaluation', 'image_ref'])
def test_broken_raw_chain_publishes_no_events(tmp_path, completed, export_api, damage):
    src = synthetic_source(tmp_path, 'success', completed)
    if damage == 'delete':
        (src / 'study/trial_record.json').unlink()
    elif damage == 'tamper':
        with (src / 'study/trial_record.json').open('a') as stream:
            stream.write(' ')
    elif damage == 'unlisted':
        (src / 'extra.json').write_text('{}')
    elif damage == 'trial_join':
        result = json.loads((src / 'result.json').read_text())
        result['study']['end_reason'] = 'host_error'
        put(src, 'result.json', result)
        reseal(src)
    elif damage == 'cap':
        manifest = json.loads((src / 'manifest.json').read_text())
        manifest['terminal']['sim_horizon_s'] = 13.
        put(src, 'manifest.json', manifest)
    elif damage == 'evaluation':
        evaluation = json.loads((src / 'eval_only/evaluation.json').read_text())
        evaluation['success'] = False
        put(src, 'eval_only/evaluation.json', evaluation)
        reseal(src)
    else:
        image, *_ = (src / 'study/request_images').glob('*.jpg')
        image.unlink()
        reseal(src)  # even a re-signed manifest cannot remove a referenced request image
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, max_images=0, allow_synthetic=True)
    assert not list(out.glob('events*'))
    assert json.loads((out / 'manifest.json').read_text())['complete'] is False


@pytest.mark.parametrize('damage', ['trial_id', 'scenario', 'seed', 'order_ids'])
def test_a303_1_resealed_foreign_trial_or_orders_publish_no_events(tmp_path, completed, export_api, damage):
    src = synthetic_source(tmp_path, 'success', completed)
    record = json.loads((src / 'study/trial_record.json').read_text())
    if damage == 'order_ids':
        for i, row in enumerate(record['orders']):
            row['order_id'] = f'unrelated-order-{i}'
    else:
        record[damage] = 987654 if damage == 'seed' else f'unrelated-{damage}'
    put(src, 'study/trial_record.json', record)
    reseal(src)  # Content joins must reject even when every file hash is valid.
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, max_images=0, allow_synthetic=True)
    assert not list(out.glob('events*'))


@pytest.mark.parametrize('damage', ['result_identity', 'manifest_identity', 'evaluation_identity',
    'result_scenario', 'result_seed', 'result_episode', 'result_attempt_bool', 'attempt_type', 'attempt_zero',
    'bundle_scenario', 'bundle_orders', 'evaluation_order_id', 'evaluation_item_id',
    'evaluation_time', 'evaluation_order_counts', 'evaluation_count_type', 'study_config_seed', 'request_sheet', 'legacy'])
def test_a303_1_all_evidence_joins_reject_rehashed_content(tmp_path, completed, export_api, damage):
    src = synthetic_source(tmp_path, 'success', completed)
    paths = {'result': 'result.json', 'manifest': 'manifest.json', 'trial': 'study/trial_record.json',
             'evaluation': 'eval_only/evaluation.json', 'config': 'study/study_config.json'}
    rows = {name: json.loads((src / path).read_text()) for name, path in paths.items()}
    if damage.endswith('_identity'):
        rows[damage.removesuffix('_identity')]['evidence_identity']['trial_id'] = 'foreign'
    elif damage == 'result_attempt_bool':
        rows['result']['evidence_identity']['attempt'] = True
    elif damage.startswith('result_'):
        rows['result'][damage.removeprefix('result_')] = 'foreign'
    elif damage.startswith('attempt_'):
        for name in ('result', 'manifest', 'trial', 'evaluation'):
            rows[name]['evidence_identity']['attempt'] = True if damage == 'attempt_type' else 0
    elif damage.startswith('bundle_'):
        sheet = rows['manifest']['bundle']['host_spec']['order_sheet']
        if damage == 'bundle_scenario':
            sheet['scenario_id'] = runner.digest('foreign')
        else:
            sheet['orders'][0]['order_id'] = 'foreign'
        bundle_sha = runner.digest(rows['manifest']['bundle'])
        rows['manifest']['bundle_sha256'] = rows['result']['bundle_sha256'] = bundle_sha
        # Update all declared digests as well: actual trial/request content still disagrees.
        for name in ('result', 'manifest', 'trial', 'evaluation'):
            rows[name]['evidence_identity'].update(bundle_sha256=bundle_sha,
                order_sheet_sha256=runner.digest(sheet), orders_sha256=runner.digest(sheet['orders']))
    elif damage.startswith('evaluation_'):
        evaluation = rows['evaluation']
        oid = next(iter(evaluation['orders']))
        if damage == 'evaluation_order_id':
            evaluation['orders']['foreign'] = evaluation['orders'].pop(oid)
        elif damage == 'evaluation_order_counts':
            evaluation['orders_by_id'][oid]['delivered'] = 999
        elif damage == 'evaluation_count_type':
            evaluation['orders'][oid]['delivered'] = True
        else:
            items = evaluation['orders'][oid]['item_delivered_sim_s']
            item = next(iter(items))
            if damage == 'evaluation_item_id':
                items['foreign'] = items.pop(item)
            else:
                items[item] += .5
    elif damage == 'study_config_seed':
        rows['config']['seed'] += 1
    elif damage == 'request_sheet':
        # Replace every outer order reference consistently; leave the saved model request intact.
        # parse_trial still validates that request against its original call provenance.
        sheet = rows['manifest']['bundle']['host_spec']['order_sheet']
        sheet['note_ko'] += ' changed'
        sheet_sha = runner.digest(sheet)
        bundle_sha = runner.digest(rows['manifest']['bundle'])
        rows['manifest']['bundle_sha256'] = rows['result']['bundle_sha256'] = bundle_sha
        rows['config']['order_sheet_sha256'] = sheet_sha
        for name in ('result', 'manifest', 'trial', 'evaluation'):
            rows[name]['evidence_identity'].update(order_sheet_sha256=sheet_sha, bundle_sha256=bundle_sha)
    else:
        for name in ('result', 'manifest', 'trial', 'evaluation'):
            rows[name].pop('evidence_identity')
    for name, path in paths.items():
        put(src, path, rows[name])
    reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, max_images=0, allow_synthetic=True)
    assert not list(out.glob('events*'))


def test_a303_1_retry_keeps_logical_trial_and_distinct_attempt_identity(tmp_path, completed, export_api):
    identities = []
    for attempt in (1, 2):
        src = synthetic_source(tmp_path, 'success', completed, attempt=attempt)
        out = tmp_path / f'events-{attempt}'
        manifest = tb.convert(src, out, max_images=0, allow_synthetic=True)
        identities.append(manifest['metadata']['evidence_identity'])
        assert export_api(str(out)).Reload().Scalars('cohort/trials')[0].value == 1
    assert identities[0]['trial_id'] == identities[1]['trial_id']
    assert identities[0]['run_id'] != identities[1]['run_id']
    assert [row['attempt'] for row in identities] == [1, 2]


def test_a303_2_evidence_writer_preserves_the_registered_runner_bytes():
    from scripts.zone_pair_v6_contract import PREREG_V6E
    sources = json.loads(PREREG_V6E.read_text())['v6_contract']['source_sha256']
    path = 'scripts/run_zone_study_integration.py'
    assert hashlib.sha256((runner.ROOT / path).read_bytes()).hexdigest() == sources[path]
    assert runner.write_outputs is not evidence_writer.write_outputs
    assert 'scripts/zone_study_evidence_writer.py' not in sources


@pytest.mark.parametrize('envelope', ['result', 'manifest', 'both'])
def test_a303_3_missing_terminal_marker_publishes_no_events(tmp_path, completed, export_api, envelope):
    src = synthetic_source(tmp_path, 'success', completed)
    for name in ('result', 'manifest') if envelope == 'both' else (envelope,):
        row = json.loads((src / f'{name}.json').read_text())
        row.pop('terminal')
        put(src, f'{name}.json', row)
    reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, max_images=0, allow_synthetic=True)
    assert not list(out.glob('events*'))


@pytest.mark.parametrize('damage', ['false', 'integer', 'string', 'null', 'empty_manifest',
                                   'partial_manifest', 'incomplete_type', 'missing_complete', 'end_time'])
def test_a303_3_invalid_terminal_marker_publishes_no_events(tmp_path, completed, export_api, damage):
    src = synthetic_source(tmp_path, 'success', completed)
    result = json.loads((src / 'result.json').read_text())
    manifest = json.loads((src / 'manifest.json').read_text())
    if damage in ('false', 'integer', 'string', 'null'):
        result['terminal'] = {'false': False, 'integer': 1, 'string': 'true', 'null': None}[damage]
    elif damage == 'empty_manifest':
        manifest['terminal'] = {}
    elif damage == 'partial_manifest':
        manifest['terminal'].pop('failure_class')
    elif damage == 'incomplete_type':
        manifest['terminal']['record_complete'] = 1
    elif damage == 'missing_complete':
        result['study'].pop('record_complete')
    else:
        manifest['terminal']['end_sim_s'] += 1.
    put(src, 'result.json', result)
    put(src, 'manifest.json', manifest)
    reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, max_images=0, allow_synthetic=True)
    assert not list(out.glob('events*'))


def test_synthetic_requires_opt_in_and_temporary_destination(tmp_path, completed, export_api, monkeypatch):
    src = synthetic_source(tmp_path, 'success', completed)
    with pytest.raises(ValueError, match='temporary-logdir'):
        tb.convert(src, tmp_path / 'events')
    monkeypatch.setattr(tb.tempfile, 'gettempdir', lambda: str(tmp_path / 'different-temp-root'))
    with pytest.raises(ValueError, match='temporary-logdir'):
        tb.convert(src, tmp_path / 'events', allow_synthetic=True)


@pytest.mark.parametrize('kind', [None, 'top_rgb', 'gt_visualization'])
def test_camera_json_is_not_video_and_gt_is_not_top_rgb(tmp_path, completed, export_api, kind):
    src = synthetic_source(tmp_path, 'success', completed)
    put(src, 'eval_only/top_camera.json', {'profile': 'synthetic-camera-config'})
    if kind:
        video = src / 'eval_only/overview.mp4'
        video.write_bytes(b'fake media registry fixture; not a playable video')
        put(src, 'eval_only/media.json', {'schema': 'ugrp.zone_study_media.v1', 'videos': [
            {'path': 'eval_only/overview.mp4', 'kind': kind, 'sha256': hashlib.sha256(video.read_bytes()).hexdigest()}]})
    reseal(src)
    out = tmp_path / 'events'
    manifest = tb.convert(src, out, allow_synthetic=True, max_images=0)
    assert manifest['metadata']['top_camera_config_present']
    assert manifest['metadata']['top_rgb_video_registered'] is (kind == 'top_rgb')
    assert len(media_registry(out)) == int(kind is not None)
    if kind:
        assert manifest['videos'][0]['kind'] == kind
        text = export_api(str(out)).Reload().Tensors('media/eval_only/overview.mp4')[0].tensor_proto.string_val[0]
        assert kind.encode() in text
        if kind == 'gt_visualization':
            assert b'top_rgb' not in text


def test_unknown_usage_and_unrecorded_metrics_survive_export(tmp_path, completed, export_api):
    src = synthetic_source(tmp_path, 'api_failure', completed)
    original = json.loads((src / 'study/trial_record.json').read_text())
    rec = metric_trial(condition='no_comm', scenario=original['scenario'], seed=original['seed'],
                       orders=original['orders'], provenance=original['provenance'],
                       deliveries=[], end_reason='api_failure', model={
        'logical_calls': 2, 'http_attempts': 3, 'tokens_complete': False, 'usage_unknown_calls': 1,
        'tokens': {'input': 30, 'output': 4, 'image': 0, 'cached': 0},
        'sim_cost_s': {'think': 1., 'talk': .2, 'call': 1.2, 'delivery': .1},
        'wall_latency_ms': [250.]})
    rec['condition'] = 'no_comm'
    rec['failure_class'] = runner.llm.API_ERROR
    rec['evidence_identity'] = original['evidence_identity']
    rec['record_complete'] = True
    rec.pop('idle')
    rec.pop('replans')
    rec['referee'].pop('conflicts')
    rec['referee'].pop('deadlocks')
    put(src, 'study/trial_record.json', rec)
    put(src, 'eval_only/evaluation.json', {**ev.efficiency_metrics(rec),
        'orders': evidence_writer.per_order_evaluation(rec), 'evidence_identity': rec['evidence_identity']})
    summary = json.loads((src / 'result.json').read_text())
    summary['study'].update(end_sim_s=rec['end_sim_s'])
    summary['sim_horizon_s'] = rec['budget']['sim_horizon_s']
    put(src, 'result.json', summary)
    manifest = json.loads((src / 'manifest.json').read_text())
    manifest['terminal']['sim_horizon_s'] = rec['budget']['sim_horizon_s']
    manifest['terminal']['end_sim_s'] = rec['end_sim_s']
    put(src, 'manifest.json', manifest)
    reseal(src)
    out = tmp_path / 'events'
    tb.convert(src, out, max_images=0, allow_synthetic=True)
    ea = export_api(str(out)).Reload()
    for absent in ('result/tokens_total', 'result/commands', 'result/cost_usd', 'result/conflicts',
                   'result/deadlocks', 'result/idle_robot_s', 'result/replans'):
        assert absent not in ea.Tags()['scalars']
    for tag, value in {'result/tokens_total_lower_bound': 34., 'result/usage_unknown_calls': 1.,
                       'result/model_calls': 2., 'result/http_attempts': 3.,
                       'result/think_sim_cost_s': 1., 'result/call_sim_cost_s': 1.2,
                       'result/talk_sim_cost_s': .3, 'result/wall_latency_ms_mean': 250.}.items():
        assert ea.Scalars(tag)[0].value == pytest.approx(value)


def test_cohort_keeps_all_six_terminal_attempts_in_denominator(tmp_path, completed):
    sources = [synthetic_source(tmp_path, kind, completed) for kind in
               ('success', 'policy_failure', 'api_failure', 'host_error', 'interrupted', 'not_evaluated')]
    records = [ev.parse_trial(json.loads((src / 'study/trial_record.json').read_text())) for src in sources]
    for i, record in enumerate(records):
        record['trial_id'] += f'-attempt-{i}'
    aggregate = ev.summarise(records)
    summary = aggregate['conditions']['no_comm']
    assert summary['trials'] == 6 and summary['successes'] == 1
    assert summary['success_rate'] == pytest.approx(1 / 6)
    assert sum(summary['end_reasons'].values()) == 6
    assert summary['cohort_tokens_total'] is None
    assert summary['cohort_delivery_rate'] is None
    cohort = next(r for r in ev.scalar_export(aggregate)['runs'] if r['run'] == 'cohort/no_comm')
    assert 'cohort/delivery_rate' not in cohort['scalars']


def test_raw_mutation_during_export_is_rejected(tmp_path, completed, export_api, monkeypatch):
    src = synthetic_source(tmp_path, 'success', completed)
    original = tb.Writer.hparams
    def mutate(writer, *args):
        with (src / 'study/inputs.jsonl').open('a') as stream:
            stream.write('{}\n')
        return original(writer, *args)
    monkeypatch.setattr(tb.Writer, 'hparams', mutate)
    out = tmp_path / 'events'
    with pytest.raises(ValueError, match='Source changed'):
        tb.convert(src, out, allow_synthetic=True, max_images=0)
    assert not list(out.glob('events*'))


@pytest.mark.parametrize('damage', ['result_schema', 'training_bypass', 'missing_archive', 'malformed_media'])
def test_cannot_bypass_zone_study_evidence_contract(tmp_path, completed, export_api, damage):
    src = synthetic_source(tmp_path, 'success', completed)
    if damage == 'result_schema':
        result = json.loads((src / 'result.json').read_text())
        result['schema'] = 'tampered'
        put(src, 'result.json', result)
    elif damage == 'training_bypass':
        put(src, 'report.json', {'progress': [{'step': 1, 'loss': 0.1}]})
        (src / 'study/trial_record.json').unlink()
    elif damage == 'missing_archive':
        record = json.loads((src / 'study/trial_record.json').read_text())
        record['request_archive'] = []
        put(src, 'study/trial_record.json', record)
        reseal(src)
    else:
        (src / 'eval_only/media.json').write_text('{')
        reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, allow_synthetic=True, max_images=0)
    assert not list(out.glob('events*'))
