import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p2cases', ROOT/'experiments/2026-10-21-pairact-p2/make_p2_cases.py')
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)


def test_pins_point_to_p2_trees():
    text = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "ADAPTER_SHA = '3779d9615ef6dc8e38f57ab968a14a9e45189ecc'" in text     # adapter -a-c5
    assert "TEACHER_SHA = '75929e7719ad98a089e3dda5251f4249d8bae511'" in text     # teacher -c5 (-c4 + c3 admission)


def test_pinned_adapter_run_passes_the_bridge_audit():
    """Codex follow-up (2026-10-20): adapter d128984d had two runner.run calls and the bridge required one
    (ValueError before any VM step). Compile the pinned adapter's run() with this root's compile_function.
    A clone without the pinned commit fails (required check, not skippable)."""
    import subprocess
    text = (ROOT/'scripts/warp_flow_episode.py').read_text()
    sha = next(l.split("'")[1] for l in text.splitlines() if l.startswith('ADAPTER_SHA = '))
    try:
        src = subprocess.check_output(['git', 'show', f'{sha}:scripts/run_beampair1.py'], cwd=ROOT, text=True,
                                      stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.fail(f'pinned adapter {sha} not in this clone: git fetch origin {sha} (not skippable)')
    ns = {}
    exec(compile(text, str(ROOT/'scripts/warp_flow_episode.py'), 'exec'), ns)
    _, audit = ns['compile_function'](src, 'run', {})
    assert audit['edits']['runner_call'] == 1


def test_derive_rejects_other_cases_file():
    with pytest.raises(ValueError, match='hash mismatch'):
        p2.derive(b'[]')


def test_derive_changes_only_candidate(monkeypatch):
    cases = [{'plan': {'seed': 8420000 + i, 'scene_profile': 'walls_floor_contrast_v5_indigo110_s80'},
              'candidate': 'beamact5_r13'} for i in range(40)]
    raw = json.dumps(cases).encode()
    monkeypatch.setattr(p2, 'R13_CASES_SHA256', hashlib.sha256(raw).hexdigest())
    out = p2.derive(raw)
    assert [c['source_world_index'] for c in out] == [1, 11, 17]
    assert all(c['candidate'] == 'pairact_p2_r13' for c in out)
    assert [c['plan'] for c in out] == [cases[i]['plan'] for i in (1, 11, 17)]


def test_smoke_worlds_are_fastest_r13_grasps():
    # SMOKE.md §2 rule on the committed attempt-1 funnel: sim 22.8 / 24.3 / 25.2.
    assert p2.select_worlds(p2.load_funnel()) == (1, 11, 17)


def test_select_worlds_tie_breaks_by_case_and_skips_failures():
    funnel = {'per_case': [
        {'case': 9, 'sim': 20.0, 'succ': True}, {'case': 4, 'sim': 20.0, 'succ': True},
        {'case': 2, 'sim': 10.0, 'succ': False}, {'case': 7, 'sim': 30.0, 'succ': True},
        {'case': 8, 'sim': 40.0, 'succ': True}]}
    assert p2.select_worlds(funnel) == (4, 9, 7)


def test_attempt2_agrees_on_the_same_three_worlds():
    funnel = json.loads((ROOT/'experiments/2026-10-21-pairact-p2/r13-funnel-attempt2.json').read_text())
    assert p2.select_worlds(funnel) == (1, 11, 17)


# ------------------------------------------------------------ P5 student eval

def _runner_module():
    import sys
    sys.path.insert(0, str(ROOT/'scripts'))
    spec = importlib.util.spec_from_file_location('p2runner', ROOT/'scripts/run_warp_flow_teacher.py')
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as error:
        pytest.skip(f'root runner imports unavailable here: {error}')
    return mod


CFG = {'mode': 'pairact_r1_student_eval_v1', 'python': '/venv/bin/python', 'source': '/src/student',
       'model': '/runs/ckpt', 'config': '/src/student/cfg.json', 'device': 'cuda'}


def test_student_eval_config_is_exact_absolute_and_pinned(tmp_path, monkeypatch):
    mod = _runner_module()
    assert mod.load_student_eval(None) is None
    path = tmp_path/'s.json'
    monkeypatch.setattr(mod, 'source_head', lambda p: mod.STUDENT_SHA)
    path.write_text(json.dumps(CFG))
    assert mod.load_student_eval(path) == CFG
    for bad in ({**CFG, 'gt_pose': True}, {**CFG, 'model': 'rel/ckpt'}, {**CFG, 'mode': 'x'}):
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            mod.load_student_eval(path)
    path.write_text(json.dumps(CFG))
    monkeypatch.setattr(mod, 'source_head', lambda p: '0'*40)
    with pytest.raises(ValueError, match='pinned'):
        mod.load_student_eval(path)


def test_student_eval_default_off_and_injected_only_when_set():
    runner = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    episode = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "p.add_argument('--student-eval',type=Path" in runner and 'default OFF' in runner
    assert "student_eval=None, hybrid_carry=None, hybrid_smoke=None):" in episode and 'bridge.student_eval = student_eval' in episode
    assert "if self.student_eval is not None:" in episode
    assert "STUDENT_SHA='3c9337d5f5c9deefd49139b26ae7117022e3d5cc'" in runner


def test_collect_root_changes_only_the_two_pins():
    import subprocess
    base = '0e60345d7e71b9249dc5317fa02d16ea6ab1ff55'     # dsh/pairact-p2-carrypath-r (pinned, not a ref)
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'diff', '-U0', base, '--', 'scripts/'],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        pytest.fail(f'base commit {base} unavailable ({error}): git fetch origin {base} (not skippable, audit 4)')
    removed = sorted(l for l in out.splitlines() if l.startswith('-') and not l.startswith('---'))
    # -r-c5-hybrid: collection still runs from -r-c5 (two pins only). The hybrid root additionally edits
    # exactly these five lines (student pin parameter, hybrid keyword threading); everything else is added.
    hybrid_edits = ["-def load_student_eval(path):",
                    "-    if head!=STUDENT_SHA:raise ValueError(f'student worker source {head} != pinned {STUDENT_SHA}')",
                    "-    student_eval=load_student_eval(a.student_eval)",
                    "-                candidate=case.get('candidate','baseline'),student_eval=student_eval)",
                    "-def make_lane(adapter_source, teacher_source, plan, out, hooks, index, cap_s, *, flow='beampair', "
                    "profile=None, canonical=None, candidate='baseline', student_eval=None):"]
    assert removed == sorted(["-ADAPTER_SHA = '6843fcaa94785e46ee52ef1889e392ca988d604d'",
                              "-TEACHER_SHA = '59299f903f4a2f9a2eabe5ff0e442e0ce25e8266'"] + hybrid_edits)


# ------------------------------------------------- -c3 detour pilot cases

def test_derive_to_detour_candidate_changes_only_candidate(monkeypatch):
    cases = [{'plan': {'seed': 8420000 + i}, 'candidate': 'beamact5_r13'} for i in range(40)]
    raw = json.dumps(cases).encode()
    monkeypatch.setattr(p2, 'R13_CASES_SHA256', hashlib.sha256(raw).hexdigest())
    assert p2.derive(raw) == p2.derive(raw, to='pairact_p2_r13')          # default unchanged
    for to in ('pairact_p2_r13_detour', 'pairact_p3_collect_detour'):
        out = p2.derive(raw, to=to)
        assert all(c['candidate'] == to for c in out)
        assert [c['plan'] for c in out] == [cases[i]['plan'] for i in (1, 11, 17)]
    with pytest.raises(ValueError, match='candidate'):
        p2.derive(raw, to='bogus')


def test_pinned_adapter_has_the_detour_candidates():
    import subprocess
    text = (ROOT/'scripts/warp_flow_episode.py').read_text()
    sha = next(l.split("'")[1] for l in text.splitlines() if l.startswith('ADAPTER_SHA = '))
    try:
        src = subprocess.check_output(['git', 'show', f'{sha}:scripts/run_beampair1.py'], cwd=ROOT, text=True,
                                      stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.fail(f'pinned adapter {sha} not in this clone: git fetch origin {sha} (not skippable)')
    assert "if candidate=='pairact_p2_r13_detour':" in src and "'carry_route':'detour_v1'" in src
    assert "COLLECT_CANDIDATES=(COLLECT_CANDIDATE,'pairact_p3_collect_detour')" in src


# ------------------------------------------------- hybrid carry (arm N, default off)

HYB = {'mode': 'pairact_r1_hybrid_carry_v2', 'carry_mode': 'nav',
       'nav': {'source': '/src/nav', 'sha': 'ceacd474b9e03110c1b35c0cd0fc2cca40594ec9'}}


def test_hybrid_pins_and_default_off():
    runner = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    episode = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "HYBRID_ADAPTER_SHA = '0479e7b47c87e0a5af7158015d011d98ca5df449'" in episode    # -a-c5-hybrid2
    assert "HYBRID_TEACHER_SHA = 'c51f3e7c2cd419c3fe9ef4199481ffc1c5f74fea'" in episode    # -c5-hybrid2
    assert "HYBRID_STUDENT_SHA='bdc41a3fa8ec151889a1c6559147f495a9619dad'" in runner      # p5-student-hybrid
    assert "HYBRID_MAP_MODE_APPROVED=False" in runner
    assert "p.add_argument('--hybrid-carry',type=Path" in runner and 'default OFF' in runner
    assert "if self.hybrid_carry is not None:" in episode
    # default path keeps the -c5 pins
    assert "ADAPTER_SHA = '3779d9615ef6dc8e38f57ab968a14a9e45189ecc'" in episode
    assert "STUDENT_SHA='3c9337d5f5c9deefd49139b26ae7117022e3d5cc'" in runner


def test_hybrid_config_needs_student_eval_nav_pin_and_refuses_map(tmp_path, monkeypatch):
    mod = _runner_module()
    path = tmp_path/'h.json'
    path.write_text(json.dumps(HYB))
    assert mod.load_hybrid_carry(None, CFG) is None
    with pytest.raises(ValueError, match='student-eval'):
        mod.load_hybrid_carry(path, None)
    monkeypatch.setattr(mod, 'source_head', lambda p: mod.HYBRID_NAV_SHA)
    assert mod.load_hybrid_carry(path, CFG)['carry_mode'] == 'nav'
    monkeypatch.setattr(mod, 'source_head', lambda p: '0'*40)
    with pytest.raises(ValueError, match='nav detector tree'):
        mod.load_hybrid_carry(path, CFG)
    path.write_text(json.dumps(dict(HYB, carry_mode='map', nav=None)))
    with pytest.raises(PermissionError, match='owner'):
        mod.load_hybrid_carry(path, CFG)
    path.write_text(json.dumps(dict(HYB, nav={'source': 'rel', 'sha': mod.HYBRID_NAV_SHA})))
    with pytest.raises(ValueError, match='absolute'):
        mod.load_hybrid_carry(path, CFG)


def test_hybrid_student_pin_is_used_with_hybrid_flag(tmp_path, monkeypatch):
    mod = _runner_module()
    path = tmp_path/'s.json'; path.write_text(json.dumps(CFG))
    monkeypatch.setattr(mod, 'source_head', lambda p: mod.HYBRID_STUDENT_SHA)
    assert mod.load_student_eval(path, mod.HYBRID_STUDENT_SHA) == CFG
    with pytest.raises(ValueError, match='pinned'):
        mod.load_student_eval(path)


def test_hybrid_template_is_the_teacher_v2_template():
    # v2: the template lives next to the fit tool in the teacher tree; root keeps no stale copy
    assert not (ROOT/'experiments/2026-10-21-pairact-p2/HYBRID_CARRY_NAV_TEMPLATE.json').exists()
    doc = (ROOT/'experiments/2026-10-21-pairact-p2/HYBRID_RUN.md').read_text()
    assert 'HYBRID_CARRY_NAV_TEMPLATE_V2.json' in doc and 'fit_loaded_odom.py' in doc


# ------------------------------------------------- hybrid code-carry smoke (teacher near field, default off)

# teacher c51f3e7c harness/hybrid_carry.calibration_values_sha256 of the fixture below (computed in that tree)
VALUES_SHA_FIXTURE = 'ed5dcf7c60bcdd93c893e64275214c955d515abadcd48a72d9800cc617522378'
PROV = {'tool': 'scripts/fit_loaded_odom.py + scripts/make_hybrid_config.py', 'fit_quality': 'per_tick'}
SMOKE = dict(HYB, shadow_predict=False, calibration_provenance=PROV)


def test_hybrid_smoke_flag_default_off_and_threaded():
    runner = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    episode = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "p.add_argument('--hybrid-smoke',type=Path" in runner and 'not learned' in runner
    assert "HYBRID_SMOKE_LABEL='teacher 근거리 + 코드 운반, 학습 아님'" in runner
    assert "if self.hybrid_smoke is not None:" in episode and 'bridge.hybrid_smoke = hybrid_smoke' in episode
    assert "if hybrid_carry is not None or hybrid_smoke is not None:" in runner      # hybrid2 stack pins


def test_hybrid_smoke_config_checks(tmp_path, monkeypatch):
    mod = _runner_module()
    path = tmp_path/'s.json'
    assert mod.load_hybrid_smoke(None, None, None) is None
    path.write_text(json.dumps(SMOKE))
    with pytest.raises(ValueError, match='no student'):
        mod.load_hybrid_smoke(path, CFG, None)
    with pytest.raises(ValueError, match='no student'):
        mod.load_hybrid_smoke(path, None, HYB)
    monkeypatch.setattr(mod, 'source_head', lambda p: mod.HYBRID_NAV_SHA)
    assert mod.load_hybrid_smoke(path, None, None)['carry_mode'] == 'nav'
    for bad, why in ((dict(SMOKE, mode='pairact_r1_hybrid_carry_v1'), 'mode'), (dict(SMOKE, shadow_predict=True), 'shadow'),
                     (dict(SMOKE, calibration_provenance=dict(PROV, tool='hand')), 'fit_loaded_odom'),
                     (dict(SMOKE, calibration_provenance=None), 'fit_loaded_odom'),
                     (dict(SMOKE, carry_mode='map'), 'nav')):
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match=why):
            mod.load_hybrid_smoke(path, None, None)
    path.write_text(json.dumps(SMOKE))
    monkeypatch.setattr(mod, 'source_head', lambda p: '0'*40)
    with pytest.raises(ValueError, match='nav detector tree'):
        mod.load_hybrid_smoke(path, None, None)


def test_values_hash_literal_matches_the_teacher_tree():
    # same canonical form as teacher harness/hybrid_carry.calibration_values_sha256 (tests/test_fit_loaded_odom.py)
    cal = {'forward_m_per_pct_s': .0036, 'lateral_m_per_pct_s': .0031, 'yaw_deg_per_pct_s': .82, 'latency_ticks': 1,
           'forward_bias_m_per_s': .002, 'lateral_bias_m_per_s': -.001, 'yaw_bias_deg_per_s': .3}
    lim = {'sigma_xy_per_m': .05, 'sigma_yaw_per_rad': .1}
    got = hashlib.sha256(json.dumps({'calibration': cal, 'sigma': lim}, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()
    assert got == VALUES_SHA_FIXTURE
