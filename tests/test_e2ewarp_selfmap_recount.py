"""Non-physics selfmap recount tests on synthetic raw artifacts."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        'e2ewarp_selfmap_recount',
        ROOT / 'scripts' / 'e2ewarp_selfmap_recount.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fixture(root: Path, *, inserted: int, policy='elapsed_sim_v1'):
    rows = []
    ticks = [0, 1, 2, 3, 4, 12]
    for i, t in enumerate(ticks):
        rows.append(dict(
            world=0, robot='r1', tick=t, sim_s=t / 10.0,
            fk_status='servo_fk_nominal_unloaded',
            self_map=dict(scan_status='observed_wall_contacts',
                          wall_columns=5 if i >= 2 else 0,
                          inserted=((inserted >= 1 and i == 0)
                                    or (inserted >= 2 and i == 5)))))
    root.mkdir(parents=True, exist_ok=True)
    (root / 'localization.json').write_text(json.dumps(rows))
    (root / 'runtime-applied.json').write_text(
        json.dumps(dict(map_keyframe_admission=policy, host='synthetic')))
    (root / 'result.json').write_text(
        json.dumps(dict(status='DONE', source_sha='synthetic', nworld=1)))
    (root / 'rejections.json').write_text(json.dumps([
        dict(reason='camera_qualification'), dict(reason='keyframe_interval_wait')]))


def test_recount_elapsed_fix_counts_insertions(tmp_path):
    raw = tmp_path / 'raw'
    write_fixture(raw, inserted=2)
    m = load_module()
    report = m.recount(raw)
    funnel = {s['stage']: s['cumulative_pass_n'] for s in report['frame_funnel']}
    assert funnel['own_rgb'] == 6
    assert funnel['qualified_unloaded_FK'] == 6
    assert funnel['settled_scan'] == 6
    assert funnel['observed_wall_contacts'] == 4
    assert funnel['inserted_keyframe'] == 2
    check = report['elapsed_sim_check']
    assert check['policy'] == 'elapsed_sim_v1'
    assert check['keyframe_insertions_gt_zero'] is True
    assert check['inserted_off_old_modulo_grid'] == 1  # tick 12 not a modulo-10 frame
    assert check['elapsed_rule_violations'] == 0
    assert report['nonphysics'] is True


def test_cli_exits_nonzero_when_elapsed_inserts_zero(tmp_path):
    raw = tmp_path / 'raw-zero'
    write_fixture(raw, inserted=0)
    out = tmp_path / 'recount.json'
    script = ROOT / 'scripts' / 'e2ewarp_selfmap_recount.py'
    proc = subprocess.run([sys.executable, str(script), '--raw', str(raw),
                           '--output', str(out), '--json-only'],
                          capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    assert 'SELFMAP_GATE_FAILED' in proc.stderr
    allowed = subprocess.run([sys.executable, str(script), '--raw', str(raw),
                              '--output', str(out), '--json-only',
                              '--allow-zero'], capture_output=True, text=True)
    assert allowed.returncode == 0, allowed.stderr
    report = json.loads(out.read_text())
    assert report['elapsed_sim_check']['keyframe_insertions'] == 0


def test_cli_exit_zero_when_insertions_gt_zero(tmp_path):
    raw = tmp_path / 'raw-ok'
    write_fixture(raw, inserted=2)
    out = tmp_path / 'out' / 'recount.json'
    proc = subprocess.run([sys.executable,
                           str(ROOT / 'scripts' / 'e2ewarp_selfmap_recount.py'),
                           '--raw', str(raw), '--output', str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    assert (out.parent / 'sha256.json').is_file()
