# pairact-r1 hybrid 전환 규칙과 hybrid 인터페이스 (사전 등록 초안)

상태: READY_FOR_REVIEW. P5 보류 평가를 하기 전에 커밋합니다. 결과를 본 뒤에는 규칙을 바꾸지 않습니다.
규칙 ID: `pairact_r1_hybrid_switch_v1`. 계산 코드는 `harness/pairact_r1_plan.py`의 `hybrid_decision(p5_counts(...))`, CLI는 `scripts/pairact_r1_p5_decide.py`입니다.

## 1. hybrid가 무엇인가
학생 ACT가 *접근 → 정렬 → READY → 파지 → 3초 공동 유지*를 맡고, 마지막 *하강·열기·후진*도 맡습니다. 그 사이의 *문 통과 운반 구간*(유지 후 출발부터 zone B 정렬까지)만 코드가 맡습니다. 이 코드는 *자기 센서 협조 주행*입니다. 입력은 자기 카메라, 자기 발행 명령, 자기 odometry/VO, 그리고 상대가 보낸 메시지뿐입니다. GT, teacher, 상대 자세 원본은 쓰지 않습니다.
- 보고 표기는 "혼합(운반 구간 코드)"입니다. 순수 학생 결과(n/N_eff)와 합산하거나 바꿔 쓰지 않습니다.

## 2. 판정 (P5 최종 count에서 한 번만, 아래 순서대로)
기호는 같은 보류 seed N_eff개 기준입니다(규칙 A 정적 제외 후). H = 학생 `hold_3s` 도달 수, D = 학생 `door` 도달 수, P = 학생 성공 수(`place`, 보정 0 확인된 것만), TD = 같은 seed teacher `door` 도달 수, k = max(3, ⌈0.15·N_eff⌉)(N_eff=20이면 3)입니다.

| 순서 | 판정 | 조건 | 다음 할 일 |
|---|---|---|---|
| 0 | `INVALID_STUDENT_CORRECTED` | 학생 행 중 하나라도 `student_gt_corrections` 또는 `teacher_commands_issued_to_student`가 0이 아님 | 학생 arm을 무효로 하고 원인을 보고합니다. 학생 수치를 주장하지 않습니다 |
| 0 | `UNVERIFIED_CORRECTIONS` / `UNVERIFIED_FUNNEL` | 보정 카운터가 null이거나 hold_3s·door 퍼널이 기록되지 않음 | 기록기를 고친 뒤 rows만 다시 만듭니다(재실행 아님). 판정은 보류합니다 |
| 1 | `GRASP_FIRST` | H < k | hybrid로는 해결되지 않습니다(파지 전에서 실패). 2회차는 접근·정렬·READY 구간 보강(DAgger 또는 구간 오버샘플) |
| 2 | `P2_PATH_FIRST` | TD < ⌈N_eff/2⌉ | 운반 경로 자체가 약합니다. teacher·장면(P2)부터 고칩니다 |
| 3 | `HYBRID_CARRY` | D ≤ ⌊H/2⌋ (3초 유지에 도달한 학생의 절반 이상이 문 통과 전에 실패) | §3 인터페이스를 구현해 hybrid arm을 엽니다. 순수 학생 2회차는 병행할 수 있지만 11/5 데모 경로는 hybrid가 우선입니다 |
| 4 | `PLACE_FIRST` | P ≤ ⌊D/2⌋ (운반은 되지만 하강·놓기에서 절반 이상 실패) | 하차 구간 오버샘플, `place_sync` 켜기 후보 |
| 5 | `PURE_CONTINUE` | 그 밖 | 순수 학생 경로를 유지하고 데이터·반복으로 늘립니다 |

- `pure_minimum_met`(P ≥ 1)는 판정과 함께 기록합니다. P ≥ 1이어도 3번 조건이 맞으면 `HYBRID_CARRY`이고, 이때도 순수 학생의 r1 최소 성공은 그대로 보고합니다.
- k와 ½의 근거: N=20에서 3/20(15%)은 "우연히 한두 번"과 구분되는 가장 작은 수입니다(aggressive-replan §5의 "공동 파지 + 3초 유지 ≥1/20 약 35%" 기대치보다 엄격). ½은 "대부분 운반에서 실패"를 수로 바꾼 값입니다. 둘 다 데이터를 보기 전에 정한 값이고 Codex 검토 대상입니다.
- TD 조건을 둔 이유: teacher도 같은 seed에서 문을 못 지나면, 실패 원인이 학생이 아니라 경로·장면일 가능성이 큽니다. 이 경우 코드 운반으로 바꿔도 같은 곳에서 막힙니다.

## 3. hybrid 평가 seed와 금지 사항
- 주 평가: *같은 보류 N_eff seed*(8342000–019, 규칙 A 동일)에서 hybrid n/N_eff를 학생 n/N_eff, teacher n/N_eff 옆에 둡니다. 이 규칙이 P5 전에 커밋되므로 사후 선택이 아닙니다.
- 운반 코드의 개발·튜닝은 pilot(8343000–039)·validation(8341000–019) seed와 학습 seed에서만 합니다. 보류 seed의 영상·로그를 튜닝에 쓰지 않습니다. 코드 SHA는 보류 실행 전에 커밋합니다.
- 확인 seed(보조): 8344000–8344019 [확인 필요: `check_pairact_r1_seeds.py` 겹침 검사, seeds.json 등록 전]. 보류에서 본 실패에 맞춰졌을 가능성을 줄이려고 따로 보고합니다.
- hybrid 사전 등록은 이 문서를 근거로 별도 파일(`PAIRACT_R1_HYBRID_PREREG.json`)로 만듭니다. arm id는 `hybrid`입니다. 에피소드 상한, 성공 정의, 퍼널, 보정 감사는 P5 v2와 같습니다.

## 4. hybrid 구현에 필요한 인터페이스 목록
| # | 인터페이스 | 입력(허용) | 출력 | 현재 상태·재사용 후보 |
|---|---|---|---|---|
| I1 | `HybridSegmentArbiter`(로봇별, 결정 함수) | 학생 단계 head 출력, 학생 done score, 자기 그리퍼 PWM, `PairActBarrier` 상태, 코드 운반 상태 | 구간 `STUDENT_GRASP → CODE_CARRY → STUDENT_PLACE → DONE`, 전환 시각 | 없음(신규). 전환은 GT `hold_ok`가 아니라 *자기 신호*로 판정: 두 로봇 모두 grasp done ≥ 0.65가 3초 유지(자기 시계) 뒤 나오고 barrier GO 상태일 때 |
| I2 | 운반 전환 동기(두 로봇) | 각 로봇의 READY_CARRY 보고(자기 판정), seq, observed_at_s | GO/HOLD/ABORT, epoch | `harness/pair_carry_sync.py` `PairCarrySync`(TTL·epoch·HOLD 무효화) 그대로 사용. task_id `carry`, plan_version 1 |
| I3 | `SelfSensorPairCarry`(코드 운반 컨트롤러) | 자기 RGB, 자기 발행 명령, 자기 자세 추정, 상대 메시지(I4), 작업 토큰(역할·목적지 B) | 로봇별 바퀴 명령, 그리퍼 PWM 유지(들기 자세 고정), `carry_status`(진행·도착·실패 사유) | 없음(신규). 재사용 후보: `harness/e2ewarp_selfnav.py`(자기 중심 기억·랜드마크 주행, 지도 금지), `harness/own_door_navigation.py`(문 위상·정면 접근점, CPU), `harness/e2e_stall_odometry.py`(RGB VO·정지 감지), `harness/owncam_carry_v6e.py`(적재 시 yaw drift 모형). 모두 CPU 시대 코드라 MJWarp 이식 여부 [확인 필요] |
| I4 | 리더–팔로워 메시지 | 리더의 발행 twist, seq, observed_at_s, plan_version | 팔로워의 강체 대형 유지 명령(빔 길이 구속) | 없음(신규). 리더는 역할 토큰(r1 끝)으로 정합니다. 메시지는 L1-lite 전달 계층과 같은 형식으로 둡니다(지연·손실 기록) |
| I5 | 자기 자세 신뢰 게이트 | 자기 자세 추정 공분산, 마지막 관측 시각 | 정지·재관측 요청, `SELF_POSE_UNCERTAIN` | `harness/owncam_pose_source.py` `PoseReport`·`check_limits` 형식 재사용. CPU 운반 0/33의 원인이 이 게이트였으므로(yaw σ 3°에 약 2.8 s) 적재 drift 모형(v6e) 없이 쓰면 같은 실패가 재현됩니다 |
| I6 | 문·zone B 인식 | 자기 RGB | 자기 중심 랜드마크(문 양쪽 기둥, zone B 경계), 거리 | GPU E2E 계약 v1은 정적 지도를 금지합니다. zone B 인식기와 문 인식기는 [확인 필요: 공동 운반에도 계약 v1이 적용되는지 창민 확인] |
| I7 | 학생 shadow 추론 | 학생 입력 그대로 | 실행하지 않는 학생 행동(기록만) | 신규(작음). 코드 운반 중에도 학생 `release` skill stream을 계속 돌려 이력·시계를 유지합니다. 이력에는 *실제로 발행된 코드 명령*이 들어갑니다(자기 발행 명령이므로 계약 위반 아님). 학생 행동은 로그에만 남깁니다 |
| I8 | 반환(STUDENT_PLACE 진입) | I3 `carry_status=arrived`(자기 판정), 두 로봇 I2 GO | 학생 명령 실행 재개 | 신규. 반환 시점의 학생 입력 분포가 teacher 데이터(zone_settle 끝)와 맞는지 *오프라인 검사 G-H*를 validation 데이터에서 먼저 봅니다: zone_settle 마지막 10행에서 단계 head가 `carry` 또는 `place`, done score < 0.65 |
| I9 | runner 플래그 | `--hybrid-carry <config.json>`(기본 off) | 학생 worker + 운반 코드 동시 실행 | root(-r-c5 다음 -r-c6)·adapter 후보 신규. 기존 후보·`--student-eval` 경로는 바이트 동일(회귀 테스트) |
| I10 | 감사 필드 | 런타임 카운터 | `code_segment_s`, `student_commands_executed_ratio`, `gt_inputs_to_code = 0`, `teacher_steps = 0`, 전환 이벤트 | 신규. `pairact_p5_rows.py`에 arm `hybrid` 행 추가, report-auto `pairact-eval`은 arm 목록을 prereg에서 읽으므로 prereg에 `hybrid` arm만 추가하면 됩니다 |
| I11 | 정적 import 감사 | 운반 코드 소스 | 시뮬레이터 truth·evaluator import 0 | `e2ewarp_selfnav.order_sheet` 방식(지도 접근 거부)과 같은 테스트 |

## 5. 위험
1. 운반 코드는 CPU에서도 0/33(`SELF_POSE_UNCERTAIN`)이었습니다. hybrid가 순수 학생보다 쉬운 길이라는 보장은 없습니다. 판정 3이 나와도 I3·I5·I6 구현이 11/5까지 끝나지 않을 수 있습니다.
2. 반환(I8) 시점의 학생 입력이 학습 분포 밖일 수 있습니다. teacher 시연에서는 운반 중 이력이 teacher 명령이고, hybrid에서는 코드 명령입니다. G-H 오프라인 검사가 실패하면 반환 지점을 앞당기는 안(zone B 앞 정렬까지 코드)을 후보로 둡니다.
3. 정적 지도 금지가 공동 운반에도 적용되면 I6이 가장 큰 구현 비용입니다.
