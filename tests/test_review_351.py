"""Independent offline counterexamples for PR #351 at 87aa99c3.

Set REVIEW_351_ROOT to a git-archive extraction of the candidate. The review
branch contains no implementation copy. Only the expected assertion may xfail;
import errors, probe crashes and timeouts are errors, never successful evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "87aa99c337f700586f01039e40c6ad4dce410afa"


def probe(source, tmp_path):
    candidate = Path(os.environ.get("REVIEW_351_ROOT", ROOT)).resolve()
    if not (candidate / "scripts/assemble_final_pair_calibration.py").is_file():
        pytest.skip("Set REVIEW_351_ROOT to the archived PR #351 candidate")
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.update(PYTHONPATH=str(candidate), PYTHONDONTWRITEBYTECODE="1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", GIT_OPTIONAL_LOCKS="0")
    # An archive lacks .git; use this review worktree's object store only for
    # the assembler's read-only provenance queries, with the archive as tree.
    if not (candidate / ".git").exists():
        env["GIT_DIR"] = subprocess.check_output(
            ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip()
        env["GIT_WORK_TREE"] = str(candidate)
    guard = """
import importlib.util, json, socket, sys
from pathlib import Path
import numpy as np
def forbidden(*args, **kwargs):
    raise RuntimeError('review forbids physics/render/network/model calls')
socket.socket.connect = forbidden
for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[module] = None
from harness.vision_loc_client import VisionWorkerClient
VisionWorkerClient.__init__ = forbidden
spec = importlib.util.spec_from_file_location('fixture351', 'tests/test_final_pair_calibration_assembly.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
a, raw, motion, b = fixture.a, fixture.raw, fixture.motion, fixture.b
tmp = Path(sys.argv[1])
"""
    result = subprocess.run([sys.executable, "-B", "-c", guard + source, str(tmp_path)],
                            cwd=candidate, env=env, text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    value = json.loads(result.stdout)
    (tmp_path / "probe-result.json").write_text(json.dumps(value, indent=2) + "\n")
    return value


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="R1: output containment omits resolved collection symlinks")
def test_output_cannot_be_inside_a_symlinked_input_collection(tmp_path):
    result = probe("""
collection = fixture.synthetic_collection(tmp/'actual', 'unloaded')
view = tmp/'view'
view.mkdir()
(view/'calibration-unloaded').symlink_to(collection, target_is_directory=True)
output = collection/'review-output-must-not-exist'
try:
    cal = a.run(view, output)
except ValueError as exc:
    rejected, reason, status = True, str(exc), None
else:
    rejected, reason, status = False, None, cal['status']
print(json.dumps({'rejected': rejected, 'reason': reason, 'status': status,
                  'raw_modified': output.exists(),
                  'output_files': sorted(p.name for p in output.iterdir()) if output.exists() else []}))
""", tmp_path)
    assert result["rejected"] and not result["raw_modified"], result


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="R2: loaded fit accepts no observed below-breakaway step")
def test_loaded_deadband_requires_the_declared_four_amplitude_support(tmp_path):
    result = probe("""
data, _ = fixture.synthetic_data('loaded', loaded=True)
valid = np.ones(len(data['pose']), bool)
for axis, name in enumerate(b.AXES):
    for start, end in data['segments'][name]['steps']:
        if np.max(np.abs(data['u'][start:end, axis])) < .007:
            valid[start:end+1] = False
data['segments'] = raw.selected_segments(data['segments'], valid)
observed = {name: sorted(set(float(np.max(np.abs(data['u'][start:end, axis])))
                            for start, end in data['segments'][name]['steps']))
            for axis, name in enumerate(b.AXES)}
try:
    profile, report = motion.fit_profile([data], b.criterion(), loaded=True)
except ValueError as exc:
    accepted, detail = False, str(exc)
else:
    accepted = report['accepted']
    detail = {'deadband': profile['deadband'], 'optimizer': report['optimizer']}
print(json.dumps({'accepted': accepted, 'observed_magnitudes': observed, 'detail': detail}))
""", tmp_path)
    assert not result["accepted"], result


@pytest.mark.parametrize("record", ["trajectory.jsonl", "contacts.jsonl"])
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="R3: NaN loaded-evidence timestamps bypass the clock check")
def test_loaded_evidence_requires_finite_sample_times(tmp_path, record):
    result = probe("""
folder = tmp/'case'
folder.mkdir()
(folder/'scene.xml').write_text('<mujoco><worldbody><body name="cargo_beam"><geom name="cargo_beam_bar" type="box" size=".3 .02 .02" pos="0 0 .02"/></body></worldbody></mujoco>')
trace = [{'t': 0., 'beam_xyz_m': [0.,0.,.1], 'beam_rotation': np.eye(3).ravel().tolist()}]
contact = [{'t': 0., 'active_weld_ids': [], 'contacts': [
    {'geom1': 'cargo_beam_bar', 'geom2': rid+'__'+side+'_finger', 'dist_m': -.001}
    for rid in ('r1','r2') for side in ('left','right')]}]
record = """ + repr(record) + """
(trace if record == 'trajectory.jsonl' else contact)[0]['t'] = float('nan')
# Python's JSON decoder accepts this token; exercise the real file reader.
for name, value in [('trajectory.jsonl',trace), ('contacts.jsonl',contact)]:
    path = folder/'eval_only'/name
    path.parent.mkdir(exist_ok=True)
    path.write_text(''.join(json.dumps(row)+'\\n' for row in value))
data = {'folder':folder, 'robots':{'r1':{'t':np.array([0.])}}}
try:
    valid, counts = raw.loaded_mask(data, raw.Inputs(), json.loads(a.CRITERION.read_text())['loaded_selection'])
except ValueError as exc:
    accepted, detail = False, str(exc)
else:
    accepted, detail = bool(valid.any()), counts
print(json.dumps({'accepted':accepted, 'detail':detail, 'record':record}))
""", tmp_path)
    assert not result["accepted"], result


def test_validation_pose_contamination_cannot_select_training_noise(tmp_path):
    result = probe("""
import copy
data, _ = fixture.synthetic_data()
clean, clean_report = motion.fit_profile([data], b.criterion())
changed = copy.deepcopy(data)
for split in data['segments'].values():
    for start, end in split['prbs']:
        # Shared boundary poses are unchanged: ONLY validation interiors move.
        changed['pose'][start+1:end, 0] += .4*np.sin(np.linspace(0., np.pi, end-start+1)[1:-1])**2
dirty, dirty_report = motion.fit_profile([changed], b.criterion())
print(json.dumps({'same_noise': bool(np.allclose(clean['noise_abs'], dirty['noise_abs'], atol=1e-12, rtol=0)),
                  'clean_noise': clean['noise_abs'], 'dirty_noise': dirty['noise_abs'],
                  'clean_accepted': clean_report['accepted'], 'dirty_accepted': dirty_report['accepted']}))
""", tmp_path)
    assert result["same_noise"] and result["clean_accepted"] and not result["dirty_accepted"], result


def test_pipeline_rechecks_input_after_assembly_before_creating_output(tmp_path):
    result = probe("""
collection = fixture.synthetic_collection(tmp/'actual', 'unloaded')
original_assemble = a.assemble
def change_input_during_assembly(metadata, sections):
    path = collection/'result.json'
    path.write_text(path.read_text()+'\\n')
    return original_assemble(metadata, sections)
a.assemble = change_input_during_assembly
output = tmp/'new-output'
try:
    a.run(collection.parent, output)
except ValueError as exc:
    rejected, reason = True, str(exc)
else:
    rejected, reason = False, None
print(json.dumps({'rejected': rejected, 'reason': reason, 'output_created': output.exists()}))
""", tmp_path)
    assert result["rejected"] and "input changed" in result["reason"] and not result["output_created"], result
