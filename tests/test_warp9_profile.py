"""No simulator/device/model calls: export fidelity and phase accounting."""
import numpy as np
import pytest
from scripts.warp9_profile import Profile, exporter


class Device:
    def __init__(self, value):
        self.value=np.asarray(value)
        self.reads=0
    def numpy(self):
        self.reads+=1
        return self.value.copy()


def native_export(result, model, data, world_id=0):
    result['qpos']=data.numpy()[world_id].copy()
    result['energy']=data.numpy()[world_id].sum()


def test_export_instrumentation_preserves_each_world_and_read_count():
    device=Device([[1.,2.],[3.,4.]])
    reads=[]
    def read(array):
        reads.append(array)
        return array.numpy()
    copy,audit=exporter(native_export,read)
    for world in (0,1):
        a,b={},{}
        native_export(a,None,device,world)
        copy(b,None,device,world)
        np.testing.assert_array_equal(a['qpos'],b['qpos'])
        assert a['energy']==b['energy']
    assert len(reads)==4 and audit['replaced_reads']==2


def test_export_transform_rejects_unaccounted_numpy_arguments():
    def unsupported(result,model,data,world_id=0):
        return data.numpy('unexpected')
    with pytest.raises(ValueError,match='numpy arguments'):
        exporter(unsupported,lambda a:a.numpy())


def test_phase_records_exception_and_blocking_read_bytes():
    p=Profile(None)
    a=Device(np.zeros((16,7),dtype=np.float32))
    p.numpy(a)
    with pytest.raises(RuntimeError):
        with p.phase('failure'):
            raise RuntimeError('expected')
    result=p.summary()['phases']
    assert result['host_readback']['bytes']==448
    assert result['host_readback']['implicit_syncs']==1
    assert result['failure']['errors']==1
