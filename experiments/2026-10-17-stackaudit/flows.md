# 최신 스택 적용 감사 — 2026-10-17

사용자: “이런 것들, 최신으로 업데이트 좀 제대로 해봐. 왜 자꾸 까먹는 거야”.

기준 main `c8dc1e6545124ed69a996618bd11df684d233969`. 1라운드 감사 완료(2라운드에서 GCP 프로젝트·계정 조합 2행 보강). **옛 값 8칸**(흐름×항목), 최신 66칸, 모름 190칸. 해당없음은 적용 흐름 밖이다. “최신”은 아래 파일/회수 manifest 범위이며 실제 새 실행·성공·배포 확인이 아니다. 다른 worktree/실행 수정0, SSH0·VM0·Mac sim/render0·모델 호출0.

## 먼저 배정할 옛 값

|우선순위|흐름·항목|현재 근거 / 수정할 곳|
|---|---|---|
|P0|warp8 release 위치 추정|`warp_frozen`→`old_release`→`old_hough`: 구역 바닥 선 Hough/지도 합의. 질감 자기 지도 LK 경로로 교체하고 별도 관문. 담당 warp8/지도 작업자. 기존 실패 결과를 새 관문으로 승계하지 않는다.|
|P1|LLM E2E 물리 백엔드|`cpu_physics`/`e2e`: CPU mj_step. 최신 MJWarp+ACT+자기 지도 통합 실행 경로와 실제 bundle 필요. 조정자 배정.|
|P1|LLM E2E 접촉·noslip|`cpu_contact`: cargo_noslip_v1/10. PR #568 native default 통합 후 실제 XML/manifest 검사. 같은 백엔드 변경과 별도 항목으로 집계.|
|P1|ACT CPU 확인 접촉·noslip|CPU 확인 자체는 AGENTS가 허용한 비교다. 기존 경로는10. PR #568 cargo_native_v1/0 또는 정확한 비교 승인 이탈을 기록하고 primary 결과와 합산하지 않는다.|
|P1|ACT CPU 확인 장면|`cpu_eval`: floor_light_v1. 최신 장면으로 비교하거나 원장면 유지 사유/승인을 stack_deviations에 기록.|

## 흐름과 고정 소스

|흐름|flow|고정 SHA|증거 범위|
|---|---|---|---|
|warp8_beam|beam_pair|`7c8acef516103ce5906b77d6481e46b298961b0c`|native 빔 관문; 회수 summary/queue 범위|
|warp8_release|release|`7c8acef516103ce5906b77d6481e46b298961b0c`|native A-S1; 다음 제출 보류. 구 localizer 교체 필요|
|act16w_teacher|teacher_gate|`37a8c833656a58ba25472e2106276f225e95ad26`|native 교사40 관문; 실제 localizer 없는 truth-free scan|
|act16w_record|record|`37a8c833656a58ba25472e2106276f225e95ad26`|native 기록; 최근 완료는 ops 보고만, 원격 원본 독립 확인 없음|
|act16w_train|train|`37a8c833656a58ba25472e2106276f225e95ad26`|native provenance 전달 코드; 진행 상태는 별도, 학습 성능 주장 없음|
|act16w_eval|act_eval|`37a8c833656a58ba25472e2106276f225e95ad26`|다음 학생 평가: native 검증 + RPC 경로, 최종평가 미실행|
|mapbuild6|self_map|`c7477b1f64910f498b52e1697488c28b2c4569e1`|v7 실제 경로 후보; LK/RBPF 판정 대기, 채택/운반 성공 미확인|
|act_cpu_check|act_eval|`c8dc1e6545124ed69a996618bd11df684d233969`|보존 CPU 확인 경로. CPU 자체는 승인된 비교지만 새 실행에는 noslip/scene 갱신 또는 승인 이탈 필요|
|llm_e2e|e2e_llm|`c8dc1e6545124ed69a996618bd11df684d233969`|main study integration 기준. 최신 MJWarp+ACT+자기지도 통합 실행 manifest 확인 안 됨|
|beam_pair_teacher|beam_pair|`7c8acef516103ce5906b77d6481e46b298961b0c`|다음 빔 짝 교사: MJWarp wrapper가 동결 교사 사용; 녹화/학생 인수와 별개|

## 기준표 × 흐름

L=최신, O=옛, ?=모름, —=해당없음. 각 칸의 근거와 한계는 [flows.json](flows.json)의 `cells.<flow>.<id>`에 있다. 소스 줄은 [evidence.json](evidence.json)의 `matches[].line`에 고정했다.

|항목|warp8_beam|warp8_release|act16w_teacher|act16w_record|act16w_train|act16w_eval|mapbuild6|act_cpu_check|llm_e2e|beam_pair_teacher|
|---|---|---|---|---|---|---|---|---|---|---|
|physics_backend|L|L|L|L|?|?|L|O|O|L|
|contact_profile|L|L|L|L|L|L|L|O|O|L|
|noslip_iterations|L|L|L|L|?|?|L|O|O|L|
|scene_profile|L|L|L|L|?|?|L|O|?|L|
|end_color_scene|?|?|—|—|—|?|—|?|?|?|
|cargo_version|?|?|?|?|?|?|?|?|?|?|
|scenario_version|?|?|?|?|?|?|L|?|?|?|
|heavy_crate|?|?|?|?|?|?|?|?|?|?|
|localization_path|—|O|—|—|—|—|L|—|?|—|
|rbpf|—|?|—|—|—|—|?|—|?|—|
|localization_engine|—|?|—|—|—|—|L|—|?|—|
|setdown_lookaround_v1|?|L|L|L|—|—|—|—|?|?|
|held_object_hidden_v1|?|L|L|L|—|?|?|?|?|?|
|held_world_reads|?|?|L|L|—|?|?|?|?|?|
|teacher_visibility|?|?|L|L|—|—|—|—|—|?|
|invisible_measurements|?|?|L|L|—|—|—|—|—|?|
|nearfield_executor|—|—|—|—|—|L|—|L|?|—|
|weld|L|L|L|L|?|?|?|?|?|L|
|top_camera_control|?|?|?|?|—|?|?|?|?|?|
|planner_model|—|—|—|—|—|—|—|—|L|—|
|planner_provider|—|—|—|—|—|—|—|—|L|—|
|planner_quantization|—|—|—|—|—|—|—|—|L|—|
|planner_fallbacks|—|—|—|—|—|—|—|—|?|—|
|planner_own_rgb_count|—|—|—|—|—|—|—|—|?|—|
|planner_cache_order|—|—|—|—|—|—|—|—|?|—|
|heading_mode|?|?|—|—|—|?|?|?|?|?|
|ultrasonic_front|?|?|?|?|—|?|?|?|?|?|
|wall_cap|L|L|L|L|?|?|?|?|?|L|
|speed_gate|?|?|?|?|—|?|?|?|?|?|
|speed_metric|L|L|?|?|—|?|?|?|?|?|
|gcp_host|?|?|?|?|?|?|?|?|?|?|
|gcp_guards|?|?|?|?|?|?|?|?|?|?|
|no_pooling|L|L|?|?|?|?|?|?|?|L|
|planning_cap_basis|?|?|—|—|—|—|?|—|?|?|
|rejection_ledger|?|?|?|?|—|?|?|?|?|?|
|cap_end_label|?|?|?|?|—|?|?|?|?|?|
|gcp_project|L|L|L|L|?|?|?|?|?|L|
|gcp_account|?|?|?|?|?|?|?|?|?|?|

## 근거 파일:줄

- `physics`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `scripts/run_warp_flow_teacher.py:1, 61`. 전체 hash/발췌는 evidence.json.
- `native`: `4f4f7a1aa64849511d03156bf49272a71c954777` · `sim/warp_native_contact.py:12, 13, 14, 16, 17, 20, 21, 24, 25, 30`. 전체 hash/발췌는 evidence.json.
- `scene`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `sim/scene_contrast_v5.py:6, 19, 32, 68, 72, 76`. 전체 hash/발췌는 evidence.json.
- `scene_act`: `37a8c833656a58ba25472e2106276f225e95ad26` · `scripts/warp_act_scene.py:2, 16, 21, 33, 36`. 전체 hash/발췌는 evidence.json.
- `localization`: `c7477b1f64910f498b52e1697488c28b2c4569e1` · `scripts/mapbuild6_replay.py:1, 27, 28, 29, 38, 46, 65, 70, 91`. 전체 hash/발췌는 evidence.json.
- `lk`: `c8dc1e6545124ed69a996618bd11df684d233969` · `harness/e2e_rgb_vo.py:144, 169, 172`. 전체 hash/발췌는 evidence.json.
- `localization_pending`: `c7477b1f64910f498b52e1697488c28b2c4569e1` · `experiments/2026-10-17-mapbuild6/README.md:3, 5, 9, 11`. 전체 hash/발췌는 evidence.json.
- `old_release`: `8e81b7d96c0c73171635348c90631462adfe1eb0` · `sim/lookaround_localization.py:20, 39, 45, 200, 209, 213, 214, 216, 236, 283`. 전체 hash/발췌는 evidence.json.
- `old_hough`: `8e81b7d96c0c73171635348c90631462adfe1eb0` · `harness/zone_solo_cyan_landmarks.py:89`. 전체 hash/발췌는 evidence.json.
- `solo_look`: `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8` · `sim/grasp_act_solo_lookaround.py:20, 32, 37, 43, 47, 63, 99, 105, 124, 125`. 전체 hash/발췌는 evidence.json.
- `act_episode`: `37a8c833656a58ba25472e2106276f225e95ad26` · `scripts/warp_act_episode.py:25, 28, 34, 41, 48, 49, 58, 67, 71, 74`. 전체 hash/발췌는 evidence.json.
- `act_gate`: `37a8c833656a58ba25472e2106276f225e95ad26` · `experiments/2026-10-16-act16w/resume4/native-gate-summary.json:4, 6, 7, 12, 13`. 전체 hash/발췌는 evidence.json.
- `act_eval`: `37a8c833656a58ba25472e2106276f225e95ad26` · `scripts/evaluate_act16w.py:11, 34, 35, 36, 48, 54, 90, 91`. 전체 hash/발췌는 evidence.json.
- `act_train`: `37a8c833656a58ba25472e2106276f225e95ad26` · `scripts/train_act16w.py:19, 33, 52, 69, 70, 81, 82, 105`. 전체 hash/발췌는 evidence.json.
- `warp_queue`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `experiments/2026-10-16-warp8/native-gate-queue.json:4, 6, 7, 45, 46, 49, 50`. 전체 hash/발췌는 evidence.json.
- `warp_recount`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `experiments/2026-10-16-warp8/beam40-native-r1-summary.json:18, 19, 21, 29`. 전체 hash/발췌는 evidence.json.
- `warp_release`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `scripts/run_warp_flow_teacher.py:40, 43, 44, 79`. 전체 hash/발췌는 evidence.json.
- `warp_frozen`: `7c8acef516103ce5906b77d6481e46b298961b0c` · `scripts/warp_flow_episode.py:17, 18, 19, 180, 192, 302, 305`. 전체 hash/발췌는 evidence.json.
- `map_scene`: `c7477b1f64910f498b52e1697488c28b2c4569e1` · `scripts/mapbuild6_capture.py:78, 81, 88, 90, 156, 189, 197, 198, 199, 294`. 전체 hash/발췌는 evidence.json.
- `cpu_eval`: `c8dc1e6545124ed69a996618bd11df684d233969` · `scripts/run_grasp_act_student.py:77, 95, 102, 106, 118, 135, 223, 236, 239, 249`. 전체 hash/발췌는 evidence.json.
- `cpu_physics`: `c8dc1e6545124ed69a996618bd11df684d233969` · `sim/masterpi_drive_friction_v7.py:231, 255`. 전체 hash/발췌는 evidence.json.
- `llm`: `c8dc1e6545124ed69a996618bd11df684d233969` · `configs/model_endpoints.json:8, 9, 10, 11, 18, 19, 39, 42, 49, 52`. 전체 hash/발췌는 evidence.json.
- `cache`: `c8dc1e6545124ed69a996618bd11df684d233969` · `harness/rgb_communication_planner.py:27, 39`. 전체 hash/발췌는 evidence.json.
- `e2e`: `c8dc1e6545124ed69a996618bd11df684d233969` · `scripts/run_zone_study_integration.py:6, 9, 13, 57, 61, 190, 192, 198, 201, 202`. 전체 hash/발췌는 evidence.json.
- `scenario`: `c8dc1e6545124ed69a996618bd11df684d233969` · `sim/zone_scenario_scene.py:81, 82`. 전체 hash/발췌는 evidence.json.
- `input`: `c8dc1e6545124ed69a996618bd11df684d233969` · `harness/grasp_act_contract.py:1, 4, 28, 45, 58, 61, 71, 72, 73, 75`. 전체 hash/발췌는 evidence.json.
- `sensors`: `c8dc1e6545124ed69a996618bd11df684d233969` · `scripts/run_zone_study_sensors.py:1, 3, 6, 7, 10, 11, 14, 25, 43, 52`. 전체 hash/발췌는 evidence.json.
- `agents`: `c8dc1e6545124ed69a996618bd11df684d233969` · `AGENTS.md:13, 14, 15, 23, 24, 27, 37, 42, 44, 45`. 전체 hash/발췌는 evidence.json.
- `nsoff`: `757632c42ee93b873cd573999bdb074f7469b54c` · `sim/execution_contact_profile.py:11, 12, 13, 14, 15, 16, 21, 23, 28, 30`. 전체 hash/발췌는 evidence.json.
- `cpu_contact`: `c8dc1e6545124ed69a996618bd11df684d233969` · `sim/zone_cargo_contact.py:8, 14, 30, 33`. 전체 hash/발췌는 evidence.json.
- `heading`: `c8dc1e6545124ed69a996618bd11df684d233969` · `harness/path_heading_policy.py:1, 3, 4, 6, 14, 15, 16, 17, 20, 27`. 전체 hash/발췌는 evidence.json.
- `end_colors`: `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8` · `sim/grasp_act_scene.py:10, 11, 18, 21, 32, 33`. 전체 hash/발췌는 evidence.json.

## 남은 확인과 제출 경계

- mapbuild6는 LK/RBPF 판정 대기다. 모름을 최신으로 계산하지 않는다. ACT 교사의 truth-free 둘러보기는 실제 자기 RGB는 보지만 위치 추정이 없으므로 새 자기 지도 경로의 통합 증거가 아니다.
- act16w의 기록 완료/학습 시작 최신 소식은 공용 ops 보고에 있으나 이 작업에서는 원격 원본을 독립 확인하지 않았다. 회수 summary가 running인 상태를 complete로 고치지 않는다.
- CPU 확인은 허용된 비교이며 primary MJWarp의 예외를 명시한다. 과거 재생은 replay_of와 원래 source/manifest를 유지한다.
- 다음 큐는 실제 적용값을 stack_values 또는 기준표의 manifest 경로로 적고 점검 결과 JSON을 첨부한다. missing은 모름/차단이다. 승인된 이탈은 항목별 이유와 user/coordinator 승인 출처를 붙인다.
- 코드/설정만 확인한 L은 원본 런타임 검증을 대체하지 않는다. 특히 top 입력 금지·자기RGB 1장·캐시 순서·실제 GCP guards는 현재 공통 manifest 증거가 부족하다.
- 분석/원본은 기존 실행 호스트 보존. 이 감사는 로컬 Git object와 이미 회수한 가벼운 기록만 읽었다. 고칠 곳은 위 표에만 적었고 다른 작업자 파일·VM·실행을 수정하지 않았다.
