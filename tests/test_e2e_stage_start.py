import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from harness.e2e_stage_start import StageStart


def test_slots_bound_and_every_member_precedes_release(tmp_path):
    names=['run-'+str(i) for i in range(4)]
    (tmp_path/'manifest.json').write_text(json.dumps(dict(members=names,source_sha='sha',restore_slots=2)))
    lock=threading.Lock();state=dict(active=0,peak=0,restored=0)
    def work(name):
        group=StageStart(tmp_path,name,'sha',timeout=6)
        with group.restore_slot():
            with lock:
                state['active']+=1;state['peak']=max(state['peak'],state['active'])
            time.sleep(.05)
            with lock:state['active']-=1;state['restored']+=1
        receipt=group.ready()
        assert state['restored']==4
        return receipt
    with ThreadPoolExecutor(4) as pool:rows=list(pool.map(work,names))
    assert state['peak']==2
    assert len({r['start_monotonic'] for r in rows})==1
    assert max(r['actual_start_monotonic'] for r in rows)-min(r['actual_start_monotonic'] for r in rows)<.3


def test_missing_member_times_out_and_wrong_sha_rejected(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps(dict(members=['a','b'],source_sha='sha',restore_slots=1)))
    with pytest.raises(ValueError):StageStart(tmp_path,'a','other')
    with pytest.raises(TimeoutError):StageStart(tmp_path,'a','sha',timeout=.05).ready()
    assert not (tmp_path/'release.json').exists()
