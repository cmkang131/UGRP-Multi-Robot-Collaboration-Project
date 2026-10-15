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


def test_warp3_handoff_needs_independent_starts_gate_and_record_api():
    text = 'SCENE_DECISION: v5\nwarp3: DISTINCT_STARTS PASS\nwarp3: TEACHER_GATE 38/40'
    assert not signals(text, 'warp3')['ready_for_queue_inspection']
    ready = text + '\nwarp3: RECORD_API_READY | source=abc'
    row = signals(ready, 'warp3')
    assert row['status'] == 'INSPECT_QUEUE'
    assert row['teacher_success_n'] == 38 and row['teacher_attempts_N'] == 40
    assert signals(ready.replace('TEACHER_GATE 38', 'TEACHER_GATE PASS 38'), 'warp3')['ready_for_queue_inspection']
    running = signals(ready.replace('TEACHER_GATE 38', 'TEACHER_GATE RUNNING 38'), 'warp3')
    assert running['teacher_attempts_N'] == 40
    assert not running['ready_for_queue_inspection']
    assert not signals(ready.replace('38/40', '37/40'), 'warp3')['ready_for_queue_inspection']
    assert not signals(ready.replace('38/40', '19/20'), 'warp3')['ready_for_queue_inspection']
    assert not signals(ready.replace('DISTINCT_STARTS PASS', 'DISTINCT_STARTS PENDING'), 'warp3')['ready_for_queue_inspection']


def test_warp3_failed_gate_or_later_not_ready_cannot_reuse_ready_receipts():
    ready = ('SCENE_DECISION: v5\nwarp1: READY\nwarp3: DISTINCT_STARTS PASS\n'
             'warp3: TEACHER_GATE 40/40\nwarp3: RECORD_API_READY')
    assert not signals(ready + '\nwarp3: TEACHER_GATE 30/40', 'warp3')['ready_for_queue_inspection']
    assert signals(ready + '\nwarp3: NOT_READY | camera mismatch', 'warp3')['status'] == 'WAIT_NOT_READY'
    assert not signals('SCENE_DECISION: v5\nwarp1: READY', 'warp3')['ready_for_queue_inspection']


def test_warp3_ready_queue_cannot_replace_gate_and_api_receipts(tmp_path):
    queue_fixture(tmp_path, 'READY', True)
    alert = tmp_path / 'ops-alert.md'
    alert.write_text('warp3: DISTINCT_STARTS PASS\nSCENE_DECISION: v5')
    assert not snapshot(alert, tmp_path / 'queue.json', 'warp3')['ready_for_queue_inspection']
