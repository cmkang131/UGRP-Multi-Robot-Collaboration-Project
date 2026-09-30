# T08b 남북 빔 접근·정렬 후보

실제 출발 상태에서 자기 RGB 위치 추정을 따라 T08a 사전 정류장으로 접근하고, 같은
posterior·발행 servo·명령 이력을 유지하며 상대 정렬로 넘어가는 **제어/결정 로직**이다.
물리·렌더·모델 실행은 0회. 실행 가능한 최종 환경 어댑터와 물리 인수는 아직 없다.
`physical_ready=false`, 배송 성공은 null이며 close/lift/carry/pivot을 포함하지 않는다.

2026-10-01 독립 검토 H333-1의 native PWM/활성 채널 수정과 새 검증은
[REVIEW_FIXES.md](REVIEW_FIXES.md)에 별도로 기록한다. 아래 최초 검증 기록은 보존한다.

## 구현 범위

- `harness/beam_approach.py::BeamApproach`: 명시적 공개 역할 배정, T08a의 지도/sheet/주문
  검증과 남쪽 +π/2·북쪽 −π/2 heading, .25 m prestation을 사용한다. 위치는 매번 같은
  provider의 자기 RGB posterior에서 얻는다. 경로는 정적 지도 A*와 연속 구간의 보수적
  swept AABB 검사를 거친다. beam·반대 역할의 **공개 정적 영역**을 회피하고, 현재 파트너
  위치는 입력으로 받지 않는다. 회전/서보/병진은 별도 필수 full-v3 command guard를 거친다.
- `OwnApproachMemory`는 이미 발행한 초기 PWM/history를 보존한다. 제안만 한 명령은
  기록하거나 provider에 반영하지 않고 실제 발행 ACK에서 한 번만 반영한다. provider가
  발행 후 오류를 내도 실제 명령은 이력에 남긴다. 중간에 PF/servo/history를 새로 만들지 않는다.
- 두 새 프레임에서 prestation 위치·heading을 확인한 뒤 `alignment_entry`에 posterior,
  servo, frame ID, history prefix hash를 기록한다. `handoff()`는 복사본/준비 자세가 아닌
  **같은 memory 객체**를 반환한다. 새 상대 정렬은 자기 JPEG를 받은 observer의 v3 chassis
  좌표만 사용하고 `.2032 m` 목표로 제한된 속도 명령을 낸다. 두 프레임의 정렬 주장은
  `relative_aligned`이며 STATUS ready/done·배송 성공을 발행하지 않는다.
- 영상 hash/카메라/robot/frame/time/디코딩, stale/불확실한 위치, 상대 관측 실패·잘못된 끝,
  guard/provider 오류, 미발행 ACK, 배달된 abort·끊긴 heartbeat·900초 경계는 hold/명시적
  실패로 처리한다. 실패는 sticky이며 재초기화·GT 보정·자동 재시도를 제공하지 않는다.
- 4조건은 동일한 코드/config/센서/기억/enum 채널을 사용한다. condition은 감사 필드뿐이다.
  역할 배정 hash와 controller 소스 hash, 검색 팔 자세 hash를 따로 기록한다.
  수신 API에는 기존 enum wire record만 들어온다. free text/파트너 pose를 STATUS에 넣을 수 없다.

## 소유와 선행 검증

작업 base main은 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`(#328)였다.
첫 명령으로 fetch 후 #315 branch를 병합했다. #315 head
`86847071f0332c23e5858c93607e2b0bbeb6dc98`는 정적 계약과 독립 carrier 형상 변이 검사 범위이며
작업 시작 시 OPEN/미병합(merge SHA 없음)이다. 실제 최신 상태는 VERIFICATION에 기록한다.

| 작업 | 확인한 SHA/병합 | 소유/검증 경계 |
|---|---|---|
| T08a #315 | `86847071f0332c23e5858c93607e2b0bbeb6dc98`, 미병합 | 공개 sheet·정적 양끝 기하; 실제 접근 성공 아님 |
| #292 | `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`, 미병합 | 등록 후보/후속 정렬·파지·운반; T08b에 자동 설치하지 않음 |
| P03 #312 | `b38c1d5905fdf798dcfd34d215c7e82d0a0cf296`, 미병합 | 위치 제공자 수명/zero-tag 조합; 복제·수정하지 않음 |
| P05 #308 | 병합 `504e4bb25a0988aaf0b8a00828ad68fc73df2670` | 다회 통신/원장; 실제 통신 성공은 이번 증거 아님 |
| P06 #303 | `114349e0adc6d934ceb9a990ee9589aa123b8543`, 미병합 | 평가·raw writer·TensorBoard; 이번 구현은 synthetic unit tests만 |
| P09 #302 | 병합 `09081b3c46f0d51e02ef625e4be8c7d6f6e67963` | 원본 요구 감사/작업 분할; inventory/feasibility는 runtime 입력 아님 |
| offline 잠금 #328 | 병합 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e` | 로컬 fake pytest는 공용 물리 잠금 없이 실행 |

시작 때 #292/#312/#308/#303/#315 PR에 범위/소유/가설을 댓글로 전달했다.
T08b는 새 모듈/테스트/이 폴더만 소유하며 봉인 제어기/provider/STATUS/심판은 수정하지 않는다.
상대방 결과는 이번 테스트/물리 성공 수에 합산하지 않는다.

## 호출 경계

실행기는 최종 v3 RGB observer와 command sweep guard를 **별도로 검증**해 넘겨야 한다.
legacy v2 perception을 v3 보정으로 간주하지 않으며 permissive guard 기본값도 없다.
이 PR은 factory·등록 JSON·workflow·실행 bundle을 교체하지 않는다. 새 runnable ID는 예약하지 않았다.

```python
# 공개 static_map/sheet/order/roles와 기존 own provider/history만 사용한다.
memory = OwnApproachMemory(provider, issued_history)  # 과거 명령은 provider가 이미 소비
controller = BeamApproach(
    static_map, sheet, order, robot_id=own_id, role_assignment=roles,
    task_id=job_id, condition=condition, memory=memory,
    observe_beam=calibrated_v3_own_rgb_observer, command_clear=own_v3_sweep_guard,
    search_servo=predeclared_search_pwm, started_at=scene_reset_time,
)
# 수신 정책이 실제 배달한 fixed-enum record에만 receive_status 호출.
# tick(now, own_observation) -> Decision. action이 비었으면 발행 ACK를 기다림.
# action을 own port가 실제 발행한 뒤 on_command({'t': now, **action}) 한 번 호출.
# 실패 시 hold/abort를 전달. 정렬 진입 후 handoff()의 동일 객체를 후속 후보에 연결.
```

`observe_beam`/`command_clear`는 신뢰된 제어 구성요소이며 이름만으로 입력 출처/물리 보정이
입증되지 않는다. 최종 조합의 source closure·보정 검증·정적/실제 sweep 인수는 코디네이터 몫이다.
본 모듈은 이 미완료 조건을 숨기거나 기존 M2의 성공을 승계하지 않는다.

## 오프라인 검증과 재현

기존 Mac 환경을 쓰고 공용 물리 잠금은 획득하지 않는다. `offline_guard.py`는 MuJoCo/모델
import와 network connect를 차단한다. pytest용 fake/합성 JPEG만 쓰며 실험 성공률을 만들지 않는다.

```sh
PYTHONPATH=.:experiments/2026-09-30-beam-approach \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -p offline_guard \
  tests/test_pair_navigation_beam_approach.py tests/test_pair_navigation_beam_initial_pose_plan.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_pair_owncam_approach.py tests/test_pair_passage_plan.py -q

/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-beam-approach/mutation_check.py /absolute/NEW-output
```

T08a가 추가했던 CI 목록 한 행은 이번 사용자 지시(CI 설정 변경 금지)에 따라 main으로
복원한다. 대신 기존 `test_pair_navigation*.py` 패턴이 bridge module에서 **T08a 전체64개**를
수집한다. T08a의 수집 assertion 경로만 바꿨으며 기하/오류 검사는 그대로다.
T08b도 같은 기존 glob으로 정상 CI에 포함된다. `.github/workflows`와 CI 설정은 main과 같다.
첫 관련 검사에서 발견한 T08a 등록 기대 실패와 bridge 수정 후 결과를 모두 보존한다.

최종 관련 검사 고유 **239개 통과**(재실행 합집합), 소스 고정 두 파일 **56개 통과**다.
최신 main 반영 뒤 **128개 통과**, 봉인 v6e 소스 **85/85 해시 동일**, 제거/경계 변이
**8/8 검출**을 확인했다. 접근 제거25·위치 gate8·상대 정렬17·인계 PF 초기화6·guard10·
영상 hash1·수신 abort1·SIM cap 경계1개의 실패가 났고, 모두 collection/import error는0이다.
최종 수치·source hash·명령·원본 위치는 `VERIFICATION.json`에 기록했다. 변이는 각 별도
프로세스에서만 적용하며 production bytes를 쓰지 않는다. 정상 테스트를 통과한 소스를
변형한 뒤 navigation/pose gate/상대 정렬/PF 인계/command guard/영상 hash/수신 abort를
제거하거나 cap 경계를 느슨하게 바꾸면 실제 테스트 실패가 나오는지 검사한다. 실패 변이를 단순 수집/import error로
세지 않는다. 정상 GitHub CI를 실행하며 취소/skip하지 않는다. draft PR만 만들고 병합하지 않는다.

## 남은 물리 검사

[PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)의 원본3배치×정상/실패×900 = **5,400 SIM초**.
v3 provider/observer/guard 및 표준 관리 adapter 연결, 독립 검토, 실제 spawn→prestation→정렬,
posterior 오차·충돌·안전 실패와 연속 인계, raw·TensorBoard 표시가 남아 있다.
새 물리/학습/평가 결과가 없으므로 공용 TensorBoard snapshot/서버/화면은 생성·변경하지 않았다.
T10b 복도 양보와 운반 pivot은 이 T08b PR에 넣지 않았다.

## 참고 자료

- `experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md`, `TASKS.md` T08a/T08b
- `harness/beam_initial_pose_plan.py`, `harness/map_goto.py`, `harness/static_keepouts.py`
- `harness/owncam_pose_source.py`, `harness/zone_pair_status.py`, `sim/masterpi_robot_models.py`
- `harness/zone_pair_executor.py`, `harness/zone_pair_guards.py`(읽기 전용), #292/P03/P05/P06
- 외부 문헌/새 의존성/새 모델 호출 없음. Python 표준 라이브러리와 기존 NumPy/OpenCV 재사용.
