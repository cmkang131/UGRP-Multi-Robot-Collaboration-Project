"""Independent rehashed identity probes; all data are synthetic."""
import json
import pytest
from tests.test_zone_study_evidence import completed, export_api, synthetic_source, put, reseal
from scripts.tensorboard_tools import export as tb

@pytest.mark.parametrize('group', ['calls', 'actions'])
@pytest.mark.parametrize('field,value', [('run_id','foreign-trial'),('seed',987654),('condition','peer_ko')])
def test_reject_foreign_log_row(tmp_path, completed, export_api, group, field, value):
    src=synthetic_source(tmp_path,'success',completed)
    record=json.loads((src/'study/trial_record.json').read_text())
    assert record[group]
    record[group][0][field]=value
    put(src,'study/trial_record.json',record)
    reseal(src)
    out=tmp_path/'events'
    try:
        tb.convert(src,out,allow_synthetic=True,max_images=0)
    except ValueError:
        assert not list(out.glob('events*'))
        return
    success=export_api(str(out)).Reload().Scalars('evaluation/reported_success')[0].value
    pytest.fail(f'foreign {group}[0].{field}={value!r} accepted; reported_success={success}')

def test_reject_relabelled_trial_with_original_call_and_action_run_ids(tmp_path, completed, export_api):
    src=synthetic_source(tmp_path,'success',completed)
    names=['manifest.json','result.json','study/trial_record.json','eval_only/evaluation.json']
    for name in names:
        row=json.loads((src/name).read_text())
        row['evidence_identity']['trial_id']='unrelated-trial'
        if name=='study/trial_record.json': row['trial_id']='unrelated-trial'
        put(src,name,row)
    reseal(src)
    out=tmp_path/'events'
    try: tb.convert(src,out,allow_synthetic=True,max_images=0)
    except ValueError: return
    success=export_api(str(out)).Reload().Scalars('evaluation/reported_success')[0].value
    pytest.fail(f'relabelled trial retained foreign call/action run IDs; reported_success={success}')
