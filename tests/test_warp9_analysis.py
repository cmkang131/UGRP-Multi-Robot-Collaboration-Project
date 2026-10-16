import json
from scripts.analyze_warp9_profile import collect,markdown


def test_running_missing_and_error_are_not_reported_as_zero_or_success(tmp_path):
    (tmp_path/'n1').mkdir()
    (tmp_path/'n4').mkdir()
    (tmp_path/'n4/summary.json').write_text(json.dumps(dict(status='HOST_ERROR',source_sha='test',
        host={},shared_load=False,errors=[dict(category='HOST_ERROR',reason='overflow')],batch_sim_s=.1)))
    r=collect(tmp_path)
    assert [x['status'] for x in r['rows']]==['RUNNING_OR_HOST_ERROR_UNRESOLVED','HOST_ERROR','UNRETRIEVED','UNRETRIEVED']
    assert all(x['timing'] is None for x in r['rows'])
    assert '0.000000' not in markdown(r)
