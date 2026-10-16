# E2E 첫 파일럿 준비 상태와 최소 연결 계획

작성일: 2026-09-30. 대상: [#216–#226 로드맵](../../docs/research_todo.md), 특히 [#224 E2E 첫 파일럿](https://github.com/kcm0127-dotcom/ugrp/issues/224).

**판정: 아직 실행 준비가 끝나지 않았다.** 단계별 성공 기록은 있지만, 최종 환경에서 출발·접근부터 목적지 방출까지 상태를 이어 쓰는 단일 실행과 네 통신 조건의 실제 한국어 다회 대화가 합쳐진 결과는 없다. 가장 먼저 닫아야 할 연결은 **최종 장면/주문 → 표식 없는 위치 제공자 → 실제 접근에서 얻은 정렬·파지 상태 → 운반·내려놓기·재측위·재파지 → 목적지 판정**이다. 문 단독 구간의 통과를 이 연결의 통과로 대신할 수 없다. 근거는 아래 S01–S15다.

## 1. 감사 기준과 증거 범위

- 작업/원격 기준: `codex/e2e-readiness`, `HEAD = origin/main = a8094cc14e098a55483f53a3c49bf6a0b116043d`를 시작 시 fetch 후 확인했다. 기본 체크아웃의 AGENTS.md와 작업 트리 지침 해시도 같았다. 이 문서의 코드 판정은 이 SHA에 한정한다. 다른 작업 트리·기본 체크아웃은 변경하지 않는다.
- 읽은 진입점: [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), [README](../../README.md), [현황 9/30 절](../../docs/current_status.md), [연구 TODO §0](../../docs/research_todo.md). GitHub 이슈 #216–#226 본문과 관련 PR을 조회했다. 과거 결과는 연결된 기록에서 인용했으며 raw 전체를 재계산하거나 새 실험을 실행하지 않았다.
- 이 작업은 **문서 감사·제안**이다. 물리 step, 시뮬레이션, 렌더, 학습/비전 추론, LLM 호출, 사전 등록 봉인, 병합은 하지 않는다. 검사는 [검증 기록](VERIFICATION.md)에 구분한다. 제안 예산은 실행 승인이 아니다.
- 9/30 현황 절은 `af96f664` 시점이다. 이후 main에는 [#288](https://github.com/kcm0127-dotcom/ugrp/pull/288)의 연쇄 전체 하드 한계 판정과 [#291](https://github.com/kcm0127-dotcom/ugrp/pull/291)의 정체 검출 조사가 있다. [#285](https://github.com/kcm0127-dotcom/ugrp/pull/285), [#292](https://github.com/kcm0127-dotcom/ugrp/pull/292), [#293](https://github.com/kcm0127-dotcom/ugrp/pull/293)은 조회 당시 열린 초안이다. [#294](https://github.com/kcm0127-dotcom/ugrp/pull/294)는 **#285의 feature 브랜치에 병합**됐으며 main 결과로 세지 않는다.
- 열린 작업 조회 SHA: #285 `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`, #292 `3afc61b00f2c127ac3fbe2be5e7bb57da989b15a`, #293 `d86cc82eedbe0c6693eaf808c54ce43387723f1d`; #294 head `9a63140edfaaf69f2ca92466384194d989e33c03`. 이들 PR의 수치는 **PR이 보고한 값**이며 이번 감사의 독립 실측이 아니다. 후속 작업은 착수 때 다시 조회한다.

### 이번 파일럿의 불변 조건

[로드맵 §0](../../docs/research_todo.md)과 [#223](https://github.com/kcm0127-dotcom/ugrp/issues/223)에 따라 `walls_v3`(벽 0.40 m), AprilTag 0개, 자기 손목 RGB·정적 지도·주문서·자기 발행 명령 이력만 제어 입력으로 쓴다. TOP와 정답 위치/관절/접촉/성공은 평가 전용이다. 동료 정보는 선언한 통신 채널로만 들어오며, 고정 enum 짝 상태 채널은 네 조건 모두 같다. `cargo_noslip_v1`, weld OFF, 실제 카메라/FOV 유지, 생각·발화 SIM 비용을 고정한다. 초음파는 이번 최소 경로에서 OFF로 제안한다. ON을 택하려면 별도 번들에 네 조건 공통으로 등록해야 한다([센서 규칙](../../docs/ultrasonic_range_sensor.md)).

**로봇 모델 v2와 v3, 밝은 바닥과 기본 바닥은 별도 실행 조건이다.** walls_v3라는 벽 이름은 로봇 모델 v3를 뜻하지 않는다. 본연구 초안 [B2](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md)는 로봇 모델 v3를 차단 선행 조건으로 둔다. 현재 제공자 allow-list는 v2 문 지도만 받으므로, 최종 모델·렌더·카메라 보정·분할 가중치를 먼저 한 묶음으로 결정해야 한다. v2의 작은 개발 시험을 본연구의 최종 환경 통과로 올려 적지 않는다.

### 성공을 붙일 실행 단위

한 `run_id`에서 초기 배치 이후 teacher 재배치·PF 정답 초기화·중간 결과 재생 없이 끝까지 진행해야 한다. `run_id → robot_id → job_id → phase/leg → command/frame → call_id/message → eval_only verdict`가 연결돼야 한다. 학생의 완료 주장과 심판의 배송 판정을 별도 보존한다. 단독 상자와 공동 봉을 함께 시험하면 세 번째 로봇도 자기 명령으로 참여해야 한다. 근거: [통합 러너](../../scripts/run_zone_study_integration.py), [PairExecution/PairTeam](../../harness/zone_pair_executor.py), [연쇄 기록기](../../harness/pair_chain_probe.py), [실행 버전 규칙](../../docs/execution_versioning.md).

## 2. 단계별 준비 상태

아래 **최소 시험은 연결 하나를 닫는 제안**이다. 성공률·안전성·새 지도 일반화를 확증하는 표본 수가 아니다. 비용은 물리가 진행되는 장면의 SIM초를 합산한 상한 제안이며, 로봇 수를 곱한 robot-seconds나 실제 경과시간(wall time)이 아니다. 순수 파일·가짜 포트 검사는 0 SIM초지만 CPU·검토 시간이 필요하다. 각 단계의 시험은 §4에서 묶어 재사용하므로 단순 합산하지 않는다.

### S01. 지도·시나리오·최종 모델 — #218

- **있는 것:** [최종 지도 목록](../../maps/zones_final/catalog.json), [시나리오 v2 6종](../../configs/zone_study_scenarios_v2/), `zone_final_env`, 표준 `Scene` 기반 [geometry 장면](../../sim/zone_geometry_scene.py)과 [모델 v3 장면](../../sim/zone_masterpi_v3_scene.py). [#255 기록](../2026-09-28-final-map-scenario-v2/README.md), [#249 기록](../2026-09-28-masterpi-visual-v3/README.md).
- **마지막 측정/조건:** #255 소스 `1cd68812`에서 지도 3+시나리오 6 정적 검사 9/9, 관련 단위 검사 90개. 원판 반지름 0.17/0.21 m의 격자 도달성이다. 물리·2인 전체 편대 통과 측정은 아니다.
- **미측정:** 새 두 지도에서 reset/seed 재현, 초기 접촉, v3 로봇으로 편대 통로 통과, 새 시야에서 위치 추정·파지. v2 시나리오의 2인 편대 정적 경로 재검사도 #255 기록에는 남아 있다.
- **빠진 연결:** `sim.zone_geometry_scene.MAP_IDS`와 `VisionPoseSourceV2.map_ids`는 문 1개 지도만 허용한다. `run_bundle()`의 `validate/bundle_for`에는 최종 지도용 `maps_dir_for()`가 전달되지 않는다. v3 장면은 있어도 `pose_providers.json`에는 v3 지도 등록이 없다. 장면 지도·공개 지도·provider·모델/보정 해시·episode를 같은 선택으로 묶어야 한다. [러너 349행 이후](../../scripts/run_zone_study_integration.py#L349), [provider 등록부](../../configs/zone_study_integration/pose_providers.json), [지도 resolver](../../harness/zone_final_env.py).
- **최소 닫기 시험:** P01의 파일/설정 검사 뒤 지도마다 1회 reset→30 SIM초 정지 캡처. 표식 texture/geom 0, 벽 높이, 실제 XML/공개 지도 해시, 자기 카메라·초기 겹침을 평가 기록으로 확인한다. 이것만으로 경로 통과를 선언하지 않는다.
- **예상 SIM 비용:** 정적 검사 0, 장면 3×30=90초(0.025 SIM-h). 초기화 비용도 결과 manifest에 별도 기록한다. 30초는 측정값이 아닌 제안 상한이다.

### S02. 표식 없는 위치 추정·초기화 — #216

- **있는 것:** [VisionPoseSource/V2](../../harness/vision_pose_source.py), [태그 카탈로그를 만들지 않는 초기화](../../harness/vision_motion_init.py), [worker 설정](../../configs/vision_loc_worker.json), VIS3 PF·분할 모델. own dock prior를 한 번만 주고 자기 영상·자기 명령으로 갱신한다. [#237 폐루프 기록](../2026-09-27-vision-worker-closed-loop/README.md), [VIS3 평가](../2026-09-26-vision-loc/README_v3.md).
- **마지막 측정/조건:** 새로 주행한 표식 0개 폐루프 dev는 `93936d36`, seed 942, r2 단독 1회다. 든 상자의 문 통과는 관찰됐으나 배송 실패(`CARRY_LEG_pose_uncertain`), 462.05 SIM초, 전체 위치 p90 32.1 cm·문 주변 8.9 cm. VIS3 독립 test 6회의 저장 영상 평가도 G2 p90 6.3 cm >5 cm로 FAIL. [VIS4](../2026-09-26-vision-loc/README_v4.md)·[VIS5](../2026-09-26-vision-loc/README_v5.md)와 [#264](https://github.com/kcm0127-dotcom/ugrp/pull/264) VIS6 재생은 채택 후보가 없었다. 서로 다른 코호트다.
- **미측정:** 현재 v2 provider와 최종 로봇/모든 지도에서 전체 주행, 집기 중 과신 회복, 큰 위치 오차에서의 회복, 최종 보정으로 문 오차 게이트. `research_result:false`를 true로 바꿔 해결할 수 없다.
- **빠진 연결:** 실제 runtime prior의 출처·허용 오차, v3 명령/카메라 기하와 VIS3 보정의 일치, 확정 분할 모델 배포·worker pin이 필요하다. 현재 worker는 `seg-v2` 해시 `34853903…`를 가리키며 밝은 바닥의 `C_mix_rgb`가 아니다. `VisionPoseSourceV2` 생성·프레임 지연·종료와 실행 번들 해시를 한 경로에서 검증해야 한다(P03).
- **최소 닫기 시험:** 가짜 worker로 미래/오래된 fix 거절과 prior 단회 설정을 검사한 뒤, 새 dev 출발 3개에서 실제 자기 prior→정지 관측→접근. GT는 사후 p90·σ 대비 실제 오차에만 사용한다. 통과하면 #216의 독립 test 게이트를 별도 새 표본으로 평가한다. 세 번의 개발 성공은 #216 완료가 아니다.
- **예상 SIM 비용:** 파일/가짜 worker 0; 3×300=900초(0.25 h) 개발 상한. #237의 전체 462초보다 짧은 접근 진단이다. 전체 M1 재검증은 S04/§4에서 따로 잡는다.

### S03. 내려놓기 체크포인트에서 재측위·재파지 — #216/#219

- **있는 것:** [ProviderM2DoorStudent._queue_grasp](../../harness/m2_provider_adapter.py), [begin_relocalization](../../harness/vision_pose_source.py#L123), [M2 checkpoint 상태](../../scripts/run_m2_pair.py), [B1 기록 #279](../2026-09-29-carry-relocalization-b1/README.md). 연쇄 기록기는 PF·명령 이력을 구간 사이에 유지한다([pair_chain_probe](../../harness/pair_chain_probe.py)).
- **마지막 측정/조건:** B1 고정 소스 `3b1877e5`, 표식 0개·벽 0.40 m·로봇 v2·문 1개·기본 바닥·`p20` 정지 화면, 7곳×2대×48 시작오차/PF 표본=672회. 위치 p50/p90 1.8/3.7 cm, yaw 0.27/0.56°, 7곳 모두 A. 참값 근처 prior에서 시작한 오프라인 평가이고 물리 0회다. [#282](../2026-09-29-seg-lightfloor/README.md)는 밝은 바닥에서 `C_mix_rgb`로 9개 체크포인트 9/9를 보고했다(정지 화면, runtime 미연결·Release 미배포).
- **미측정:** 실제 운반 후 잔류 흔들림/팔 처짐, 내려놓으며 움직인 빔, 이전 PF의 잘못된 모드·σ를 이어받은 재측위, 재파지 성공. `search` 자세는 B1 전체 수용 기준 FAIL이다. **7곳 전부 X라는 현황 요약은 원표와 다르다**: 기본 바닥/vision/wide/search는 `B X A A A B A`다. 판정은 원 보고서를 따른다.
- **빠진 연결:** B1은 필터를 새로 만들고 GT 근처 prior를 주지만, 실제 `begin_relocalization()`은 예측 belief를 보존하고 fix receipt만 지운다. 이미 있는 checkpoint 상태에 **이 실제 prior·지연된 fix·p20 8장·동일 보정**을 넣어 검증해야 한다. B1 helper의 GT 초기화·oracle 분할을 runtime으로 복사하지 않는다. `C_mix_rgb` 선택 시 P03에서 새 가중치/보정 설정을 추가한다.
- **최소 닫기 시험:** 문 앞·문 뒤·목적지 전 3곳에서, 이전 구간 명령을 실제로 실행한 뒤 lower→open→p20 scan→새 fix→re-align→grasp→lift까지 이어간다. `last_scan_t`, frame/capture/release 시각, posterior σ·평가 오차, 빔 이동을 기록한다. teacher로 각 checkpoint에 옮기면 별도 진단으로만 센다.
- **예상 SIM 비용:** 오프라인 계약 0; 3×120=360초(0.10 h) 단축 연쇄 상한. B1 인용값은 scan 8.4초, checkpoint 왕복 가정 18초×7=126초, 순수 carry 170.8초다. **126초는 이번 실제 전이 측정값이 아니다.** §4의 문 연쇄에 포함해 재사용한다.

### S04. 접근과 단독 배송 — #219/#221

- **있는 것:** [GuardedPairApproach](../../harness/zone_pair_guards.py), [PairOwnCamApproach](../../harness/pair_owncam_approach.py), [ZoneOwnExecutor](../../harness/zone_own_executor.py), [M1 delivery](../../harness/m1_owncam_delivery.py). 시작부터 M2 접근하는 경로가 있으며 단순한 stage probe 연결만 있는 것은 아니다.
- **마지막 측정/조건:** [M2 2c](../2026-09-26-zone-m2-pair/README.md) 옛 태그 v2 문 지도, 새 seed 831–836에서 접근 두 로봇 도착 ON/OFF 각각 6/6, 전체 운반 각각 5/6; s833 checkpoint 재측위 실패. [M1](../2026-09-26-zone-m1-owncam/README.md)은 `ca2fdb8`, 태그 지도, v9, test 101–106에서 4/6·거짓 성공 0(2회 ENOSPC). 표식 0개 최신 주행은 S02의 배송 실패 1회다.
- **미측정:** 최종 모델/무표식 환경에서 접근 종료 상태가 b-v6d/g/h 정렬 입력의 허용 오차에 드는지, 교차 접근 충돌, 세 번째 로봇과 동시 진행, 최종 M1 ≥5/6 게이트.
- **빠진 연결:** `make_plan()`의 빔 시트 허용 범위는 x 0.7–1.2, |y−0.05|≤0.15, |yaw|≤10°다. 실제 s1/s4의 빔 `(1.275,0.45,1.5708)`은 이 범위 밖이다. provider의 실제 접근 posterior/servo/history를 정렬에 넘겨야 하며, probe의 준비 자세로 덮으면 안 된다. [plan 검사](../../harness/zone_pair_executor.py#L28), [s1 v2](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json).
- **최소 닫기 시험:** P02/P04로 계약을 확인한 뒤 새 dev 출발 3개에서 접근→정렬 진입까지, 그다음 같은 소스로 M1 새 6개를 전체 실행한다. 각 단계 미도달도 분모에 남긴다. 색/물건 확대는 S13의 별도 능력 검증이다.
- **예상 SIM 비용:** 접근 3×300=900초(S02와 같은 실행, 중복 합산 안 함); M1 6×900=5,400초(1.5 h). 900초는 제안 cap이고 과거 성공 약 503–544초를 참고했다. 새 환경의 실제 시간은 모른다.

### S05. 정렬 — #220/#221

- **있는 것:** [zone_pair_align](../../harness/zone_pair_align.py), [fine motion](../../harness/owncam_align_motion_v6d.py), [wide-hue beam](../../harness/owncam_pair_beam_v6d.py), [#265 기록](../2026-09-29-pair-v6d-align/README.md).
- **마지막 측정/조건:** b-v6d 25/25(독립 궤적 19/19), 이전 b-v6c 13/25. 태그 개발 지도, teacher/E2E checkpoint에서 시작하는 **한 단계** 격자, 실패 셀을 보고 수정한 dev 결과다. 정렬 34.0–38.6 SIM초. 25셀 실행 트리 `052e3eba`; 등록 v80 트리 `4714263a`의 재확인은 부분 6셀이다.
- **미측정:** 표식 없는 provider의 실제 접근 오차, v3 외관/명령 기하, 그림자·가림, 최종 바닥에서 독립 격자. 25/25를 새 위치 추정기까지 포함한 성능으로 승계할 수 없다.
- **빠진 연결:** 자기 영상의 beam-relative 신호와 전역 posterior의 상호작용, `align_fine_motion` 프로필 시작/복귀, fix 시각과 내려온 팔의 fresh frame 판정을 P03/P04에서 이어 검사한다. 광학 정렬 성공이 목적지 좌표 정확도를 보증하지 않는다.
- **최소 닫기 시험:** 실제 접근을 마친 정상/횡 편향/yaw 편향 3개를 **그대로** 정렬→preclose까지 실행. 자기 영상 receipt와 eval-only 상대 오차를 비교하고, 가려진 영상 1개는 닫기 거부로 끝나야 한다. 최종 #220 격자 검증은 별도다.
- **예상 SIM 비용:** 4×60=240초(0.067 h), 정상 3개는 S04와 한 실행으로 묶는다. cap 60초는 기존 약 39초+실패 관찰 여유의 제안이다.

### S06. 파지·들기 — #219/#221

- **있는 것:** [PairGraspRelook](../../harness/zone_pair_grasp.py), [v6c entry](../../harness/zone_pair_grasp_entry_v6c.py), [hold/lift 판단](../../harness/owncam_pair_lift_v3.py), [v6c 기록](../2026-09-29-pair-v6c/README.md), [v6d 회귀](../2026-09-29-pair-v6d-align/README.md).
- **마지막 측정/조건:** b-v6c/b-v6d 22/23, 같은 dev 허용 오차 경계·E2E 정합 prior, 태그 개발 지도·teacher staging·weld OFF. 단계 7.3 SIM초. 실패 `corner+−+`는 r2 `LOAD_NOT_HELD_AFTER_LIFT`. v6d 최종 트리 단계3 23셀 재확인은 있지만 E2E 접근은 아니다.
- **미측정:** 실제 무표식 정렬 종료 분포에서의 두 손 접촉/상승/retention, 새 모델과 바닥, 모든 checkpoint 재파지의 누적 실패, 그림자·가림 거짓 확신(#220).
- **빠진 연결:** `preclose_check`→신선한 자기 프레임→`grasp_confirmed`→carry barrier의 출처를 보존해야 한다. status heartbeat 단절·상대 실패·invalid image가 남은 팔/주행 명령을 취소하는지 확인한다. 교사 힘/GT 높이로 `held`를 주입하지 않는다. 기존 `ArmSequence`는 명령 helper로 쓰되 teacher 계획기를 호출하지 않는다([m2_controller](../../harness/zone_pair_executor.py#L134)).
- **최소 닫기 시험:** S05 정상 3개에서 실제 close→lift→짧은 hold, 추가 한쪽 파지 실패 1개에서 동기 정지. 평가 접촉·높이는 성공 채점에만 기록한다. 미관측을 held로 취급하지 않는 반례를 P04에 넣는다.
- **예상 SIM 비용:** 4×30=120초(0.033 h), S05/문 연쇄 안에 포함 가능. 30초 cap은 7.3초 단계+유지·실패 전파 관찰 여유다.

### S07. 짐을 든 문 통과·전체 운반 — #216/#221

- **있는 것:** [RoutedM2.door_schedule](../../harness/zone_pair_executor.py#L199), [carry model](../../harness/owncam_carry_v6e.py), [정책 등록](../../harness/zone_pair_v6_policy.py), [chain probe](../../harness/pair_chain_probe.py). 등록 main은 v81/b-v6g 계열이고, v6h1은 #292 초안이다.
- **마지막 측정/조건:** [#278](../2026-09-29-pair-v6e-carry/README.md) hR2 56/70, 문 L0+L1만 6/20. L0만 E2E와 같은 시작이며 L1–L6은 GT로 옮긴 배치·기록 prior다. [#281](../2026-09-29-door-guard-relax/README.md) 가드 완화 `k1g` 17/20도 단독 구간이다. [#283](../2026-09-30-door-relax-envelope/README.md)의 L0→lower/open/regrasp→L1 연쇄는 b-v6g 0/10, k1g 0/20, 진행 감시를 완화한 k1g+p1/p2 14/20(유효 10개, 2배치). 모두 개발 지도·teacher 첫 staging이며 최종 walls_v3 무표식 E2E가 아니다.
- **더 최신이지만 미병합인 측정:** #285/#294는 gain+axial-lag ON 29/29배치·58/58케이스, 벽 접촉/하드 위반 0을 보고한다. 이는 기존 dev 연쇄이고 새 60개 확증·처음부터 접근·최종 무표식 환경 검증이 아니다. #292는 등록 구현 309 단위 검사 통과를 보고하나 인수 재생·분류기 통합·봉인은 남았다. #294가 #285로 병합된 상태를 main의 성능으로 합산하지 않는다.
- **미측정:** 최종 지도/로봇에서 실제 접근부터 들어온 PF로 L0–L7 전체, 실제 막힘 시 멈춤/복구, v6h1 등록 코드와 탐색 probe의 동작 일치. 문기둥의 시각/충돌 geometry 차이와 높은 벽 접촉도 다시 확인해야 한다(#283 양성 대조는 낮은 divider와 뒷바퀴).
- **빠진 연결:** #292의 미해결 classifier pin·일반 setdown/teacher 준비 창 정의, 최종 소스 인수 뒤에 무표식 provider와 checkpoint 주기를 연결한다. gain/lag 보정만으로 p2f의 미무장을 해결하지 못한다(S09). 바뀐 문 가드를 무조건 새 기본값으로 켜지 않는다. **TOP yaw 추정 제안은 이 파일럿 입력 경계에서 제외**한다.
- **최소 닫기 시험:** 코디네이터가 #294 지정 골든 5개를 등록 후보로 인수 재생한 뒤, 최종 환경에서 접근부터 L0→재측위/재파지→L1까지 3개 새 dev를 실행한다. 그다음 같은 소스로 L0–L7와 목적지까지 이어간다. 동일 명령 SHA만으로 물리 접촉·하드 한계 일치 검사를 대신하지 않는다.
- **예상 SIM 비용:** 인수 5×180=900초(0.25 h), 무표식 문 연쇄 3×300=900초(0.25 h) 제안. 전체 carry 계획 170.8초+checkpoint 가정 126초에 접근·정렬·실패 관찰 시간을 더해야 하므로 전체 1회는 900초 cap으로 잡는다. 인수는 최종 환경 성능 분모에서 제외한다.

### S08. 목적지 내려놓기·방출·완료 확인 — #219/#221

- **있는 것:** b-v6e 이후 [광학 검정 기준 영상 유효성/한정 후진 정책](../../harness/zone_pair_v6_policy.py), [목적지 chain 평가](../../harness/pair_chain_probe.py), [평가 심판](../../harness/zone_study_referee.py).
- **마지막 측정/조건:** [#278](../2026-09-29-pair-v6e-carry/README.md) b-v6e, 소스 `d08818ef`, 목적지 계획19 중 staging 가능한13 **13/13**. 전부 놓은 뒤 후진이 `SWEEP_GUARD_VETO_AFTER_RELEASE`로 막혀 멈춘 통과(12.7–13.1 SIM초)다. 6개 staging 불가도 기록돼 있다. 이전 b-v6c 0/13은 `OWN_IMAGE_INVALID`였으며 최신 결과로 쓰지 않는다. 최종 b-v6g 소스·held-out·실제 전체 운반 후 결과는 아니다.
- **미측정:** 누적 운반 오차가 있는 목적지 진입, 두 손 release·안정 착지·영역 전체 포함, 다음 작업을 위한 충분한 후퇴, 자기 완료 주장과 referee 일치. 13/13은 충돌 없이 다음 임무를 시작할 수 있음을 뜻하지 않는다.
- **빠진 연결:** 마지막 leg의 inset/종료 좌표와 실제 목적 구역 판정을 맞추고, `job_summaries` 종료와 평가 성공을 분리한다. setdown 거부/부분 방출에서도 raw와 실패가 남아야 한다. #292/#294의 일반 setdown·준비 창 정의가 먼저 정해져야 전체 chain 판정이 안정된다.
- **최소 닫기 시험:** 정상/구역 경계/어두운 바닥 3개를 직전 leg부터 방출·정지·자기 재관측까지 실행한다. 일부만 영역에 걸친 물체와 잡고 있는 물체를 referee가 배송으로 세지 않는 fake-truth 반례(P06)를 먼저 검사한다.
- **예상 SIM 비용:** 3×60=180초(0.05 h) 단축 연쇄 상한. 전체 E2E 안에서 도달한 경우 그 실행에 포함한다.

### S09. 정체 감지·정지·복구 — #216/#221

- **있는 것:** ProgressMonitor와 probe 전용 완화([zone_pair_progress_relax](../../harness/zone_pair_progress_relax.py)), [#291 조사/오프라인 D1](../2026-09-30-stall-detection-research/README.md), 열린 [#293 D1 초안](https://github.com/kcm0127-dotcom/ugrp/pull/293). 신뢰할 수 있는 든 쌍 정체 대응은 아직 없다.
- **마지막 측정/조건:** #283 양성 대조의 막힌 8/8을 제어기가 감지하지 못했다. #285 p2f도 208건 모두 무장 0. #291은 기존 자기 영상에서 사후 선택한 D1 비율 0.4/2연속으로 정체 18/18(9케이스×2대), 이동 오경보 0/90, 지연 중앙1.6초·최대5.4초를 보고했다. 막힘은 한 유형, 실질 독립 2–3개, 렌더 조명 무늬에 의존한다. 새 물리 확증이 아니다.
- **미측정:** 시작부터 막힌 경우, 저속 정상 이동, 빔 끝 걸림/한쪽 장애/미끄러짐, 최종 밝은 바닥·모델 v3, 검출 뒤 안전한 중단·재시도. #293도 시작부터 막힌6개를 모두 놓치면 전체 기준을 못 넘는다고 명시한다.
- **빠진 연결:** D1 경보/unknown→자기 executor 사건→남은 명령 취소→짝 enum 정지→LLM 재판단의 계약이 없다. 먼저 #293을 검토하고 관찰 전용 모드로 검증한다. GT 접촉 라벨로 로봇을 멈추거나 진행 감시를 꺼서 성공으로 세지 않는다. 자동 후진/재파지는 별도 검증 전에는 지원하지 않고 안전 종료로 보고한다.
- **최소 닫기 시험:** P08의 가짜 프레임/명령·중단 전파 검사 후, 코디네이터가 새 정체5종×6=30, 정상3leg×5속도×4=60의 사전 등록을 확정한다. 경보를 제어기에 연결한 최종 후보에서 정상 이동·중간 정체·시작 정체 각 1개로 중단 흐름을 검증한다. 이 3개만으로 D1 정확도 통과를 대체하지 않는다.
- **예상 SIM 비용:** fake 검사 0. #291의 시험 제안은 **2–3 SIM-h**이며 미실측 추정이다. 계획 상한으로 90×120=10,800초(3 h), 별도 중단 흐름 3×120=360초(0.10 h)를 잡는다. staging 초과 시 코디네이터가 실행 전에 예산을 다시 정한다.

### S10. 한국어 LLM 다회 드라이버·전송/사용량 원장 — #222

- **있는 것:** [LiveDriver/MainStudySendLedger](../../harness/zone_study_llm_driver.py), [MainStudyBudget](../../harness/zone_main_budget.py), [한국어 prompt v3](../../harness/zone_study_prompts_ko.py), [프로필](../../configs/zone_study_integration/llm_driver.json), [실패 규칙](../../docs/zone_study_llm_failure_rules.md). #256의 10/30 상한 prompt 불일치는 후속 수정으로 고쳐져 있다. PR 본문의 오래된 “남은 문제”를 그대로 승계하지 않는다.
- **마지막 측정/조건:** [#238 기록](../2026-09-27-zone-study-pilot/README.md), s1 seed11의 **첫 호출만** 17회: v63 16/16 정상 채택, v62 JSON fence 1회 거절, 17/17 과금 대조. 물리 0회·실제 다회 대화/E2E는 아니다. [#256](https://github.com/kcm0127-dotcom/ugrp/pull/256)의 드라이버 검사는 fake wire이며 실제 상류 모델 검증이 아니다.
- **미측정:** 최종 executor 작업 경계에서 새 호출·받은 한국어에 따른 재결정, 실제 provider finish_reason/토큰·지연, 장시간 오류·상한, 한국어 왕복 대화와 실제 행동의 연결.
- **빠진 연결:** 새 prereg에 모델/실효 모델·temperature/effort·speech profile·cohort cap·미상 사용량 과금·새 DB 경로를 고정해야 한다. 기존 #222 DB를 재사용/리셋하지 않는다. `call_id → send ledger → raw wire → proxy receipt → upstream attempts/usage`가 같은 실행으로 정산돼야 한다. DB 존재나 HTTP 수만으로 정산 완료라 하지 않는다.
- **최소 닫기 시험:** P05에서 4조건×3로봇×2턴 이상 fake wire, 429/503·비정상 finish·ENOSPC·late reply를 검사한다. 실제 호출은 코디네이터가 최종 환경에서 로봇당 최소2턴의 작은 연결 시험 후 전체 파일럿을 실행한다. 한국어 literal ID·실제 send/reply·원문 보존을 확인한다.
- **예상 SIM 비용:** fake wire는 물리 0. 실제 짧은 연결 4×120=480초(0.133 h) cap 제안이나 모델 지연의 SIM 부과로 2턴에 못 닿으면 실패/미도달로 남긴다. 호출 비용은 SIM과 별도다. [#254 초안 §10](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md)의 첫 호출 평균10,899 토큰은 다회 호출의 검증된 비용이 아니다.

### S11. 평가 전용 심판과 숨은 사건 — #223/#224

- **있는 것:** [Referee/HiddenEventSchedule](../../harness/zone_study_referee.py), [물리 사건 훅](../../sim/zone_hidden_events.py), [run_loop/write_outputs](../../scripts/run_zone_study_integration.py#L472), [#257 설명](../../docs/zone_study_integration.md). `orders_complete`는 host 종료·평가에 쓰고 로봇 입력/깨우기에 전달하지 않는다.
- **마지막 측정/조건:** #257이 보고한 실제 host 물리 probe 11/11, 별도 fake-truth/입력 경계 검사. [9/29 현황](../../docs/current_status.md)의 남은 항목은 s2/s3/s5 **전체 장면 실행**이다. hook만 켜지는 것과 실제 사건을 경험한 것은 다르다.
- **미측정:** 최종 모델/새 지도에서 s2 막힘이 관측되기 전 정보가 새지 않는지, s3 지연이 실제 집결에 영향을 주는지, s5 62.5초 낙하 때 물체를 이미 들고 있는지. 이벤트가 no-op이면 조작 성립으로 세지 않는다([s5 설정](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json)).
- **빠진 연결:** scenario item_id와 host objects 및 referee 주문의 일치, `placements_match`, 혼합 물건 truth adapter, 한 물건 중복 차감 방지. 늦은 성공/부분 착지/아직 잡고 있음/시작 전 실패가 공통 종료 기록에 연결돼야 한다(P02/P06).
- **최소 닫기 시험:** fake truth로 이동·회전·부분 착지·붙잡힘·같은 색 다른 개체·반복 완료를 검증하고, 코디네이터가 s2/s3/s5 각1회를 사건 전부터 종료까지 실행한다. 평가 사건만 바꾸고 자기 RGB/명령을 고정했을 때 model payload와 wake가 불변이어야 한다.
- **예상 SIM 비용:** fake 0. 짧은 사건 도달 확인 3×120=360초(0.10 h) 제안은 조작 여부만 본다. **전체 장면 검증은 3×1800=5,400초(1.5 h)**이며 §4의 24회 no-LLM 집합 안에 포함한다.

### S12. 네 통신 조건·동일 실행기·SIM 비용 — #223

- **있는 것:** [CONDITIONS](../../harness/zone_study_contract.py), [protocol](../../harness/zone_study_protocol.py), [IntegratedTrial](../../harness/zone_study_integration.py), [PairStatus](../../harness/zone_pair_status.py), [SIM cost](../../harness/zone_sim_cost.py). `no_comm / peer_ko / leader_ko / structured`; leader는 seed%3 순환, reference_R은 주4조건 밖이다.
- **마지막 측정/조건:** [#229 통합 기록](../2026-09-26-zone-study-integration/README.md) 태그 임시 provider·fixture·seed700의 4조건에서 배송 모두2/3, 거짓 확인0. v1은90/90 호출 상한을 썼고 v2 `9f7b16f2`에서 타이머 연쇄를 수정했다. [#245](../2026-09-27-zone-study-multiturn/README.md) 다회 fake 회귀502개는 물리·모델0이다. 대화 효과 측정은 없다.
- **미측정:** 최종 무표식 혼합 임무의 네 조건, 모든 leader ID, 실제 message→다음 결정→수락한 명령, host가 역할/경로/중재를 대신 정하지 않는 전체 흐름.
- **빠진 연결:** 동일 scene/seed/모델/하위 정책/예산에서 조건만 바뀌는 새 episode 코호트, pair status 설정 해시, participant 격리와 자기 작업 경계의 호출 시각을 고정한다. provider config에는 추론 SIM 비용 미부과 문구가 남지만 실제 통합은 [고정 지연 wrapper](../../harness/zone_study_pose_delay.py)로0.16초를 부과하므로 **실효 적용값**을 확인한다. LLM think/talk 비용과 중복 계산하지 않는다.
- **최소 닫기 시험:** P05의 no_comm inbox0·follower 간 직접전송0·structured 자유문0·동료 비공개 상태 변이·GT/TOP 변이 불변성 검사. 다음 실제 fixture 4조건×같은3seed(leader r1/r2/r3)를 실행하고 후속 메시지가 자기 job 경계에서 처리됐는지 확인한다.
- **예상 SIM 비용:** fake 0; 12×1800=21,600초(6 h) 최대. §4의 24회 집합에서 leader 회전이 충족되도록 배정해 중복 실행을 줄일 수 있지만, 동일 배치3seed 반복과 시나리오6종 커버리지는 서로 다른 축으로 남긴다.

### S13. 관측 기억·물건 종류·역할 선택의 범위 — #217/#219/#220/#223

- **있는 것:** [memory_v3](../../harness/owncam_memory_v3.py), [own memory 경계](../../harness/owncam_memory_inputs.py), [wrist perception](../../harness/wrist_zone_skill_v9.py), [executor_plan](../../harness/zone_study_integration.py#L262), 시나리오6종. 이는 부가 기능이 아니라 전체 시나리오를 통과하려면 확인해야 하는 범위다.
- **마지막 측정/조건:** [연구 TODO](../../docs/research_todo.md)는 memory_v2 태그 제공자 test OFF4/6·ON3/6으로 이득 기준 미충족, memory_v3(#234) 병합으로 기록한다. [#220](https://github.com/kcm0127-dotcom/ugrp/issues/220)은 인식 v3 test10/10과 그림자 확신오류1건·가림7/100을 함께 남겼다. 최종 무표식 v3/새 바닥의 정확도로 승계하지 않는다.
- **미측정:** 새 환경 기억 ON/OFF, 비청록 물건·캔·타일·heavy_crate 자기 카메라 수행, 파트너 r3 재배정·서로 바뀐 역할, 이동한 특정 개체의 재식별.
- **빠진 연결(코드상 확정):** `ZoneOwnExecutor.deliver()`는 cyan 외 `KIND_NOT_SUPPORTED_BY_M1_SKILL`; `executor_plan()`은 2대 long_beam 한 개만, r1/end_neg·r2/end_pos 고정이다. `host_spec()`은 pair-only 주문+order_id=item_id를 요구하고, geometry 장면은 cargo가 있으면 색 상자 placeholder를 지운다. 반면 s1/s3/s4는 혼합 주문, s2는 heavy_crate, s6는 90° 회전·순서 관계를 요구한다. **시나리오 JSON만 바꿔 연결되지 않는다.** [host_spec](../../scripts/run_zone_study_integration.py#L318), [geometry _resolve](../../sim/zone_geometry_scene.py), [6종 설정](../../configs/zone_study_scenarios_v2/).
- **최소 닫기 시험:** P02로 cyan1+long_beam1 혼합을 별도 새 dev scenario에서 정상/미지원 거절까지 검사한다. P09로6종×물건/역할/경로/사건 지원 표와 구현 단위를 확정한다. 초기 파일럿은 memory OFF 또는 명시한 고정 버전으로4조건 동일하게 둔다. 기억 이득 비교·모든 화물 확장은 해당 기능을 구현한 뒤 별도 새 물리 시험으로 닫는다.
- **예상 SIM 비용:** 지원 표·계약0. 각 신규 물건/역할 최소1 정상+1실패의 물리 검증은 **기능당2×900=1800초(0.5 h)** 제안; 기능 수·지원 범위가 고정되지 않아 전체 추가 비용은 미산정이다. 최소 혼합 E2E는 §4의4회 집합에 포함한다.

### S14. 원본 기록·TensorBoard·평가 전용 TOP — #226

- **있는 것:** [write_outputs/write_study](../../scripts/run_zone_study_integration.py#L588)의 자기 입력·명령·wire·ledger·`eval_only`·manifest, [eval TOP profile](../../sim/zone_eval_top.py), [TensorBoard exporter](../../scripts/tensorboard_tools/), [캡처 프로필 #241](https://github.com/kcm0127-dotcom/ugrp/pull/241), [TensorBoard 절차](../../docs/tensorboard.md).
- **마지막 측정/조건:** [#237 snapshot](../2026-09-27-vision-worker-closed-loop/README.md)은65항목 readback 불일치0,3run 표시를 당시 확인했다. [#283](../2026-09-30-door-relax-envelope/README.md)은 해당 연쇄 snapshot 기록을 남겼다. 이 감사에서 기존 서버나 화면을 새로 열어 확인하지 않았고, 현재 E2E snapshot은 없다.
- **미측정:** 최종 단일 실행의 모든 실패/중단 포함 완전성, 원래 요청 이미지·응답·정산의 같은 분모, 실제 TOP 영상 등록. `top_camera.json`은 카메라 설정이며 영상 파일 존재를 증명하지 않는다. GT 위치 그림도 TOP RGB 촬영이 아니다.
- **빠진 연결:** 새 run manifest→공통 workflow 기록→완료/실패 ledger→export→event readback→영상 링크/고정 카드까지 P06에서 묶는다. `eval_only` 경로 분리만으로 비누출이 입증되지는 않으므로 요청 digest·깨우기 변이 검사가 함께 필요하다. dev1Hz 캡처 최적화는 미검증 상태로 적용하지 않는다. D1에는0.1초 쌍이 필요하므로1Hz 저장만으로 재현할 수 없다([#291 §2.1/2.5](../2026-09-30-stall-detection-research/README.md)).
- **최소 닫기 시험:** synthetic 완료/실패/ENOSPC 기록의 누락·변조를 검출하고, 첫 실제 결과에서 source hash→event 값→기본 logdir/영상 등록→브라우저 표시를 대조한다. 성공·SIM시간·명령수·모델호출·응답시간을 pin한다. 공용 설정은 쓰기 직전 다시 읽고 자기 키만 추가한다.
- **예상 SIM 비용:** 변환·readback·화면 확인0, 촬영은 해당 E2E 실행 비용에 포함. 원본은 기본 체크아웃 `outputs/` 절대 경로, 보존/공유는 [디스크 규칙](../../docs/disk_management.md)을 따른다. 현재 대시보드 주소는 절차상 [127.0.0.1:6006](http://127.0.0.1:6006)이며 이번 감사의 live 확인 링크가 아니다.

### S15. 교사 사용은 staging/시연·평가에 한정 — #225

- **있는 것:** [teacher 실행기](../../scripts/run_zone_teacher_fix.py), [feasibility gate](../../harness/zone_teacher_gate.py), [stage probe](../../harness/pair_stage_probe.py), [#207 기록](../2026-09-26-zone-teacher-fix/README.md).
- **마지막 측정/조건:** `3885fdf`, 새 seed21–23 교사 feasibility5/8, TOP green 검출 N1 미해결. GT/IK 교사·fixture·noslip·weld OFF이며 학생 성공이 아니다. stage/chain probe는 첫 자세를 교사가 만들어 준다.
- **미측정:** 같은 최종 모델/환경에서 모든 staging 셀의 적합성·물리 실현성, teacher 없이 전체 pipeline 시작. 교사 성공을 늘려도 학생의 S02–S09가 닫히지 않는다.
- **빠진 연결:** 초기 배치/교사 준비 종료 시각을 기록하고 student 시작 이후 teacher mutation·GT 초기화·성공 receipt가0임을 확인해야 한다. E2E에서는 scenario reset 외 teacher 준비를 사용하지 않는다. `ArmSequence`처럼 명령만 실행하는 공용 helper와 GT teacher plan은 구분한다(P04/P07).
- **최소 닫기 시험:** mock world의 privileged read/write를 student 시작 이후 금지한 계약 검사; 코디네이터는 정상/불가능 staging 각1개로 준비 실패가 학생 실패와 구분되고 원본이 남는지 확인한다. 이후 E2E run에는 teacher 진입점이 호출되지 않아야 한다.
- **예상 SIM 비용:** 정적/가짜 검사0; staging audit2×30=60초(0.017 h) 제안. 새 teacher E2E 코호트는 첫 학생 파일럿의 필수 경로가 아니다. 필요한 초기화/물리 실현성만 검증한다.

## 3. 지금 병목인 연결을 한눈에 보기

| 우선순위 | 연결 단절 | 바로 할 일 | 담당/동시 진행 |
|---|---|---|---|
| P0 | 최종 scene/모델/provider/보정이 한 구성으로 등록되지 않음 | P01+P03, 동일 manifest로 검증 | Codex, 서로 파일 소유 조율 후 병렬 가능 |
| P0 | 혼합 주문·item ID·물건/역할/경로 지원 부족 | P02(작은 혼합 연결), P09(6종 전체 차이) | Codex, P01과 병렬 가능; 물리 지원은 코디네이터 |
| P0 | stage 준비 상태와 실제 접근/재파지 posterior 사이 미검증 | P04, S02–S08 최종 모델 연쇄 | Codex 계약; 코디네이터 물리, 순차 |
| P0 | v6h1 등록/분류/인수와 D1 감지/반응이 각각 미완료 | 기존 #285/#292/#293 작업 재사용, P08 | Codex는 중복 구현 없이 검토/가짜 어댑터; 코디네이터 물리 |
| P1 | 다회 실제 한국어 판단과 물리 job 경계 미검증 | P05, 최종4조건 연결 시험 | fake 부분 병렬 가능, 실제는 앞 관문 뒤 |
| P1 | 같은 run의 평가·원장·영상·TensorBoard 연결 미검증 | P06 | synthetic 검사는 병렬; 화면 확인은 새 결과 뒤 |
| P1 | 실행 범위/분모·실효 모델·예산·source freeze 미확정 | P07 | 초안 생성은 병렬, 봉인은 모든 변경/검토 뒤 |

여기서 Codex는 **코드 계약·단위/저장 자료 검사까지만** 맡고, 렌더·시뮬레이션·모델 호출·물리 결과 채택은 코디네이터가 한다. 본 문서는 이 작업 프롬프트들을 실행한 결과가 아니다.

## 4. 가장 짧은 실행 순서와 예산

### 4.1 먼저 범위를 명시한다

빠르게 확인할 첫 실행은 **문1개 최종 환경 + cyan1개와 long_beam1개 + 세 로봇 + 네 통신 조건**의 새 개발 시나리오로 제안한다. 이는 현재 하위 기술의 지원 범위를 먼저 연결하는 시험이다. 기존 s1–s6 주문·배치를 덮어쓰지 않는다. 고정 r1/r2 역할을 쓴다면 그 제약을 이름/manifest에 표시하며 자율 파트너 배정 성공이라고 하지 않는다(S13).

**이 작은 시험으로 #224 전체 마일스톤을 완료 처리하지 않는다.** #224는 no-LLM24회 뒤 LLM 파일럿을 요구한다. [본연구 초안](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md)은6시나리오×3seed×4조건=72회 외부 파일럿을 제안한다. 작은 연결 확인(아래 C5), 마일스톤 스모크(C6), 본연구 파일럿(C7)은 서로 다른 분모다. P09로 미지원 능력을 해결하지 않으면 C6/C7은 진행할 수 없다. 로봇 모델 v3·무표식 입력·4조건 등 최종 조건은 작은 시험에서도 생략하지 않는다.

### 4.2 의존성과 중단 조건

```text
C0 범위/최종 구성 선택
 ├─ [병렬] P01 지도/scene + P03 provider/모델
 ├─ [병렬] P02 혼합 주문 + P09 전체 지원 범위
 ├─ [병렬] P04 상태 연결 + P05 대화/원장 + P06 평가/기록
 └─ [병렬] P07 미봉인 manifest + P08 정체 계약(기존 PR 의존)
            ↓ 코드 합성·독립 검토·새 source/bundle 고정
C1 최종 장면 reset/접근/파지/재측위 단축 확인
            ↓
C2 등록 후보 인수 → 최종 무표식 문 연쇄 → 목적지 연쇄
            ├─ C3 D1 확증/중단 흐름(물리 슬롯은 직렬; 분석은 병렬 가능)
            ↓ C2와 C3 모두 충족
C4 새 M1/M2 전체 재검증 (#219)
            ↓
C5 작은 혼합 ONE-run ×4조건 (고정 결정 → 실제 다회 한국어)
            ↓ P09의 모든 필요한 능력도 검증됨
C6 6개 시나리오 no-LLM 24회 → 사건 성립·거짓 성공0·경계 감사
            ↓
C7 범위 고정한 실제 LLM 파일럿 → 원장 정산·TensorBoard·실패 포함 보고
```

| 관문 | 가장 작은 실행과 통과 증거 | 제안 SIM 상한/근거 |
|---|---|---:|
| C0 | P01–P09의 승인 대기 없는 준비·가짜 계약. 새 후보는 미봉인 상태로 검토하고 마지막에 코디네이터가 source/배치를 고정 | 0 |
| C1 | 3지도×30초 reset, 실제 출발3개×300초(접근/정렬/파지·첫 재측위 포함), invalid-frame/한쪽 파지실패 각1개×60초. 실패하면 그 연결부터 수정 후 새 후보로 | 1,110초 = 0.31 h. S01–S06의 축약 묶음 |
| C2 | #292 인수5개×180초 + 최종 문 연쇄3개×300초 + 목적지 직전 leg3개×60초. 실제 predecessor 상태를 쓰고 첫 teacher lift를 쓴 진단은 별도 분모 | 1,980초 = 0.55 h. 전체 L0–L7는 C4에서 확인 |
| C3 | #293 검토 후 새 D1 30정체+60정상, 이어3개 중단 흐름 | 10,800+360=11,160초 = 3.10 h. 사전 등록 값이 확정되면 재산정 |
| C4 | 같은 최종 후보 M1 새6회 + M2 새6회, 각각900초 cap 제안. M1≥5/6 등 기존/새로 고정한 기준과 거짓 성공0를 적용; 실패/미도달 제외 금지 | 10,800초 = 3 h. 후속 정책을 바꾸면 영향 범위 재검증 |
| C5a | 작은 혼합 임무, 동일seed×4조건, no-LLM fixture로 초기화부터 목적지까지. 중간 재배치 없이 모든단계·평가·로그 연결 | 4×1800=7,200초 = 2 h |
| C5b | C5a와 같은 고정 구성으로 실제 다회 LLM×4조건. 첫 작은 E2E 한국어 파일럿. no_comm은 메시지0, 열린 자연어 채널은 실제 왕복, structured는 schema, 모두 실제 job 수행 | 4×1800=7,200초 = 2 h. 호출 최대360회(90×4); 토큰 상한은 코디네이터 확정 |
| C6 | 정식 s1–s6 각1개 새 smoke block×4조건=24회. leader seed%3를 균형 배정하고 s2/s3/s5 사건 실제 발생·관측 도달을 검사. 이슈 #224의24회 요구를 새 manifest로 구체화한 제안 | 24×1800=43,200초 = 12 h; C5와 다른 시나리오이면 합산 대체 금지 |
| C7 | 최소 검토용: 정상+복구2시나리오×3seed×4조건=24회 제안(leader3종). #254의 정식 외부 파일럿을 택하면6×3×4=72회로 수행 | 각각12 h / 36 h. 24회로72회 통계 설계를 완료했다고 하지 않음 |

**C1–C5b의 계획 상한 합계는39,450초(10.96 SIM-h)**다. staging audit S15가 필요하면60초 추가다. 이는 알려진 지원 범위가 통과한다는 가정의 **1차 연결 시험 예산**이며, 실패 원인 수정·재실행, v3 새 보정/인식 학습, C6에 필요한 화물/파트너/경로 확장 비용은 포함하지 않았다. 따라서 마일스톤 완료까지의 총시간 추정이 아니다. C6과 C7(72회)을 더하면 추가48 SIM-h지만 P09의 미지원 능력 개발 비용은 여전히 미산정이다. wall 환산은 새 환경 처리량을 재지 않아 하지 않는다.

**최소화하는 방법:** 같은 실행에서 도달한 S02→S08 증거는 해당 관문에 공동으로 연결하되, 한 회를 독립 표본 여러 개로 세지 않는다. 문 앞에서 실패했다면 목적지 시험을 완료로 적지 않는다. 새 map/모델/가드/분할이 바뀌면 과거 통과를 승계하지 않는다. 정체 detector 없이 성공 사례만 얻어 “stall handling 완료”라고 쓰지 않는다. 실측이 계획 cap에 못 들어오면 horizon을 몰래 늘리지 말고 실패를 보존한 뒤 새 계획으로 정한다.

### 4.3 코디네이터 실행 전·후 체크

1. main/열린 PR의 최신 변화와 실행 중 소스 고정 작업을 확인한다. #292 등록/분류/인수 및 #293 D1을 독립 검토하고, 최종 로봇/렌더/모델/보정·기억·초음파 선택을 명시한다. `FILL_AT_FREEZE`, null 승인·해시를 채우기 전 실행하지 않는다([버전 규칙](../../docs/execution_versioning.md), [#254 §11](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md)).
2. 새로운 ID는 main+열린 PR 최댓값 뒤에서 정한다. 이 문서는 ID를 예약하지 않았다. 자기 worktree에서 표준 `sim_cli` workflow로 실행하고 원본은 기본 `outputs/` 절대 경로에 쓴다. `agent_lock`/세션 소유와 10 GiB 여유를 확인하고 부하를 기록한다. 다른 작업을 중단하지 않는다([AGENTS](../../AGENTS.md), [운영](../../CONTRIBUTING.md)).
3. 모델/비용의 현재 승인 근거를 확인한 뒤 새 원장을 생성한다. 문서에 적힌 과거 프록시 PID/실효 모델/잔액을 현재값으로 쓰지 않는다. 실패·미도달·HOST_ERROR·미상 사용량은 분모와 비용에 남긴다. 실제 송신 없는 fake 시험은 provider 검증으로 세지 않는다([실패 규칙](../../docs/zone_study_llm_failure_rules.md)).
4. 완료 후 원본 해시·manifest·각 명령/프레임·요청/응답·ledger·referee를 대조한다. 현재 소스가 cohort 시작 SHA와 같은지 확인한다. TensorBoard 새 snapshot에 성공/실패를 함께 변환하고 실제 event 로딩, 공용 logdir, 영상 등록, pin/HParams 화면을 확인한다. 선택 가중치는 [Release 배포 규칙](../../docs/model_artifacts.md)에 따라 다운로드·해시·로딩까지 검증한다(모델 로딩/추론은 이 문서 작성 작업에서는 수행하지 않음).

## 5. 물리 없이 Codex에 줄 작업 프롬프트

모두 독립 작업에 복사할 수 있도록 지침·대상·완료 기준을 넣었다. 한 파일이 다른 프롬프트에 등장하면 동시에 쓰지 말고 소유자를 나눈다. 특히 #285/#292/#293을 새로 구현하는 프롬프트가 아니다. 최신 head를 읽고 이미 해결된 부분은 회귀/통합에만 쓴다.

| 프롬프트 | 산출물 | 선행·병렬 범위 |
|---|---|---|
| [P01 최종 환경 등록](task_prompts/P01_final_environment.md) | 3지도·scene/provider resolver 계약과 실패 검사 | 즉시; P03과 registry 소유 조율 |
| [P02 혼합 주문 연결](task_prompts/P02_mixed_jobs.md) | cyan+봉 dev 혼합 주문/개체 ID/host setup 계약 | 즉시; P01과 별도 파일 |
| [P03 무표식 제공자 생명주기](task_prompts/P03_tagfree_provider.md) | prior/fix/명령 이력 연속성·모델 자산 명세 | 즉시; 실제 추론 없음 |
| [P04 단계 연결·teacher 경계](task_prompts/P04_chain_contract.md) | 한 실행의 상태·시간·실패 전파 계약 검사 | P02/P03 합성 전에도 fake로 시작 가능 |
| [P05 네 조건·한국어 원장 연결](task_prompts/P05_dialogue_ledger.md) | 다회 fake-wire 통합/고장·정보 누출 변이 검사 | 즉시, S10/S12 |
| [P06 평가·증거 연결](task_prompts/P06_evidence_referee.md) | synthetic 평가/기록/변환 완전성 검사 | 즉시; 물리 결과 없음 |
| [P07 미봉인 실행 계획](task_prompts/P07_run_manifest.md) | dry-run-only manifest/지원·승인 누락 거부 | P01–P06의 인터페이스와 병렬 초안 |
| [P08 D1 정체 어댑터 계약](task_prompts/P08_stall_contract.md) | #293 검토·관찰 전용 경보 계약/중단 fake 검사 | 기존 D1 작업과 중복 금지; 검증 뒤에만 제어 연결 |
| [P09 전체6시나리오 지원 차이](task_prompts/P09_scenario_capabilities.md) | 물건·역할·경로·사건별 구현/물리 작업 목록 | 즉시; C6/C7의 차단을 명확히 함 |

## 참고 자료와 판정 원칙

위 각 단계의 파일/PR 링크가 해당 주장과 측정의 직접 출처다. 이 문서의 “빠진 연결”, 최소 시험 및 SIM cap은 그 코드/기록에 근거한 **새 제안**이며 과거 실측으로 표시하지 않았다. 독립 test·개발 격자·teacher staging·오프라인 반사실·실제 모델 첫 호출·단위 검사·전체 E2E를 합산하지 않는다.

- 로드맵: [#216](https://github.com/kcm0127-dotcom/ugrp/issues/216), [#217](https://github.com/kcm0127-dotcom/ugrp/issues/217), [#218](https://github.com/kcm0127-dotcom/ugrp/issues/218), [#219](https://github.com/kcm0127-dotcom/ugrp/issues/219), [#220](https://github.com/kcm0127-dotcom/ugrp/issues/220), [#221](https://github.com/kcm0127-dotcom/ugrp/issues/221), [#222](https://github.com/kcm0127-dotcom/ugrp/issues/222), [#223](https://github.com/kcm0127-dotcom/ugrp/issues/223), [#224](https://github.com/kcm0127-dotcom/ugrp/issues/224), [#225](https://github.com/kcm0127-dotcom/ugrp/issues/225), [#226](https://github.com/kcm0127-dotcom/ugrp/issues/226).
- 관리/평가: [연구 TODO](../../docs/research_todo.md), [9/30 현황](../../docs/current_status.md), [본연구 사전 등록 초안](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md), [시뮬레이션 관리](../../docs/simulation_management.md), [TensorBoard](../../docs/tensorboard.md), [모델 보존](../../docs/model_artifacts.md).
- 검증 범위: [이번 문서 검사 기록](VERIFICATION.md). 새 물리/학습/평가 코호트가 없어 TensorBoard 재변환·서버 기동은 하지 않았다. UGRP 예외에 따라 Drive 작업은 없다. 기존 원본·snapshot·사전 등록은 보존했다.
