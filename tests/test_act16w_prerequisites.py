"""Prerequisite safety boundary: no physics, GPU, credentials or network."""
import json
from scripts.act16w_prerequisites import signals, snapshot


def test_missing_or_quoted_signal_cannot_admit():
    assert not signals("warp1: READY_HOLD_SCENE")['ready_for_queue_inspection']
    assert not signals("act16w-gate: missing warp1: READY and SCENE_DECISION: x")['signals_present']


def test_latest_not_ready_overrides_historical_ready():
    value = signals("warp1: READY_HOLD_SCENE\nSCENE_DECISION: scene_v1\nwarp1: NOT_READY reason=runtime")
    assert value['status'] == 'WAIT_NOT_READY'
    assert value['warp1'].endswith('reason=runtime')


def test_both_signals_only_admit_queue_inspection():
    value = signals("2026-10-16 warp1: READY_HOLD_SCENE | queue=/tmp/q.json\nSCENE_DECISION: scene_v1")
    assert value['ready_for_queue_inspection']
    assert value['status'] == 'INSPECT_QUEUE'


def test_unready_or_pending_line_is_not_ready():
    for state in ('UNREADY', 'PENDING', 'PLAN_READY', 'NOT_READY'):
        assert not signals(f"warp1: {state}\nSCENE_DECISION: x")['ready_for_queue_inspection']


def queue_fixture(tmp_path, readiness, table_exists):
    alert = tmp_path / 'ops-alert.md'
    alert.write_text('warp1: READY_HOLD_SCENE\nSCENE_DECISION: v5')
    table = tmp_path / 'rejection_table.json'
    if table_exists:
        table.write_text('{}')
    queue = tmp_path / 'queue.json'
    queue.write_text(json.dumps(dict(backend_readiness=readiness, rejection_table=str(table),
                                    blockers=['model layout'] if readiness == 'NOT_READY' else [])))
    return snapshot(alert, queue)


def test_not_ready_queue_overrides_a_ready_alert(tmp_path):
    row = queue_fixture(tmp_path, 'NOT_READY', True)
    assert row['status'] == 'WAIT_NOT_READY'
    assert row['queue_blockers'] == ['model layout']
    assert not row['ready_for_queue_inspection']


def test_missing_rejection_table_blocks_queue_inspection(tmp_path):
    row = queue_fixture(tmp_path, 'READY', False)
    assert row['status'] == 'WAIT_REJECTION_TABLE'
    assert not row['ready_for_queue_inspection']


def test_ready_queue_with_real_table_allows_only_inspection(tmp_path):
    row = queue_fixture(tmp_path, 'READY', True)
    assert row['status'] == 'INSPECT_QUEUE'
    assert row['ready_for_queue_inspection']


def test_explicit_ready_queue_does_not_need_ready_word_in_progress_line(tmp_path):
    queue_fixture(tmp_path, 'READY', True)
    alert = tmp_path / 'ops-alert.md'
    alert.write_text('warp1: GPU_SHARED_TIMING\nSCENE_DECISION: v5')
    assert snapshot(alert, tmp_path / 'queue.json')['status'] == 'INSPECT_QUEUE'
