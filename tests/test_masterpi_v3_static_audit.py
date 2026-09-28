"""정적 감사의 분모·weld OFF·시작 자세·충돌 분류를 검증한다."""
import pytest

mujoco = pytest.importorskip('mujoco')

from scripts.audit_masterpi_v3_static import audit
from sim.zone_masterpi_v3_scene import MAP_IDS


@pytest.mark.parametrize('name', MAP_IDS)
def test_three_robot_start_audit_without_step(name, monkeypatch):
    monkeypatch.setattr(mujoco, 'mj_step', lambda *a, **k: pytest.fail('mj_step 금지'))
    result = audit(name)
    assert result['sim_time_s'] == 0 and result['active_welds'] == 0
    assert result['mj_step_calls'] == result['model_calls'] == 0
    assert result['contact_profile'] == 'cargo_noslip_v1' and result['noslip_iterations'] > 0
    assert len(result['cameras']) == 6
    assert not [row for row in result['contacts'] if row['kind'] in ('self', 'peer')]
    assert all('floor' in row['geoms'] and row['penetration_m'] < .0002 for row in result['contacts'])
    for rid in ('r1', 'r2', 'r3'):
        nav = result['cameras'][rid + '__nav_cam']
        wrist = result['cameras'][rid + '__robot_cam']
        assert nav['rays'] == wrist['rays'] == 221
        # Preserve observed occlusion as evidence, not a made-up zero-occlusion claim.
        assert nav['self_hits'] == 2
        assert wrist['self_hits'] == 0
