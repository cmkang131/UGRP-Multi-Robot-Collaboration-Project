import json
from pathlib import Path
import pytest
from scripts import grasp_act_host as host


def test_identity_reads_only_nonsecret_metadata_and_rejects_other_project(monkeypatch):
    monkeypatch.setattr(host.platform,'system',lambda:'Linux')
    calls=[]
    values={'project/project-id':host.GCP_PROJECT,'instance/name':'gcp-test',
            'instance/machine-type':'projects/123/machineTypes/test-16','instance/zone':'projects/123/zones/test-zone'}
    def get(url,headers):
        calls.append((url,headers));return values[url.split('/v1/')[1]]
    monkeypatch.setattr(host,'metadata',get)
    result=host.identity('gcp1')
    assert result['machine_type']=='test-16' and result['provider']=='gcp'
    assert len(calls)==4 and all(h=={'Metadata-Flavor':'Google'} for _,h in calls)
    assert not any('token' in url or 'recursive' in url for url,_ in calls)
    values['project/project-id']='other-project'
    with pytest.raises(ValueError,match='project'):host.identity('gcp1')
    monkeypatch.setattr(host.platform,'system',lambda:'Darwin')
    with pytest.raises(ValueError,match='Linux'):host.identity('gcp1')


def test_machine_bound_baseline_rejects_unmeasured_and_other_host(tmp_path):
    h={'schema':'ugrp.grasp_act.host.v1','provider':'gcp','project_id':host.GCP_PROJECT,
       'instance':'test','machine_type':'test-16','zone':'test-zone','cpu_count':16}
    (tmp_path/'resource-admission.json').write_text(json.dumps({'execution_host':h,'concurrency':16}))
    p=tmp_path/'speed-gate.json'
    p.write_text(json.dumps({'completed':16,'median_wall_per_sim':2.,'invalid_samples':[]}))
    assert host.measured_speed_baseline(tmp_path,h,16)['median_wall_per_sim']==2.
    for bad in ({**h,'provider':'azure'},{**h,'machine_type':'test-32'},{**h,'instance':'different'},None):
        with pytest.raises(ValueError,match='machine'):host.measured_speed_baseline(tmp_path,bad,16)
    with pytest.raises(ValueError,match='concurrency'):host.measured_speed_baseline(tmp_path,h,8)
    p.write_text(json.dumps({'completed':15,'median_wall_per_sim':2.,'invalid_samples':[]}))
    with pytest.raises(ValueError,match='measurement'):host.measured_speed_baseline(tmp_path,h,16)


def test_only_managed_persistent_subdirectory_is_admitted(monkeypatch,tmp_path):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    host.require_run_root(tmp_path/'ugrp-sim/runs/new-run')
    for path in (tmp_path/'ugrp-sim/runs',tmp_path/'tmp/run',tmp_path/'ugrp-sim/runs/../outside'):
        with pytest.raises(ValueError,match='persistent'):host.require_run_root(path)


def test_gcp_cohort_cannot_inherit_azure_limit_or_skip_measurement(monkeypatch,tmp_path):
    from scripts import run_grasp_act_batch as batch
    plan=tmp_path/'plan.json';plan.write_text(json.dumps({'episodes':[{}]*40}))
    monkeypatch.setattr(batch,'identity',lambda _: {'cpu_count':16})
    monkeypatch.setattr(batch,'require_run_root',lambda _:None)
    argv=['batch','--root',str(tmp_path/'run'),'--plan',str(plan),'--execution-host','gcp1']
    monkeypatch.setattr(batch.sys,'argv',argv)
    with pytest.raises(ValueError,match='explicit measured speed limit'):batch.main()
    monkeypatch.setattr(batch.sys,'argv',argv+['--speed-gate-limit','2.5'])
    with pytest.raises(ValueError,match='--probe-only'):batch.main()
    assert not (tmp_path/'run').exists()
