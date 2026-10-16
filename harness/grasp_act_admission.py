"""Recording admission tied to the measured executable and frozen gate plan."""
import hashlib
from pathlib import Path

CRITERIA={'min_z_m':.012,'max_tilt_deg':10.,'hold_s':3.}

def recording_admission(gate,*,source_sha,teacher_profile,gate_plan):
    digest=hashlib.sha256(Path(gate_plan).read_bytes()).hexdigest()
    if gate.get('qualified') is not True or gate.get('N',0)<40 or gate.get('n',0)/max(1,gate.get('N',0))<.95:
        raise ValueError('qualified >=38/40 teacher gate required')
    for key,value in {'source_sha':source_sha,'teacher_profile':teacher_profile,'plan_sha256':digest,
                      'object_kind':'long_beam','criteria':CRITERIA,'self_pose_source':'issued'}.items():
        if gate.get(key)!=value:raise ValueError('recording gate mismatch: '+key)
    completed=[r for r in gate.get('rows',[]) if r.get('status')=='complete' and r.get('exit')==0]
    if len(completed)!=gate['N'] or sum(r.get('physical_success') is True for r in completed)!=gate['n']:
        raise ValueError('recording gate denominator mismatch')
    if any(r.get('source_sha')!=source_sha or r.get('teacher_profile')!=teacher_profile for r in completed):
        raise ValueError('recording gate mixed execution source')
    return {'source_sha':source_sha,'teacher_profile':teacher_profile,'plan_sha256':digest,
            'qualified':True,'n':gate['n'],'N':gate['N'],'criteria':CRITERIA}

def recording_mode_equivalence(gate_rows,recorded_rows):
    """The same starts must pass in both rendering modes before data admission."""
    baseline={r['index']:r for r in gate_rows if r.get('status')=='complete' and r.get('exit')==0}
    if len(recorded_rows)<3:raise ValueError('at least three paired recording-mode checks required')
    seen=set()
    for row in recorded_rows:
        index=row['index'];old=baseline[index]
        if index in seen:raise ValueError('distinct paired starts required')
        seen.add(index)
        if row.get('status')!='complete' or row.get('physical_success') is not True or old.get('physical_success') is not True:
            raise ValueError('recording mode physical result differs or fails')
        for key in ('source_sha','teacher_profile','action_contract','self_pose_source','episode_plan_sha256'):
            if row.get(key)!=old.get(key):raise ValueError('paired source mismatch')
        if row.get('observation_sampling',{}).get('rgb_size')!=[640,480] or row['observation_sampling'].get('rgb_hz')!=10:
            raise ValueError('student runtime camera sampling required')
    return {'qualified':True,'n':len(seen),'N':len(seen),'indices':sorted(seen),
            'source_sha':recorded_rows[0]['source_sha'],'teacher_profile':recorded_rows[0]['teacher_profile']}
