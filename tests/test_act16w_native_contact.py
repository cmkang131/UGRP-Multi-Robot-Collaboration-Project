"""Source/profile boundaries only; no simulator, renderer or GPU imports."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

from sim.warp_native_contact import apply

ROOT = Path(__file__).resolve().parents[1]


def test_profile_bytes_and_xml_options_are_pinned():
    assert hashlib.sha256((ROOT/'sim/warp_native_contact.py').read_bytes()).hexdigest() == 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
    import xml.etree.ElementTree as ET
    source = '<mujoco><option noslip_iterations="10" iterations="80" ls_iterations="50" tolerance="1e-8"/><worldbody/></mujoco>'
    option = ET.fromstring(apply(source, 'warp_native_contact_v1')).find('option').attrib
    assert option == dict(noslip_iterations='0', iterations='80', ls_iterations='50',
                         tolerance='1e-8', cone='elliptic', integrator='implicitfast', impratio='5')
    assert apply(source) == source


def test_private_initialize_has_only_two_native_guard_changes_and_receipt():
    original = subprocess.check_output(['git', 'show', 'f0db6b1abb842ea65b71c433738210254f300a7c:scripts/warp_act_backend.py'], cwd=ROOT, text=True)
    private = (ROOT/'scripts/act16w_native_contact.py').read_text()
    def initialize(text, cls):
        node = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == cls)
        return next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == 'initialize')
    a, b = initialize(original, 'WarpTransport'), initialize(private, 'NativeTransport')
    # Receipt writing is the only appended operation; no physics work is hidden after it.
    assert ast.unparse(b.body[-1]).startswith("(self.out / 'native-contact.json').write_text")
    b.body.pop()
    wanted = ast.unparse(a).replace('model.opt.noslip_iterations != 10', 'model.opt.noslip_iterations != 0').replace('self.wm.opt.noslip_iterations != 10', 'self.wm.opt.noslip_iterations != 0').replace('noslip10 / weld OFF required in every world', 'native contact noslip0 / weld OFF required in every world').replace('noslip lost in Warp conversion', 'native noslip0 lost in Warp conversion')
    assert ast.unparse(b) == wanted


def test_native_gate_train_validation_and_final_starts_are_disjoint():
    p = json.loads((ROOT/'experiments/2026-10-16-act16w/resume3/protocol.json').read_text())
    sets = [set(p[key]) for key in ('gate_seeds', 'train_seeds', 'validation_seeds', 'final_evaluation_seeds')]
    assert all(not a & b for i, a in enumerate(sets) for b in sets[i+1:])
    assert len(sets[0]) == len(sets[3]) == 40
    assert len(sets[1]) == 32 and len(sets[2]) == 8
    assert set(p['dagger_train_seeds']) <= sets[1] and len(p['dagger_train_seeds']) == 20
    assert not set.union(*sets[:3]) & (set(range(86820, 86870)) | set(range(8317100, 8317140)))


def test_native_recount_uses_all_original_results_and_requires_zero_audit(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    from act16w_native_stage import recount
    refs = tmp_path/'refs'; refs.mkdir()
    out = tmp_path/'run'; controller = out/'group-00/controller'; controller.mkdir(parents=True)
    (refs/'plans.json').write_text(json.dumps(dict(episodes=[dict(seed=87220+i, kind=('cyan','red','green','yellow')[i%4]) for i in range(40)])))
    (controller/'native-contact.json').write_text(json.dumps(dict(gpu_noslip=0, cpu_noslip=[0]*40, cpu_impratio=5)))
    value = dict(status='complete', physical_success=True, cap_end=False, training_rgb=False,
                 lift_success=True, release_success=True, input_audit=dict(invisible_measurements=0, held_world_reads=0))
    for i in range(40):
        folder = controller/f'world-{i:03d}'; folder.mkdir(); (folder/'result.json').write_text(json.dumps(value))
    assert recount(out, refs, [(0,list(range(40)))])['passed']
    for i in (0, 1):
        (controller/f'world-{i:03d}/result.json').write_text(json.dumps({**value, 'physical_success': False}))
    r = recount(out, refs, [(0,list(range(40)))])
    assert (r['n'],r['N'],r['passed']) == (38,40,True)
    (controller/'world-002/result.json').write_text(json.dumps({**value, 'input_audit':dict(invisible_measurements=1, held_world_reads=0)}))
    r = recount(out, refs, [(0,list(range(40)))])
    assert (r['n'],r['N'],r['passed']) == (37,40,False)
    (controller/'world-039/result.json').unlink()
    r = recount(out, refs, [(0,list(range(40)))])
    assert r['N'] == 40 and not r['complete'] and not r['passed']
