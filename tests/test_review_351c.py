"""Independent scoped clock re-review against an archived PR #351 candidate.

Set REVIEW_351_ROOT as in test_review_351.py. These cases rewrite synthetic
JSONL plus its manifest, so rejection cannot come from a stale artifact hash.
No simulation, rendering, real collection or model invocation is involved.
"""
import pytest

from test_review_351 import probe


@pytest.mark.parametrize('record', [
    'pose', 'frame', 'label', 'initial_servo_command', 'arm', 'look',
    'mecanum', 'beam', 'contact', 'unknown_command',
])
def test_real_jsonl_clock_types_fail_closed_with_current_manifest(tmp_path, record):
    result = probe("""
record = """ + repr(record) + """
collection = fixture.synthetic_collection(tmp/'actual', 'loaded')
folder = collection/raw.MAP_ID
paths = {'pose':'eval_only/r1/pose.jsonl', 'frame':'robots/r1/frames.jsonl',
         'label':'eval_only/r1/camera_labels.jsonl', 'beam':'eval_only/trajectory.jsonl',
         'contact':'eval_only/contacts.jsonl'}
path = folder/paths.get(record, 'robots/r1/commands.jsonl')
original = path.read_bytes()
gate = json.loads(a.CRITERION.read_text())['loaded_selection']
def audit():
    inputs = raw.Inputs()
    data = raw.load_collection(collection, 'loaded', inputs)
    valid, _ = raw.loaded_mask(data, inputs, gate)
    inputs.verify()
    return bool(valid.all())
control = audit()
cases = []
values = [('numeric_string','1.3'), ('nan_string','NaN'), ('true',True),
          ('false',False), ('null',None), ('nan',float('nan')),
          ('inf',float('inf')), ('negative_inf',-float('inf')), ('missing',None)]
for name,value in values:
    rows = [json.loads(line) for line in original.splitlines()]
    if record == 'unknown_command':
        target = {'kind':'unknown_command', 't':1.3}
        rows.append(target)
    else:
        selected = rows if record in paths else [r for r in rows if r['kind'] == record]
        target = selected[len(selected)//2]
    if name == 'missing':
        target.pop('t')
    else:
        target['t'] = value
    path.write_text(''.join(json.dumps(row)+'\\n' for row in rows))
    fixture.refresh_manifest(folder)
    try:
        audit()
    except ValueError as exc:
        cases.append({'case':name, 'rejected':True, 'reason':str(exc)})
    else:
        cases.append({'case':name, 'rejected':False})
path.write_bytes(original)
fixture.refresh_manifest(folder)
print(json.dumps({'record':record, 'control':control, 'restored_control':audit(), 'cases':cases}))
""", tmp_path)
    assert result['control'] and result['restored_control'], result
    assert len(result['cases']) == 9, result
    assert all(case['rejected'] and 'finite numeric time' in case['reason']
               for case in result['cases']), result


@pytest.mark.parametrize('record', ['pose', 'frame', 'label', 'command', 'beam', 'contact', 'schedule'])
def test_reversed_and_duplicate_sample_clocks_fail_closed(tmp_path, record):
    result = probe("""
record = """ + repr(record) + """
collection = fixture.synthetic_collection(tmp/'actual', 'loaded')
folder = collection/raw.MAP_ID
paths = {'pose':'eval_only/r2/pose.jsonl', 'frame':'robots/r2/frames.jsonl',
         'label':'eval_only/r2/camera_labels.jsonl', 'command':'robots/r2/commands.jsonl',
         'beam':'eval_only/trajectory.jsonl', 'contact':'eval_only/contacts.jsonl',
         'schedule':'inputs/schedule.json'}
path = folder/paths[record]
original = path.read_bytes()
gate = json.loads(a.CRITERION.read_text())['loaded_selection']
def audit():
    inputs = raw.Inputs()
    data = raw.load_collection(collection, 'loaded', inputs)
    valid, _ = raw.loaded_mask(data, inputs, gate)
    inputs.verify()
    return bool(valid.all())
control = audit()
cases = []
for mode in ('reverse_times', 'duplicate_time', 'reverse_rows'):
    rows = json.loads(original) if record == 'schedule' else [json.loads(line) for line in original.splitlines()]
    i = next(i for i in range(1, len(rows)-1) if rows[i]['t'] < rows[i+1]['t'])
    if mode == 'reverse_times':
        rows[i]['t'], rows[i+1]['t'] = rows[i+1]['t'], rows[i]['t']
    elif mode == 'duplicate_time':
        rows[i+1]['t'] = rows[i]['t']
    else:
        rows[i], rows[i+1] = rows[i+1], rows[i]
    path.write_text(json.dumps(rows) if record == 'schedule' else ''.join(json.dumps(row)+'\\n' for row in rows))
    fixture.refresh_manifest(folder)
    try:
        audit()
    except ValueError as exc:
        cases.append({'case':mode, 'rejected':True, 'reason':str(exc)})
    else:
        cases.append({'case':mode, 'rejected':False})
path.write_bytes(original)
fixture.refresh_manifest(folder)
print(json.dumps({'record':record, 'control':control, 'restored_control':audit(), 'cases':cases}))
""", tmp_path)
    assert result['control'] and result['restored_control'], result
    assert len(result['cases']) == 3 and all(case['rejected'] for case in result['cases']), result


@pytest.mark.parametrize('profile', ['unloaded', 'fine', 'loaded'])
def test_finite_initial_clock_offsets_fail_closed(tmp_path, profile):
    result = probe("""
profile = """ + repr(profile) + """
collection = fixture.synthetic_collection(tmp/'actual', profile)
folder = collection/raw.MAP_ID
cases = []
for rid in ('r1','r2'):
    path = folder/f'robots/{rid}/commands.jsonl'
    original = path.read_bytes()
    for offset in (-.05, .05):
        rows = [json.loads(line) for line in original.splitlines()]
        rows[0]['t'] += offset
        path.write_text(''.join(json.dumps(row)+'\\n' for row in rows))
        fixture.refresh_manifest(folder)
        try:
            inputs = raw.Inputs()
            raw.load_collection(collection, profile, inputs)
            inputs.verify()
        except ValueError as exc:
            cases.append({'robot':rid, 'offset':offset, 'rejected':True, 'reason':str(exc)})
        else:
            cases.append({'robot':rid, 'offset':offset, 'rejected':False})
    path.write_bytes(original)
    fixture.refresh_manifest(folder)
inputs = raw.Inputs()
raw.load_collection(collection, profile, inputs)
inputs.verify()
print(json.dumps({'profile':profile, 'restored_control':True, 'cases':cases}))
""", tmp_path)
    assert result['restored_control'], result
    assert len(result['cases']) == 4 and all(case['rejected'] for case in result['cases']), result
