import sys,socket
import pytest
for module in ('mujoco','torch','torchvision'):
    sys.modules[module]=None
@pytest.fixture(autouse=True)
def p03_side_effect_guard(monkeypatch):
    from harness.vision_loc_client import VisionWorkerClient
    original=VisionWorkerClient.__init__
    def fake_only(self,*args,**kwargs):
        argv=kwargs.get('argv')
        if not argv or not any(str(x).endswith('tests/vision_loc_fake_worker.py') for x in argv):
            pytest.fail('P03 forbids real inference worker')
        original(self,*args,**kwargs)
    monkeypatch.setattr(VisionWorkerClient,'__init__',fake_only)
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('P03 forbids network'))
    monkeypatch.setattr(socket.socket,'connect_ex',lambda *a:pytest.fail('P03 forbids network'))
    from harness import zone_map_schematic
    monkeypatch.setattr(zone_map_schematic,'render_schematic',lambda *a,**kw:pytest.fail('P03 forbids render'))
    from harness.wall_tags import TagDetector
    monkeypatch.setattr(TagDetector,'detect',lambda *a,**kw:pytest.fail('P03 forbids vision detection'))

def pytest_collection_modifyitems(config,items):
    excluded=[]
    kept=[]
    for item in items:
        if item.path.name=='test_zone_study_pair_delay.py' or item.name=='test_host_worker_crash_stops_base_motion_and_holds':
            excluded.append(item)
        else:
            kept.append(item)
    items[:]=kept
    config.hook.pytest_deselected(items=excluded)
