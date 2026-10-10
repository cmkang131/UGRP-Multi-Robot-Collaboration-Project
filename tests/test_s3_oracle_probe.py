import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import run_s3_oracle_probe as oracle


def test_plan_and_bundle_keep_host_scope_and_only_cyan_continues_after_close(tmp_path, capsys):
    assert oracle.main(['--expected-source-sha','0'*40,'--output',str(tmp_path/'unused')]) == 0
    assert not (tmp_path/'unused').exists()
    pair=oracle.bundle('0'*40,'pair'); cyan=oracle.bundle('0'*40,'cyan')
    assert pair['stop_after_close'] and not cyan['stop_after_close']
    assert pair['host']=='oracle-a1' and pair['case_cap_s']==cyan['case_cap_s']==60.
    assert pair['alignment_entry']==oracle.OPTION
    assert pair['controller_config']['options']==cyan['controller_config']['options'] or cyan['controller_config']['options']['heading_visual_lock']
    assert oracle.FIXTURE in pair['source_sha256']
    assert pair['s3_camera_binding'] != 'off'
    assert pair['controller_config']['options']['s3_dev_light']=='continue_estimate_v1'


def test_setup_is_copied_eval_fixture_without_raw_lookup():
    a=oracle.setup_record(Path('/nonexistent-Mac-source'),'cyan')
    a['robots']['r3']['pose']['robot_xyz_m'][0]=999
    b=oracle.setup_record(None,'cyan')
    assert b['robots']['r3']['pose']['robot_xyz_m'][0]!=999
    assert 'synthetic' in b['classification'] and not b['checkpoint']


def test_archive_guard_refuses_mac_and_checks_source_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(oracle.platform,'system',lambda:'Darwin')
    with pytest.raises(ValueError,match='Mac execution prohibited'):
        oracle.archive_guard('a'*40,Path('outputs/test/raw'))
    root=tmp_path/('a'*40);root.mkdir();monkeypatch.chdir(root);monkeypatch.setattr(oracle,'ROOT',root)
    parent=root/'outputs/test';parent.mkdir(parents=True);(parent/'SOURCE_SHA').write_text('a'*40)
    monkeypatch.setattr(oracle.platform,'system',lambda:'Linux');monkeypatch.setattr(oracle.platform,'machine',lambda:'aarch64')
    monkeypatch.setenv('MUJOCO_GL','osmesa')
    monkeypatch.setattr(oracle.os,'getpriority',lambda *args:0)
    monkeypatch.setattr(oracle.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*1024**3))
    oracle.archive_guard('a'*40,Path('outputs/test/raw'))
    (parent/'SOURCE_SHA').write_text('b'*40)
    with pytest.raises(ValueError,match='receipt mismatch'):
        oracle.archive_guard('a'*40,Path('outputs/test/raw'))


def test_actual_probe_loop_reaches_lift_and_carry_only_when_requested(tmp_path,monkeypatch):
    from scripts import run_s3_alignment_probe as p
    from sim import s3_motion_ports
    from harness import zone_s3_recovery_runtime
    class Host:
        def __init__(self,b,out,seed): self.now=0.;self.commands={r:{1:2000} for r in p.ROBOTS}
        def reset(self,cap): pass
        def set_deadline(self,t): pass
        def eval_sample(self): pass
        def capture(self): return {}
        def advance_to(self,t): self.now=t
        def issue(self,r,a): self.commands[r].update({a['servo_id']:a['pulse']})
        def close(self): pass
    class Own:
        def __init__(self):
            self.state='init';self.failure=None;self.servo={1:2000};self.last_obs={};self.i=0
            self.vision=SimpleNamespace(detect=lambda *a:[{'estimated_box_center_base_m':[.24,0.,0.]}])
        def set_state(self,s,t): self.state=s
        def step(self,t):
            self.state=('grasp','lift','carry')[min(self.i,2)];self.i+=1;self.servo[1]=1500
            return [('r3',dict(kind='arm',servo_id=1,pulse=1500))]
    class Runtime:
        def __init__(self,*a,**kw): self.localizers={'r3':Own()}
        def initial_commands(self,*a): pass
        def on_frames(self,*a): pass
        def on_command(self,*a): pass
        def record(self): return {}
        def close(self): pass
    monkeypatch.setattr(s3_motion_ports,'PhysicsBackend',Host)
    monkeypatch.setattr(zone_s3_recovery_runtime,'Runtime',Runtime)
    monkeypatch.setattr(p,'restore_scene',lambda *a:None);monkeypatch.setattr(p,'setup_record',lambda *a:{})
    monkeypatch.setattr(p,'assert_frame_commands',lambda *a:None);monkeypatch.setattr(p,'CAP',1.5)
    monkeypatch.setattr(p,'environment_record',lambda:{})
    for stop in (True,False):
        b=oracle.bundle('0'*40,'cyan');b['stop_after_close']=stop
        out=tmp_path/str(stop);result=p.run(b,out)
        assert result['status']=='DEV_STAGE_FINISHED'
        assert result['final']['r3']['state']==('grasp' if stop else 'carry')
