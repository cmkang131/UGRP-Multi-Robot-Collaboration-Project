"""Compile-only audit of actual builder XML hooks; no World reset/step/render."""
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def audit():
    import mujoco
    from sim import execution_contact_profile as p
    from sim.multi_masterpi_production import MultiMasterPiProductionV2, build_multi_robot_xml
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_cargo_scene import CargoZoneScene
    from sim.zone_scenario_scene import scene_spec
    from sim.zone_cargo_contact import base_profile
    rows = []
    def denied(*args, **kwargs):
        raise AssertionError('compile audit forbids step/forward/render')
    def receipt(name, profile, model, xml):
        p.assert_model_profile(model, profile)
        rows.append(dict(entrypoint=name, profile=profile,
            options={k:float(getattr(model.opt,k)) for k in ('noslip_iterations','cone','integrator','impratio','solver','iterations','ls_iterations')},
            xml_sha256=hashlib.sha256(xml.encode()).hexdigest()))
    def compile_constructor(world, *args, xml_transform, **kwargs):
        world.physical_params = {}; world.calibration_parameters = {}
        world.scene_xml = xml_transform(build_multi_robot_xml({}))
        world.model = mujoco.MjModel.from_xml_string(world.scene_xml)
        world.data = SimpleNamespace(eq_active=world.model.eq_active0)
    with patch.object(mujoco,'mj_step',denied), patch.object(mujoco,'mj_forward',denied), \
         patch.object(mujoco,'Renderer',denied), patch.object(MultiMasterPiProductionV2,'__init__',compile_constructor):
        scenario = json.loads((ROOT/'configs/dev_s1lite_native_v445.json').read_text())
        spec = scene_spec(scenario,11)
        for module in ['masterpi_drive_friction','masterpi_drive_friction_v2','masterpi_drive_friction_v3',
            'masterpi_drive_friction_v4','masterpi_drive_friction_v5','masterpi_drive_friction_v5_hard',
            'masterpi_drive_friction_v6','masterpi_drive_friction_v7']:
            factory = importlib.import_module('sim.'+module)
            profile = inspect.signature(factory.build_world).parameters['contact_profile'].default
            scene = FinalV3Scene.from_spec(spec,base_profile(profile))
            w = factory.build_world(scene,drive_profile=factory.PROFILE,render=False)
            receipt('sim.'+module+'.build_world',profile,w.model,w.scene_xml)
        factory = importlib.import_module('sim.masterpi_drive_friction_v7')
        for profile in (p.WARP_DEFAULT,p.LEGACY):
            scene = FinalV3Scene.from_spec(spec,'local_contact_fine')
            w = p.build_world_with_contact(factory.build_world,profile,scene,drive_profile=factory.PROFILE,render=False)
            receipt('warp batch shared factory / '+profile,profile,w.model,w.scene_xml)
        factory = importlib.import_module('sim.zone_final_v3_scene')
        for profile in (p.CPU_DEFAULT,'cargo_noslip_v1'):
            scene = FinalV3Scene.from_spec(spec,base_profile(profile))
            w = factory.build_world(scene,profile,render=False)
            receipt('sim.zone_final_v3_scene.build_world / '+profile,profile,w.model,w.scene_xml)
        scene = CargoZoneScene.from_cargo_config('zone_wide',11,cargo=[])
        xml = scene.transform(build_multi_robot_xml({}))
        receipt('CargoZoneScene.from_cargo_config default',p.CPU_DEFAULT,mujoco.MjModel.from_xml_string(xml),xml)
        xml = '<mujoco><option noslip_iterations="10"/></mujoco>'
        model = mujoco.MjModel.from_xml_string(xml)
        p.configure_model(model)
        receipt('simalt external XML option hook',p.WARP_DEFAULT,model,xml)
    return rows,mujoco.__version__


def main():
    from sim.execution_contact_profile import BUNDLE_ID,CPU_DEFAULT,WARP_DEFAULT
    out = ROOT/'experiments/2026-10-16-noslip-off'
    rows,version = audit()
    files = ['sim/execution_contact_profile.py','sim/warp_native_contact.py','sim/zone_cargo_contact.py',
        'scripts/check_noslip_defaults.py','scripts/warp_act_backend.py','scripts/warp_act_episode.py','scripts/warp_flow_episode.py']
    report = dict(schema='ugrp.noslip_compile_audit.v1',execution_bundle_id=BUNDLE_ID,mujoco=version,
        physics_steps=0,forward_calls=0,renders=0,training=0,vm_used=False,rows=rows,
        source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
    (out/'compile_receipts.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# 진입점별 컴파일 확인','',f'번들 `{BUNDLE_ID}` / MuJoCo {version}. Mac에서 MjModel 로드만 수행.',
        'step/forward/render는 예외로 차단했다. World 생성자의 초기 reset은 대체하고 실제 XML transform hook을 호출했다.',
        'cone 1=elliptic, integrator 3=implicitfast, solver 2=Newton. 직접 CLI 실행·동결 외부 교사 생성자·GPU put_model은 확인 안 됨.','',
        '| 실제 XML hook / 모델 로드 경로 | 기본/선택 프로필 | noslip | cone | integrator | impratio |','|---|---|---:|---:|---:|---:|']
    for r in rows:
        o=r['options'];lines.append(f"| `{r['entrypoint']}` | `{r['profile']}` | {o['noslip_iterations']:g} | {o['cone']:g} | {o['integrator']:g} | {o['impratio']:g} |")
    lines += ['', '| 실행기 | 기본 프로필 | 직접 CLI 모델 로드 |','|---|---|---|']
    for name in ['run_warp_act_teacher','run_warp_flow_teacher','warp_act_backend','simalt_mjwarp','simalt_physics_compare','simalt_step_probe']:
        lines.append(f'| `scripts/{name}.py` | `{WARP_DEFAULT}` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |')
    for name in ['run_e2e_ownmap_live','run_active_wall_baseline','run_active_wall_map','run_active_wall_nav2','run_active_wall_recovery',
        'run_active_wall_rotleft','run_active_wall_wide','run_arena_wall_map','run_wall_parallax_strafe','run_wall_parallax_texture',
        'run_wall_servo_stiffness','run_m2_pair','study_owncam_pair_beam','run_zone_owncam_skill','run_zone_owncam_skill_v5',
        'run_zone_owncam_skill_v6','run_zone_owncam_skill_v7','run_zone_owncam_skill_v8','simalt_pilot']:
        lines.append(f'| `scripts/{name}.py` | `{CPU_DEFAULT}` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |')
    lines += ['', '기존 prereg/버전 JSON 입력 재생 경로는 기록된 프로필 유지. 접촉 안정성·교사 성공·E2E 성공은 미검증.',
        '재현: `PYTHONPATH=. python -m scripts.check_noslip_defaults` (기존 공유 sim 환경 Python). 원본: `compile_receipts.json` (XML·소스 SHA-256).']
    (out/'entrypoints.md').write_text('\n'.join(lines)+'\n')
    funnel=dict(raw_path=str(out/'compile_receipts.json'),reproduce='PYTHONPATH=. python -m scripts.check_noslip_defaults',
        funnel=[dict(gate='actual_model_load',passed=len(rows),rejected=0),dict(gate='selected_noslip_and_weld_off',passed=len(rows),rejected=0)],
        rejections=[],runtime_gpu_conversion='not_measured',physics_success='not_measured')
    (out/'rejection_table.json').write_text(json.dumps(funnel,indent=2)+'\n')
    print(f'COMPILE PASS {len(rows)}; step=forward=render=training=0')


if __name__=='__main__':main()
