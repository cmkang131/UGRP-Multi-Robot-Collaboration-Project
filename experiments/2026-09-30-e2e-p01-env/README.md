# P01 최종 환경 등록 연결 — 정적 계약, 미봉인

Refs #218, #223. 기준 감사 `a8094cc14e098a55483f53a3c49bf6a0b116043d`, [READINESS S01](../2026-09-30-e2e-readiness/READINESS.md). 시작 main/worktree SHA `d17ca4345affef8cf027e121cf1f3197b36c23e0`, 브랜치 `codex/final-env-registry`. 코드 SHA는 이 기록을 포함한 PR 커밋과 [VERIFICATION.json](VERIFICATION.json)의 변경 파일 전체 해시로 식별한다.

## 변경과 보존

- `configs/zone_final_environment_registry_v1.json`은 기존 final catalog와 v3 scene catalog의 파일 해시를 참조하는 **DRAFT_UNSEALED** 계약이다. 지도 ID → 파일/파일 해시/정적 해시 → Scene factory → 로봇 모델 → provider/실제 실행 보정 지원을 연결한다.
- `harness.zone_environment_registry`의 정적 resolver를 시나리오 기본 validator/공개 map bundle, host의 Scene 선택/정적 지도, 실행 bundle에서 재사용한다. 알 수 없는 지도, map/model/static hash 불일치, provider/calibration 불일치와 표식 지도→무표식 provider를 factory 이전에 거부한다.
- 문 1개 지도는 기존 `GeometryCargoZoneScene` 그대로, 문 2개·복도는 새 `FinalGeometryCargoZoneScene` 어댑터로 표준 `CargoZoneScene`의 base scene/reset/transform을 재사용한다. cargo가 있으면 기존 pair-only placeholder 제거 의미도 그대로다. 혼합 주문 구현은 P02/P09 소유이며 이 PR로 해결하지 않는다.
- `sim/zone_geometry_scene.py`, `sim/session_scenes.py`, #249 `legacy_files_sha256`의 모든 파일, 원래 지도 3종·시나리오 6종·catalog bytes는 바꾸지 않는다. `pose_providers.json`, `vision_pose_source.py`, worker/model 등록부도 P03 소유이므로 수정하지 않는다.
- `run_bundle` 변경은 `runtime_files`/`run_bundle`에 제한한다. 실제 지도 경로를 `validate`와 `bundle_for`에 전달하고 등록된 환경만 `environment_binding`을 추가한다. 선택된 scene 모듈·catalog·registry·map을 해시로 기록한다. provider 기본값, 등록 실행 번들 ID, workflow 버전·기존 봉인 파일은 바꾸지 않는다. 최종 새 실행 ID와 봉인은 코디네이터에게 남긴다.

## 지원 판정

| 지도 | 장면 / 로봇 모델 | `vision_zero_tag_v2` / 보정 | 실행 판정 |
|---|---|---|---|
| `zone_wide_door_geometry_v2` | 기존 geometry / `masterpi_v2` | 기존 M1 dev 파일·SHA에 한정 | 기존 생성 계약만 허용, 물리 적합성 미확인 |
| `zone_wide_two_doors_final_v1` | 새 final geometry / `masterpi_v2` | P03 allow-list·새 지도 보정 미확인 | 거부 |
| `zone_wide_corridor_final_v1` | 새 final geometry / `masterpi_v2` | P03 allow-list·새 지도 보정 미확인 | 거부 |
| `zone_wide_door_geometry_v3`, `..._dock_v1` | 기존 v3 / `masterpi_v3` | v2 운동/카메라 보정은 v3 적합성 근거 아님 | 거부 |

`walls_v3`는 0.40 m 벽 프로필이며 `masterpi_v3` 로봇 모델과 별개다. 원래 최종 지도 3종은 v2 모델을 유지한다. 동일 ID에 v3 override를 허용하지 않는다. 최종 로봇 v3의 문 2개·복도 조합을 채택하려면 별도 지도/scene 버전·부모 hash와 새 provider/운동/카메라 보정을 등록해야 한다. 이번에는 미검증 새 v3 조합을 실행 가능하게 만들지 않았다. 모든 등록 항목은 `research_result:false`다.

## 검증 범위

[VERIFICATION.json](VERIFICATION.json)에 명령, 소스/보존 해시, 결과를 남긴다. `run_ci_tests.main`의 선택 파일 목록만 제한하고 공용 `local_lock_root`/`run_locked`를 그대로 사용했다. 점유 중인 다른 작업 잠금을 우회하지 않는다.

새 fake-seam 시험은 renderer·Scene 생성자·World 모듈·host·pose factory·worker·torch·socket·subprocess 호출을 금지한다. 3지도의 dict/fake scene factory, 6시나리오 validator/공개 지도 hash, 잘못된 지도/모델/hash/보정/표식 반례를 검사한다. 6시나리오 `run_bundle` 경로 시험은 **P03 지원 선언과 host_spec만 메모리 내 fake로 바꾼다**. 실제 미지원 provider/cargo 조합을 허용했다는 결과가 아니다. P03 확장 없이 문 2개·복도는 실제 allow-list 및 환경 계약 양쪽에서 거부되는 별도 양성 거절 시험이 있다.

기존 시험은 소스를 읽고 정적 범위만 선정했다. `test_zone_final_env`의 NumPy grid/reachability는 정적 CPU 계산이다. `test_zone_study_integration_seams`는 기존 태그 PF 생성/가짜 host/가짜 mj_forward만 사용한다. `test_zone_study_source_pinning`은 bundle/dict/fake wire이며 실제 LLM을 호출하지 않는다. `test_zone_masterpi_v3_scene`은 Scene/MjModel/mj_forward, `test_vision_pose_source` 전체는 관측 처리·worker subprocess, integration_pair 일부는 Scene/프레임 처리라 이번 실행 목록에서 제외했다. #249 봉인 해시는 새 시험에서 순수 bytes로 검증한다.

물리·시뮬레이션·렌더·학습·비전 추론·LLM 호출은 실행하지 않았다. 새 실험/평가 cohort가 없으므로 TensorBoard 재변환·서버·브라우저 작업도 없다. Drive 작업은 없다.

## 코디네이터 계획 — 3 × 30 SIM초, 아직 실행하지 않음

1. P01/P03/P02 합성·독립 검토 후 최종 로봇 v3 지도/scene 버전, 운동/카메라 보정, provider/segmentation 모델, 렌더/바닥·초음파 OFF·기억 설정을 같은 manifest에 고정한다. 현재 거부 항목이 남은 동안 실행하지 않는다. main+열린 PR의 최대 ID 뒤에서 새 실행 bundle/workflow를 등록·봉인한다.
2. 자기 worktree에서 표준 관리 CLI와 소유 세션으로 **지도별 1회 reset → 정지 30 SIM초**, 총 3회/90 SIM초 상한을 계획한다. 30초는 관측 제안 상한이다. 실제 reset 초기화 SIM초는 별도 기록한다. 공용 배타 잠금·10 GiB 여유·부하를 확인한다. 로봇 제어/LLM/teacher drive 없이 초기 배치를 검사한다.
3. 지도별 저장할 평가 증거: source/config/map 파일·정적·공개 hash와 실제 XML, robot model/robot XML hash, wall 0.40 m, tag texture/geom 0, cargo/로봇/벽 초기 겹침·접촉/관통, seeded reset의 출발 위치. 정답/접촉은 `eval_only`에만 둔다. 정적 해시 일치가 실제 reset/충돌 검사를 대신하지 않는다.
4. 실제 배치/FOV를 유지한 r1/r2/r3 자기 wrist RGB의 카메라 이름·크기·시각·원본 hash·좌우/축/팔 가림을 확인한다. TOP는 평가 영상으로만 보존한다. v3 arm mount/도크 이동, sag/pan 결합, 운동 profile(하중·정지 후 drift), 초기 prior 좌표/허용 오차를 새 보정으로 대조한다. v2 calibration bytes를 v3 성공으로 승계하지 않는다.
5. 실패/reset 불일치/초기 관통/카메라 오류/ENOSPC(HOST_ERROR)를 모두 보존하고 그 조합을 차단한다. raw는 기본 `outputs/` 절대 경로, hash/manifest/결과는 새 기록으로 남긴다. 새 실제 결과를 받은 뒤 TensorBoard snapshot/event/video/pin/HParams를 검증한다. 이 90초 계획은 경로 통과·파지·localisation 정확도·M1/M2/E2E 물리 성공 판정이 아니다.

## 참고 자료

- [#255 최종 지도·시나리오 기록](../2026-09-28-final-map-scenario-v2/README.md), [#249 v3 장면 기록](../2026-09-28-masterpi-visual-v3/README.md), [실행 버전 규칙](../../docs/execution_versioning.md).
- 기존 `zone_map_schematic`, `zone_study_scenarios`, 표준 `CargoZoneScene`/`GeometryCargoZoneScene` 재사용. 새 의존성·논문·외부 라이브러리 채택 없음.
- 채택하지 않은 방식: 봉인된 geometry `MAP_IDS` 직접 수정, 기존 map/scenario/catalog 덮어쓰기, 벽 v3를 로봇 v3로 해석, v2 보정을 미검증 지도/v3로 자동 확대, P03 provider 등록부 동시 편집.
