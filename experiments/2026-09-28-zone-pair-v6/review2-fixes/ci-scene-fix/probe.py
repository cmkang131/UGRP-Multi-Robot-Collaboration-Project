"""Read-only scene/catalogue provenance and sparse-input audit; no world construction."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
opened = set()
def audit(event, args):
    if event == 'open' and isinstance(args[0], str):
        path = Path(args[0]).resolve()
        if path.is_relative_to(ROOT):
            opened.add(str(path.relative_to(ROOT)))
sys.addaudithook(audit)
from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_dev_runtime import make_scene
from scripts.zone_pair_registered_source import committed_blob, verify_registered_source
from sim.zone_cargo import catalogue_record
from sim import zone_tagged_cargo_scene as tagged

receipt = verify_registered_source(dev.PREREG_V5B)
p = json.loads(committed_blob(str(ROOT), receipt['source_commit'], receipt['registration_path']))
catalogue_path = 'experiments/2026-09-25-zone-cargo-catalogue/results.json'
blob = committed_blob(str(ROOT), receipt['source_commit'], catalogue_path)
archived = json.loads(blob)['catalogue']
native = catalogue_record()
alternate = copy.deepcopy(archived)
center = alternate['kinds']['tri_frame']['parts'][0]['center']
old = center[1]
center[1] = math.nextafter(old, math.inf)
alternate['sha256'] = hashlib.sha256(json.dumps(
    {k: v for k, v in alternate.items() if k != 'sha256'}, sort_keys=True).encode()).hexdigest()
rows = []
for label, catalogue in [('native', native), ('registered', archived), ('one_ulp', alternate)]:
    tagged.catalogue_record = lambda: copy.deepcopy(catalogue)
    for case in p['runs']:
        scene = make_scene({'map': p['environment']['map'], 'seed': case['seed'], 'goal': {'B': {'cyan': 1}},
                            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': case['setup_beam_xyyaw']}]})
        row = {'catalogue': label, 'run': case['id'], 'resolved_sha256': scene.record()['resolved_sha256'],
               'registered_sha256': p['scene_instances'][case['id']]['resolved_sha256']}
        comparable = copy.deepcopy(scene.config)
        comparable['cargo_set']['catalogue_sha256'] = archived['sha256']
        row['only_catalogue_differs'] = dev.digest({'config': comparable, 'map': scene.map}) == row['registered_sha256']
        assert row['only_catalogue_differs']
        try:
            dev.validate_scene(p, scene)
            row['scene_guard'] = 'accepted'
        except ValueError as exc:
            row['scene_guard'] = str(exc)
        rows.append(row)
tagged.catalogue_record = catalogue_record
sparse = {line[2:] for line in subprocess.check_output(['git', 'ls-files', '-t'], cwd=ROOT, text=True).splitlines()
          if line.startswith('S ')}
assert not opened & sparse
assert all((ROOT / path).exists() for path in opened)
assert not any(Path(path).suffix in {'.py', '.json'} for path in sparse)
sizes = {}
for line in subprocess.check_output(['git', 'ls-tree', '-rl', 'HEAD'], cwd=ROOT, text=True).splitlines():
    fields, path = line.split('\t')
    if path in sparse:
        sizes[path] = int(fields.split()[3])
result = {'source_commit': receipt['source_commit'], 'registration_sha256': receipt['registration_sha256'],
          'catalogue_blob': {'path': catalogue_path,
                             'sha256': hashlib.sha256(blob).hexdigest(), 'commit': receipt['source_commit']},
          'native_catalogue_sha256': native['sha256'], 'registered_catalogue_sha256': archived['sha256'],
          'perturbed_catalogue_sha256': alternate['sha256'],
          'perturbation': {'field': 'kinds.tri_frame.parts[0].center[1]', 'before': old, 'after': center[1],
                           'scope': 'one-ULP portability counterexample, not measured Ubuntu libm output'},
          'scenes': rows, 'sparse_omitted_files': len(sparse), 'sparse_omitted_bytes': sum(sizes.values()),
          'missing_scene_inputs': [], 'scene_read_paths': sorted(opened),
          'full_checkout_hydration': 'not needed for scene inputs; all accessed files already present; omitted files are media/archives',
          'native_ubuntu_run': False, 'physics_steps': 0, 'model_calls': 0}
(Path(__file__).parent / 'diagnosis.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'scene_read_paths'}, indent=2))
