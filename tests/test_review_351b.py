"""Offline regressions ported from PR #351 re-review a1ed666f.

Use the guarded subprocess against this checkout. All 18 reviewer cases,
including the four former strict xfails, must pass.
"""
import pytest

from tests.test_review_351 import probe


@pytest.mark.parametrize('kind', ['root', 'collection', 'case', 'nested', 'incomplete'])
def test_resolved_relative_input_and_output_aliases_do_not_overlap(tmp_path, kind):
    result = probe("""
import os
collection = fixture.synthetic_collection(tmp/'actual', 'unloaded')
view = tmp/'view'
view.mkdir()
kind = """ + repr(kind) + """
target = collection
if kind == 'root':
    (view/'root').symlink_to(collection.parent, target_is_directory=True)
    root = view/'root'
elif kind in ('collection', 'incomplete'):
    (view/'calibration-unloaded').symlink_to(collection, target_is_directory=True)
    root = view
    if kind == 'incomplete':
        (collection/'result.json').unlink()
elif kind == 'case':
    (view/'calibration-unloaded').mkdir()
    (view/'calibration-unloaded'/raw.MAP_ID).symlink_to(collection/raw.MAP_ID, target_is_directory=True)
    # An incomplete collection's case is still protected.
    root, target = view, collection/raw.MAP_ID
else:
    target = tmp/'external-evidence'
    target.mkdir()
    (collection/'extra-input').symlink_to(target, target_is_directory=True)
    root = collection.parent
(view/'output-link').symlink_to(target, target_is_directory=True)
output = view/'output-link'/'new-output'
try:
    a.run(os.path.relpath(root), os.path.relpath(output))
except ValueError as exc:
    rejected, reason = True, str(exc)
else:
    rejected, reason = False, None
print(json.dumps({'rejected':rejected, 'reason':reason, 'created':output.exists()}))
""", tmp_path)
    assert result['rejected'] and 'overlap' in result['reason'] and not result['created'], result


def test_deadband_variants_need_both_robots_and_full_horizons(tmp_path):
    result = probe("""
import copy
gate = b.criterion()
data, fields = fixture.synthetic_data('loaded', loaded=True)
fields['deadband'] = {'c0':[.008,.011,.014], 'u1':[.029,.034,.039]}
data['pose'] = motion.path_of(motion.increments(data, fields))
partner = copy.deepcopy(data)
partner['u'] *= -1
partner['pose'] = motion.path_of(motion.increments(partner, fields))
_, control = motion.fit_shared([data,partner], gate, deadband=True)
rejections = []
for case in ('one_robot', 'long_horizon', 'coast_only', 'fine_commands', 'unloaded_commands'):
    damaged = copy.deepcopy(partner)
    if case in ('fine_commands','unloaded_commands'):
        damaged, _ = fixture.synthetic_data(case.split('_')[0], loaded=True)
    else:
        spans = damaged['segments']['forward']['steps']
        selected = []
        for start,end in spans:
            if abs(damaged['u'][start,0]-.006) < 1e-12:
                if case == 'one_robot':
                    continue
                if case == 'long_horizon':
                    end = start+40
                else:
                    start = end-20
            selected.append((start,end))
        damaged['segments']['forward']['steps'] = selected
    try:
        motion.fit_shared([data,damaged], gate, deadband=True)
    except ValueError as exc:
        rejections.append({'case':case,'rejected':True,'reason':str(exc)})
    else:
        rejections.append({'case':case,'rejected':False})
print(json.dumps({'control':control['success'],'cases':rejections}))
""", tmp_path)
    assert result['control'] and all(row['rejected'] for row in result['cases']), result


@pytest.mark.parametrize('record', ['pose', 'command', 'frame', 'label', 'beam', 'contact'])
def test_nonfinite_times_in_each_sample_record_fail_closed(tmp_path, record):
    result = probe("""
record = """ + repr(record) + """
profile = 'loaded' if record == 'command' else 'unloaded'
collection = fixture.synthetic_collection(tmp/'actual', profile)
rejections = []
for rid in ('r1','r2'):
    for value in (float('nan'),float('inf'),-float('inf')):
        class BadTime(raw.Inputs):
            def rows(self,path):
                rows = super().rows(path)
                paths = {'pose':f'eval_only/{rid}/pose.jsonl',
                         'command':f'robots/{rid}/commands.jsonl',
                         'frame':f'robots/{rid}/frames.jsonl',
                         'label':f'eval_only/{rid}/camera_labels.jsonl',
                         'beam':'eval_only/trajectory.jsonl', 'contact':'eval_only/contacts.jsonl'}
                if path == collection/raw.MAP_ID/paths[record]:
                    rows[1 if record == 'command' else 0]['t'] = value
                return rows
        try:
            inputs = BadTime()
            data = raw.load_collection(collection,profile,inputs)
            if record in ('beam','contact'):
                raw.loaded_mask(data,inputs,json.loads(a.CRITERION.read_text())['loaded_selection'])
        except ValueError as exc:
            rejections.append({'robot':rid,'time':str(value),'rejected':True,'reason':str(exc)})
        else:
            rejections.append({'robot':rid,'time':str(value),'rejected':False})
print(json.dumps({'record':record,'cases':rejections}))
""", tmp_path)
    assert all(row['rejected'] for row in result['cases']), result


@pytest.mark.parametrize('profile', ['unloaded', 'fine', 'loaded'])
def test_initial_command_nan_is_rejected_from_real_jsonl(tmp_path, profile):
    result = probe("""
profile = """ + repr(profile) + """
collection = fixture.synthetic_collection(tmp/'actual', profile)
folder = collection/raw.MAP_ID
results = []
for rid in ('r1','r2'):
    path = folder/f'robots/{rid}/commands.jsonl'
    original = path.read_bytes()
    rows = [json.loads(line) for line in original.splitlines()]
    rows[0]['t'] = float('nan')
    path.write_text(''.join(json.dumps(row)+'\\n' for row in rows))
    fixture.refresh_manifest(folder)
    inputs = raw.Inputs()
    try:
        data = raw.load_collection(collection,profile,inputs)
        inputs.verify()
    except ValueError as exc:
        results.append({'robot':rid,'rejected':True,'reason':str(exc)})
    else:
        results.append({'robot':rid,'rejected':False,
                        'initial_time_finite':bool(np.isfinite(data['robots'][rid]['commands'][0]['t']))})
    path.write_bytes(original)
    fixture.refresh_manifest(folder)
print(json.dumps({'profile':profile,'cases':results}))
""", tmp_path)
    assert all(row['rejected'] for row in result['cases']), result


def test_initial_command_infinities_are_rejected(tmp_path):
    result = probe("""
collection = fixture.synthetic_collection(tmp/'actual', 'unloaded')
cases = []
for rid in ('r1','r2'):
    for value in (float('inf'),-float('inf')):
        class BadInitialTime(raw.Inputs):
            def rows(self,path):
                rows = super().rows(path)
                if path == collection/raw.MAP_ID/f'robots/{rid}/commands.jsonl':
                    rows[0]['t'] = value
                return rows
        try:
            raw.load_collection(collection,'unloaded',BadInitialTime())
        except ValueError as exc:
            cases.append({'robot':rid,'time':str(value),'rejected':True,'reason':str(exc)})
        else:
            cases.append({'robot':rid,'time':str(value),'rejected':False})
print(json.dumps({'cases':cases}))
""", tmp_path)
    assert all(row['rejected'] for row in result['cases']), result


def test_initial_nan_cannot_produce_accepted_fine_section(tmp_path):
    result = probe("""
collection = fixture.synthetic_collection(tmp/'actual','fine')
folder = collection/raw.MAP_ID
path = folder/'robots/r1/commands.jsonl'
rows = [json.loads(line) for line in path.read_text().splitlines()]
rows[0]['t'] = float('nan')
path.write_text(''.join(json.dumps(row)+'\\n' for row in rows))
fixture.refresh_manifest(folder)
output = tmp/'output'
cal = a.run(collection.parent,output)
report = json.loads((output/'fit_report.json').read_text())
print(json.dumps({'status':cal['status'],'fine_audit':report['fine']['collection_audit'],
                  'fine_motion_accepted':report['fine'].get('motion',{}).get('accepted',False),
                  'fine_gain':cal['params']['motion_profiles']['fine']['gain']}))
""", tmp_path)
    assert result['fine_audit'] == 'FAIL' and not result['fine_motion_accepted'] and result['fine_gain'] is None, result


def test_all_three_two_door_collections_remain_partial(tmp_path):
    result = probe("""
for profile in ('unloaded','fine','loaded'):
    fixture.synthetic_collection(tmp/'actual',profile)
output = tmp/'output'
cal = a.run(tmp/'actual',output)
report = json.loads((output/'fit_report.json').read_text())
print(json.dumps({'status':cal['status'],
    'audits':{p:report[p]['collection_audit'] for p in ('unloaded','fine','loaded')},
    'axis_pass':report['unloaded']['criterion_B']['axis_pass'],
    'missing_unloaded':[row for row in cal['missing'] if row['field'].startswith('params.motion.')]}))
""", tmp_path)
    assert result['status'] == 'PARTIAL' and set(result['audits'].values()) == {'PASS'}, result
    assert all(value is None for value in result['axis_pass'].values()), result
    assert result['missing_unloaded'] and all('frozen criterion B' in row['reason'] for row in result['missing_unloaded']), result
