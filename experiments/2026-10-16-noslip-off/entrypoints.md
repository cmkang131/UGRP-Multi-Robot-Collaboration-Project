# 진입점별 컴파일 확인

번들 `noslip-off-v445` / MuJoCo 3.12.0. Mac에서 MjModel 로드만 수행.
step/forward/render는 예외로 차단했다. World 생성자의 초기 reset은 대체하고 실제 XML transform hook을 호출했다.
cone 1=elliptic, integrator 3=implicitfast, solver 2=Newton. 직접 CLI 실행·동결 외부 교사 생성자·GPU put_model은 확인 안 됨.

| 실제 XML hook / 모델 로드 경로 | 기본/선택 프로필 | noslip | cone | integrator | impratio |
|---|---|---:|---:|---:|---:|
| `sim.masterpi_drive_friction.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v2.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v3.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v4.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v5.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v5_hard.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v6.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.masterpi_drive_friction_v7.build_world` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `warp batch shared factory / warp_native_contact_v1` | `warp_native_contact_v1` | 0 | 1 | 3 | 5 |
| `warp batch shared factory / legacy_noslip10` | `legacy_noslip10` | 10 | 1 | 3 | 1 |
| `sim.zone_final_v3_scene.build_world / cargo_native_v1` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `sim.zone_final_v3_scene.build_world / cargo_noslip_v1` | `cargo_noslip_v1` | 10 | 1 | 3 | 1 |
| `CargoZoneScene.from_cargo_config default` | `cargo_native_v1` | 0 | 1 | 3 | 5 |
| `simalt external XML option hook` | `warp_native_contact_v1` | 0 | 1 | 3 | 5 |

| 실행기 | 기본 프로필 | 직접 CLI 모델 로드 |
|---|---|---|
| `scripts/run_warp_act_teacher.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/run_warp_flow_teacher.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/warp_act_backend.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/simalt_mjwarp.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/simalt_physics_compare.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/simalt_step_probe.py` | `warp_native_contact_v1` | 확인 안 됨: Linux/VM·GPU 금지; 위 공유 hook만 확인 |
| `scripts/run_e2e_ownmap_live.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_baseline.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_map.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_nav2.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_recovery.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_rotleft.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_active_wall_wide.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_arena_wall_map.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_wall_parallax_strafe.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_wall_parallax_texture.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_wall_servo_stiffness.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_m2_pair.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/study_owncam_pair_beam.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_zone_owncam_skill.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_zone_owncam_skill_v5.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_zone_owncam_skill_v6.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_zone_owncam_skill_v7.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/run_zone_owncam_skill_v8.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |
| `scripts/simalt_pilot.py` | `cargo_native_v1` | 확인 안 됨: 직접 실행은 step/render 포함; 위 CPU factory/scene만 확인 |

기존 prereg/버전 JSON 입력 재생 경로는 기록된 프로필 유지. 접촉 안정성·교사 성공·E2E 성공은 미검증.
재현: `PYTHONPATH=. python -m scripts.check_noslip_defaults` (기존 공유 sim 환경 Python). 원본: `compile_receipts.json` (XML·소스 SHA-256).
