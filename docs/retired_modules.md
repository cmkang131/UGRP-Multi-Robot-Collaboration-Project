# 퇴역 모듈 (2026-10-09)

기준 main: `888447674318bc311e1ef65f71c654692b2b76bb`. 코드 소스 퇴역이며 시뮬레이션·모델 호출·실물 실행 0회. `outputs/`, 지도, 자산, 실험 결과는 변경하지 않았다.

모듈 1068개 = 퇴역 87개 / 보류 14개 / 유지 967개. 전용 시험 2개 퇴역.
유지 모듈 255,623줄, 보류 모듈 918줄, 퇴역 모듈 10,160줄 + 시험 51줄. 삭제 코드·시험 10,211줄. 보류 모듈 918줄.

## 판단과 재현

`import`/상대 import, importlib 별칭·상수·모듈 문자열, subprocess `-m`, pathlib 경로 조합의 AST 그래프를 계산했다. 파일 이름의 부분 문자열 유무로 삭제를 결정하지 않았다. 현재 실행 경로, main 안내 명령, 운영/실물 경로, 열린 PR의 변경 코드·설정·명령과 전이 의존성을 시작점으로 삼았다. 유지 모듈을 직접 검사하는 시험은 의존성 전체를 유지한다. 그대로 남기는 과거 실험 Python 스크립트의 호출 대상도 보류했다. 임의 외부 설정/체크포인트에 담긴 동적 import는 정적으로 완전하게 증명할 수 없다.

기본 카탈로그 41항목 + 조각 18항목은 모두 유지 경로/문서/PR 의존성에 연결되어 이번에 퇴역하지 않는다. 오래됐다는 이유만으로 현재 번들 소스나 고정 시험을 지우지 않았다. 카탈로그별 근거는 아래 표와 `inventory.json`의 시작점/브랜치 경로에 있다.

전체 복구: 별도 복제본에서 `git checkout --detach 888447674318bc311e1ef65f71c654692b2b76bb` 후 해당 실험 README의 명령·환경을 따른다. 단일 소스 확인은 `git show 888447674318bc311e1ef65f71c654692b2b76bb:<파일>`로 가능하다. 마지막 변경 SHA는 파일 이력 정보이고, 재현 기준은 의존성이 함께 있는 위 전체 커밋이다. 기록된 과거 성공/물리 결과를 현재 실행 결과로 승계하지 않는다.

아래 마지막 사용 열은 **찾은 실험 문서의 최신 경로 참조**이며 실행 완료/실제 최종 사용 일시를 추정하지 않는다. 참조가 없으면 미발견으로 표시했다. 전체 참조 목록·파일별 줄 수·SHA는 [retirement.json](../experiments/2026-10-09-module-retirement/retirement.json)에 있다.

## 퇴역 및 보류 파일

| 판정 | 파일 | 마지막 사용 실험/번들 (확인 범위) | 마지막 변경 SHA | 재현 방법 / 보류 근거 |
|---|---|---|---|---|
| 보류 | `harness/real_obstacles.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | physical MasterPi depth-provider contract; protected real robot boundary |
| 퇴역 | `harness/visual_transport.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/analyze_carry_act_experiment.py` | `experiments/2026-09-18-act-pair-carry/README.md` (경로 참조) | `5fba937402155e5deffec2376dade034e9e091ad` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_act_feasibility.py` | 직접 기록 미발견 | `478ba532b6f512feeeaad76c2c272eb352d42baf` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_act_speed.py` | 직접 기록 미발견 | `ef3e6de886da83bd5ede2b2a7df4bacc24513ff2` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_camera_pixel_grasp.py` | 직접 기록 미발견 | `6446e2ad1bae96f1e2eb396fb56fb38a85aa85ce` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_camera_visual_grasp.py` | 직접 기록 미발견 | `a3829b604592a868348a63edad6355919d20f7ba` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_carry_act_experiment.py` | `experiments/2026-09-18-act-pair-carry/README.md` (경로 참조) | `5fba937402155e5deffec2376dade034e9e091ad` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_carry_input_ablation.py` | `experiments/2026-09-21-carry-input-ablation/README.md` (경로 참조) | `491eaa334070b78431aa7f4ff5512603ee8877b1` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_dispatch_carry_clearance.py` | 직접 기록 미발견 | `1dec480fc4c9a2bc19a79b93859703458ad184a2` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_dispatch_concurrency.py` | 직접 기록 미발견 | `f1a31447a079fc2f2eacffac337ddaa39d4a31ee` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_jev_motion.py` | `experiments/2026-09-21-jev-direct-motion/README.md` (경로 참조) | `aed309c7e8f8695aaf77e3335180405810581a4f` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_jev_semantic_cohort.py` | 직접 기록 미발견 | `ed4b21b45cb2458728cea3460fd66d85e44e1ea7` | 위 전체 커밋 checkout |
| 보류 | `scripts/audit_pair_grasp_endurance.py` | `experiments/2026-09-14-pair-grasp-endurance/README.md` (경로 참조) | `cdeee5fb22fe7ccbbb90b0bde424e7692a94aa16` | retained executable experiment record imports/launches this file |
| 보류 | `scripts/audit_pair_grasp_recovery.py` | 직접 기록 미발견 | `cdeee5fb22fe7ccbbb90b0bde424e7692a94aa16` | retained executable experiment record imports/launches this file |
| 보류 | `scripts/audit_pair_navigation.py` | `experiments/2026-09-14-pair-navigation/README.md` (경로 참조) | `cdeee5fb22fe7ccbbb90b0bde424e7692a94aa16` | retained executable experiment record imports/launches this file |
| 퇴역 | `scripts/audit_recovery_aggregation.py` | 직접 기록 미발견 | `db1199c3907131fbf319aeafaf758a0caa50f81b` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_recovery_command_calibration.py` | 직접 기록 미발견 | `16dbd80f2ed58f836211c0b86462559bc0f32fcb` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_recovery_experiment.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `d78f4f7faa264275d9d1e21c44548345e6a96e0d` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_research_camera_e2e.py` | `experiments/research-e2e-recovery-20260916/README.md` (경로 참조) | `e706f155b011e9dc9c6c95d318e9a3ab9b2000bc` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_teacher1_diagnostic.py` | 직접 기록 미발견 | `ef3e6de886da83bd5ede2b2a7df4bacc24513ff2` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/audit_three_robot_e2e.py` | 직접 기록 미발견 | `b3888574c85c63f4d8db00d2a36fcb5953054805` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/benchmark_dispatch_capture.py` | `experiments/2026-09-22-act-render-speed/README.md` (경로 참조) | `4beb670e1f8ac0faab82c095474863bbb097e92f` | 위 전체 커밋 checkout |
| 보류 | `scripts/benchmarks/apply_masterpi_trial_measurement.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/evaluate_masterpi_task_parity.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/fit_masterpi_gripper.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/make_masterpi_aruco_markers.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/masterpi_task_validation_plan.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/record_masterpi_calibration_measurement.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/render_masterpi_geometry_views.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 보류 | `scripts/benchmarks/run_masterpi_calibration_trial.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 퇴역 | `scripts/build_dispatch_review.py` | 직접 기록 미발견 | `6944fcf7469cf64942e2c598b759707d5300482c` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/build_recovery_datasets.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `c482f511cd8b013972c8f46de82308f1a7c078f4` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/build_zone_supplement_views.py` | `experiments/2026-09-26-tb-0925-supplement/README.md` (경로 참조) | `19b358987afa7d0ea33ec64e20bb192ebf424f16` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/check_zone_item_recovery_mutations.py` | `experiments/2026-09-30-t13b-recovery/README.md` (경로 참조) | `5d1268e8a95cff5506d67d86ddaa6f1948be1908` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/collect_camera_short_transport_teacher.py` | 직접 기록 미발견 | `b61bb4c9476b1f6cefcc03ee00c83a5243c33be7` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/collect_recovery_curriculum.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `10de0b0ee171134c4c9cd778385e1979fa4664f1` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/compare_jev_skill_cohorts.py` | 직접 기록 미발견 | `150554b99a2f700832e5addd336b78f5edaa17e0` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/compose_act_speed_comparison.py` | 직접 기록 미발견 | `ef3e6de886da83bd5ede2b2a7df4bacc24513ff2` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/compose_recovery_comparison.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `a43826315049c33e3611003b6d64c13d4f4cee11` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/diagnose_opencv_columns.py` | `experiments/2026-10-05-opencv-column-diagnosis/README.md` (경로 참조) | `ec0215f37118f8cbb0a656621ac89cc3279d400e` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/diagnose_speed_teacher_failures.py` | 직접 기록 미발견 | `ef3e6de886da83bd5ede2b2a7df4bacc24513ff2` | 위 전체 커밋 checkout |
| 보류 | `scripts/eval_masterpi_v2_expert.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 퇴역 | `scripts/eval_partial_fix_gate.py` | `experiments/2026-10-05-opencv-column-diagnosis/README.md` (경로 참조) | `ec0215f37118f8cbb0a656621ac89cc3279d400e` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/evaluate_mixed_recovery.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/evaluate_visual_team.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/export_dispatch_wheel_templates.py` | 직접 기록 미발견 | `bfb5bfd6360df9151e970dcf48c47532218bfa7e` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/merge_camera_varied_start_teacher.py` | 직접 기록 미발견 | `5ae9589548a1c178a0c143d8e8f502e8b121926d` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/plot_jev_semantic_cohort.py` | 직접 기록 미발견 | `ed4b21b45cb2458728cea3460fd66d85e44e1ea7` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/ppo_policy_server.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_camera_jaw_visibility.py` | 직접 기록 미발견 | `bb76e68420a12a49793b1e72c47eb9595492a539` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_camera_retry.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_dispatch_grip_retention.py` | 직접 기록 미발견 | `ce3bc9578175d84fc22b86570a79f989109fbc49` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_dispatch_solo_route.py` | 직접 기록 미발견 | `71900deb091716e2f70c81d490cb3cc9dd285897` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_gemini_navigation.py` | 직접 기록 미발견 | `c6eb676a3fcf1fd2d9f9911825085dd62542f251` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_kaggle_runtime.py` | 직접 기록 미발견 | `b1cc9dcd63a00746ff1d9b56267db9d6f59ac285` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_known_map_turn.py` | 직접 기록 미발견 | `8512cd92e2d03072808890859b06dcb03680008a` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_markerless_manipulation.py` | 직접 기록 미발견 | `c6eb676a3fcf1fd2d9f9911825085dd62542f251` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_multi_object_tracking.py` | 직접 기록 미발견 | `42024aa53c2e5d0fee3db37edddebd2684132a78` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_pair_navigation_hold.py` | `experiments/2026-09-14-pair-navigation/README.md` (경로 참조) | `89cee623eede570af3c6b3bba9d5a0864a0d3d35` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_research_visual_witness.py` | `experiments/research-e2e-witness-20260916/protocol.md` (경로 참조) | `e706f155b011e9dc9c6c95d318e9a3ab9b2000bc` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_varied_start_axes.py` | 직접 기록 미발견 | `05040bd14c97a03e2a28dde5a8242a9964681c46` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_varied_start_grasp_tolerance.py` | 직접 기록 미발견 | `81793ec1f2f19fd3663e2e461af22ab7fbd70509` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_visual_acquisition.py` | `experiments/2026-09-14-skill-semantic-pick/protocol.md` (경로 참조) | `c6eb676a3fcf1fd2d9f9911825085dd62542f251` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/probe_visual_grip.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/record_sim_beam_mission.py` | `experiments/2026-09-09-dual-grasp-sync/README.md` (경로 참조) | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/record_sim_pipeline.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/record_sim_team.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/record_sim_team_visible.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/record_sim_warehouse_mission.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/refit_dispatch_grasp.py` | 직접 기록 미발견 | `0e2c64448a3281ac1eedf77d97c726f8e29c265c` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/relay_colab_models.py` | 직접 기록 미발견 | `f0b304beada0a08d7465c8a039764e5a20a049d6` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/render_carry_act_comparison.py` | 직접 기록 미발견 | `5fba937402155e5deffec2376dade034e9e091ad` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/render_jev_motion.py` | `experiments/2026-09-21-jev-direct-motion/README.md` (경로 참조) | `9acced5cacf762c87087e07eed7f492a6b20d98f` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/render_jev_semantic_cohort.py` | 직접 기록 미발견 | `ed4b21b45cb2458728cea3460fd66d85e44e1ea7` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/replay_pair_vision.py` | 직접 기록 미발견 | `cdac7b7e5154cdc531169a46c90732461b5ae06e` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/report_heading_navigation.py` | `experiments/2026-09-13-heading-map-navigation/README.md` (경로 참조) | `e1029833a6e7b273b8bb5e8171ad2bfcdf376e7c` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/report_known_map_cohort.py` | `experiments/2026-09-13-known-map-navigation/README.md` (경로 참조) | `3ad947391a2ff84c3cb325121d4829a3e32dce37` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_act_recovery_trial.py` | 직접 기록 미발견 | `d78f4f7faa264275d9d1e21c44548345e6a96e0d` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_act_speed_cohort.py` | 직접 기록 미발견 | `8face9dd83d23ec7c5a8d116311e2ef8953bcdbe` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_camera_goal_cohort.py` | `experiments/research-e2e-varied-start-20260916/README.md` (경로 참조) | `fd5d68ee41bc56c8b61d1f020f5891b218e36ef0` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_camera_pixel_grasp.py` | 직접 기록 미발견 | `64f4bdaf21ac85678f6151016b846feff19c91db` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_camera_short_transport_cohort.py` | `experiments/2026-09-13-rgb-short-transport/reproduction.md` (경로 참조) | `1d904c255b9ff551b103e6de98ba22bd7692d86f` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_camera_visual_grasp.py` | 직접 기록 미발견 | `a3829b604592a868348a63edad6355919d20f7ba` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_cloud_carry_continuation.py` | 직접 기록 미발견 | `d13cda20834d039184bf90d5d9c817c1579b494c` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_pair_carry_cohort.py` | `experiments/2026-09-13-pair-carry-sync/README.md` (경로 참조) | `99898d8983315e39635c063e0b6b430c01818b22` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_pair_carry_sync.py` | 직접 기록 미발견 | `99898d8983315e39635c063e0b6b430c01818b22` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_parallel_carry_study.py` | 직접 기록 미발견 | `5f863b43bd089093ec77d99f1ea71d11933e6767` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_recovery_cases.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `d78f4f7faa264275d9d1e21c44548345e6a96e0d` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_recovery_final.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `d78f4f7faa264275d9d1e21c44548345e6a96e0d` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_zone_owncam_skill_v9.py` | `experiments/2026-09-26-sim-speed/README.md` (경로 참조) | `1561166039ef5fa88a24277d25bc1d97d8800d41` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/run_zone_study_offline_smoke.py` | `experiments/2026-09-26-zone-study-offline-smoke/v6/README.md` (경로 참조) | `c21a6fe9ddd33203aff4e34a0577e0d8adb95334` | 위 전체 커밋 checkout |
| 보류 | `scripts/stress_real_geometry_parity.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | real robot calibration/geometry boundary; current owner use unconfirmed |
| 퇴역 | `scripts/stress_warehouse_seeds.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/summarize_carry_resolution.py` | 직접 기록 미발견 | `d9005af4bfb252e5848e67ff96f6b83ba01b319f` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/train_camera_grasp_student.py` | `experiments/2026-09-10-teacher-student/report.md` (경로 참조) | `1d076017dcdf8efe14289c3d8f62080b9baf4fd5` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/train_grasp_recovery_student.py` | 직접 기록 미발견 | `523873613dc3a7aab942baf565cc86fb167dfb34` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/train_recovery_act.py` | `experiments/2026-09-16-act-recovery/REPRODUCE.md` (경로 참조) | `9084510d47f6bc5c83a09a0df4b84f9d6d05b7ed` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/v98_light_summary.py` | `experiments/2026-10-03-pair-carry-highpose/README.md` (경로 참조) | `232397cfc7b0d9fd27f1e476361dcc542df9c155` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/verify_perception_noslip_snapshot.py` | `experiments/2026-09-26-tb-perception-noslip/README.md` (경로 참조) | `e19c88a08ec5b9c595615409ecff4a0a14a65057` | 위 전체 커밋 checkout |
| 퇴역 | `scripts/verify_training_grasp.py` | 직접 기록 미발견 | `2df573259de679e651bc1085e34f7da6ea713716` | 위 전체 커밋 checkout |
| 퇴역 | `tests/test_carry_resolution_selection.py` | 직접 기록 미발견 | `d9005af4bfb252e5848e67ff96f6b83ba01b319f` | 위 전체 커밋 checkout |
| 퇴역 | `tests/test_parallel_carry_study.py` | 직접 기록 미발견 | `5f863b43bd089093ec77d99f1ea71d11933e6767` | 위 전체 커밋 checkout |

## 유지 workflow 카탈로그

| 카탈로그 | ID | 판정 |
|---|---|---|
| `configs/simulation_workflows.d/final_environment_gain_calibration_v101.json` | `zone-final-environment-gaincal-v101` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_environment_measurement_v89.json` | `zone-final-environment-floor-light-v2-check` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_environment_v84.json` | `zone-final-environment-check` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_environment_v87.json` | `zone-final-environment-floor-light-check` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_loaded_gain_v102.json` | `zone-final-pair-loaded-gaincal-v102` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_v88.json` | `zone-final-pair-v3` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_v90.json` | `zone-final-pair-heldout-v90` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_v91.json` | `zone-final-pair-heldout-v91` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_v92.json` | `zone-final-pair-loaded-v92` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/final_pair_v95.json` | `zone-final-pair-heldout-v95` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/masterpi_drive_friction.json` | `masterpi-drive-friction-probe` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/masterpi_v7_roller_approx.json` | `masterpi-v7-roller-approx-probe` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/pair_highpose_v98.json` | `zone-final-pair-highpose-v98` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/pair_highpose_v98_dev_checkpoint.json` | `zone-final-pair-highpose-v98-dev-checkpoint` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/pair_llm_v100.json` | `zone-pair-llm-v100` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/s3_door_yield_v108.json` | `zone-s3-door-yield-v108` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/s3_host_v107.json` | `zone-s3-host-v107` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.d/solo_cyan_v106.json` | `zone-solo-cyan-v106` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-study-pilot` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `local` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `dispatch` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `dispatch-skills` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `communication` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `multi-object` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-dispatch` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-teacher-fix` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-cargo-probe` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-team-jobs-smoke` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-cargo-catalogue` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-color-eval` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-cargo-perception-eval` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-rgb-outcome-eval` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `navigation` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `pair-navigation` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `camera-pair` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `rgb-traffic` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `act` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `teacher` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `act-map-suite` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `act-training` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `act-input-training` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `act-input-finalization` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `jev` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `stage-sync` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `physical` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `worker` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `tensorboard` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `communication-study` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `communication-cloud-submit` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-owncam-loc-record` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-owncam-loop-run` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-m1-owncam-run` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-m1-owncam-memory-v3-run` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-m1-owncam-memory-run` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-m2-pair` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-pair-dev` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `masterpi-v3-static-audit` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-study-integration-run` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |
| `configs/simulation_workflows.json` | `zone-pair-bootstrap-probe` | 유지: runner가 보호 집합 안에 있음; 퇴역 확인 전 보류 |

## 범위 밖

`maps/`·`sim/assets/` 59개 추적 파일은 [목록](../experiments/2026-10-09-module-retirement/out_of_scope.txt)만 남겼다.

## 감사 기록

[작업 기록과 검증 결과](../experiments/2026-10-09-module-retirement/README.md). DRAFT PR이며 감독·사용자 확인 전 병합 금지.

- 2026-10-09 S3 준비용 `zone-s3-host-heading-v144` / workflow7.37.0: 물리 실행0·heading 의존성 미승인 상태에서 퇴역. 사용자 새 최대+1 지시에 따라 `zone-s3-host-heading-v146` /7.39.0으로 대체; 계획 원본은 `experiments/2026-10-09-s3-no-prior/s3next/registration.json`과89357a64에 보존. 과거v142 실행과 원본은 유지.

- 2026-10-09 S3 `zone-s3-sweep-v149`는 원본 `b73ce193` 및 raw 증거를 보존한 과거 DEV 실행이다. 후속 실행은 pre-GO 재대기와 사전 등록된 motion 옵션 선택을 묶은 `zone-s3-odometry-v150` /7.43.0을 사용한다. 기존 실행/실패 기록과 재생 소스는 삭제·덮어쓰지 않는다.
