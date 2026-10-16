"""Host admission tests do not import MuJoCo or perform network requests."""
from contextlib import contextmanager
import pytest
from scripts import simalt_host


@pytest.mark.parametrize('project,instance,machine,accepted',[
    ('ugrp-sim-b-1014','ugrp-act-l4-gcp2','g2-standard-8',True),
    ('ugrp-sim-b-1014','ugrp-sim-gcp2','n4-highcpu-64',True),
    ('ugrp-act-train-1014','ugrp-act-l4-gcp2','g2-standard-8',False),
    ('ugrp-sim-b-1014','ugrp-act-l4-pilot1','g2-standard-4',False),
    ('ugrp-sim-b-1014','ugrp-act-l4-gcp2','g2-standard-4',False),
])
def test_metadata_binds_project_instance_and_machine(monkeypatch,project,instance,machine,accepted):
    monkeypatch.setattr(simalt_host.platform,'system',lambda:'Linux')
    values={'project/project-id':project,'instance/name':instance,
            'instance/machine-type':machine,'instance/zone':'asia-northeast3-a'}
    class Opener:
        @contextmanager
        def open(self,request,timeout):
            key=request.full_url.split('/computeMetadata/v1/')[1]
            assert key in values  # includes no service-account/token endpoint
            class Response:
                def read(self,n):return values[key].encode()
            yield Response()
    monkeypatch.setattr(simalt_host,'build_opener',lambda *args:Opener())
    if accepted:
        assert simalt_host.gcp2_identity()['project_id']==project
    else:
        with pytest.raises(RuntimeError,match='unapproved'):
            simalt_host.gcp2_identity()
