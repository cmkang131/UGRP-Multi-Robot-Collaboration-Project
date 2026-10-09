# S2 heading · 비교 DEV (2026-10-09)

사용자: 이동 시 동쪽을 보며 옆으로 가는 주행을 경로 방향으로 회전 후 전진하도록 변경.
`codex/s2-heading`, 기준 `99d81d8c`/v141. 진행 중인 s2-realism은 수정하지 않는다.
3개 기존 seed 1066/1068/1065를 비교하며 졸업·신규 확증 표본으로 세지 않는다.
[사전 기록](registration.json), [번호 조회](reservation.json). 새 v143/7.36.0, DRAFT PR.

## 표준 방법 조사

- Coulter, [Implementation of the Pure Pursuit Path Tracking Algorithm](https://www.ri.cmu.edu/publications/implementation-of-the-pure-pursuit-path-tracking-algorithm/): 경로의 전방 목표를 차체 좌표로 변환하는 고전적 추종법. 원문 상세는 이번 조사에서 미확인.
- Macenski et al., [Regulated Pure Pursuit for Robot Path Tracking (2023)](https://arxiv.org/abs/2305.20026): 곡률·장애물 접근·목표 접근에 따라 속도를 조절하는 Nav2 RPP. 논문 초록 확인.
- [Nav2 공식 RPP README](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md), [공식 현재 C++ 구현](https://api.nav2.org/nav2-rolling/html/regulated__pure__pursuit__controller_8cpp_source.html): `use_rotate_to_heading`, `atan2(carrot.y, carrot.x)`와 제자리 회전, `max_angular_accel` 및 정지 거리로 각속도를 제한한다. 코드 322–369행 확인.

우리 변경은 RPP 전체 이식이 아니라 **경로 접선/전방 목표 방향 정렬 → 전진** 규칙의 펄스 제어 적용이다.
MasterPi의 최소 PWM 때문에 임의 저속·연속 가속 램프를 만들지 않는다. 기존 실측 turn ±.35/.10s와
전체 coast·지연된 최신 PF 관측 대기를 그대로 사용한다. 기존 v141보다 회전 속도·각가속도 펄스를
키우지 않는다. 운반도 별도 하중 펄스의 같은 상한을 사용한다. 이것은 물리 각가속도의 새 실측 보증이 아니다.
능동 관측은 기존 RGB 측정 ±90° guard/횟수/시간 예산을 그대로 유지한다. 주행 방향 회전과 능동 관측을
별도로 기록하며, 능동 관측 guard를 주행 yaw 기준으로 초기화하거나 우회하지 않는다.

## 구현·검증 범위

`heading_mode=path_tangent_v1`, 기본 off. off는 v141 factory와 bundle을 그대로 반환한다.
on은 cooperative MRO에서 펄스 주행만 교체하므로 위치추정·미끄럼 회복·능동 관측·카메라 자세를 보존한다.
먼 이동은 제자리 turn 후 양의 forward만 선택하며 중간 waypoint 근처라고 옆걸음을 허용하지 않는다.
최종 작업 목표 0.10m 안에서만 기존 동쪽 작업 방향을 맞추고 .35/.06s 미세 옆걸음을 허용한다.
판정·GT 좌표는 제어기에 전달하지 않는다.

저장 기록 재생은 같은 기록 입력에서의 제안 명령 비교와 보정 모델상의 경로 재생이다. 새로운 RGB,
접촉, 미끄럼, 완주 결과를 재현했다는 뜻이 아니다. 실제 비교 DEV는 대기열 뒤에서 한 번에 하나씩 수행한다.
원본·영상은 primary outputs에 보존하며 로컬 보관을 원격 백업으로 표현하지 않는다.

## 남은 검증

로컬 시험, 저장 기록 재생, push 후 세 DEV, 평가·4배속 영상·TensorBoard를 진행한다.
S3 채택 권고는 세 비교 결과가 나온 뒤 감독에게 제시하며 현재 채택 판정은 보류한다.

## 오프라인 결과 (실행 전)

바뀐 시험 파일 **17 PASS**(30.94s), 앞선 dependency 두 파일13개 PASS. 최초 방향 부호 시험2건은
±π 근처에서 짧은 펄스의 오버슈트를 최소화하다 반대 방향을 골라 실패했고, wrap한 오차의 부호를
우선하는 Nav2 규칙으로 수정 후 통과했다. [검증](verification.json).
기본 off의 실제 v141 factory record/RNG/bundle 바이트 동일, 주행 경로·명령·이벤트 동일을 확인했다.
기존 v141 관련 소스는 수정하지 않았다. 표준 workflow plan도 실행 없이 통과했다.

[기록 재생 요약](offline-summary.json): 저장된 **1,757/1,757 제안 명령 off 바이트 동일**.
같은 기록 입력에 새 selector를 적용한 옆걸음/이동 명령시간 비율은 아래와 같다.

|seed|v141 제안|새 제안|기존 전체 발행 명령|보정 평균 모델 경로 도착 off/on|
|---:|---:|---:|---:|---:|
|1066|46.879%|3.654%|43.842%|4/4 · 4/4|
|1068|40.529%|2.146%|37.441%|6/6 · 6/6|
|1065|10.347%|0.547%|10.347%|74/74 · 74/74|

분모는 명령 비영(非零) 시간이며, 실제 발행 통계는 hold/다음 base 명령/expiry의 이른 종료를 반영한다.
제안 통계는 각 후보 pulse duration의 합이다. **새 방식이 바꾼 이후 영상은 없으므로 이 비율은
실제 새 실행 비율이 아니다.** 84개 저장 A* 계획의 보정 모델 재생은 평균 응답 가정의 도착일 뿐,
실제 문 통과·미끄럼·성공의 근거가 아니다. v141 DEV direct fallback은 경로 이벤트가 없어 waypoint를
목표로 표시했다. 원본 SHA와 실패한 replay v1/v2도 보존했다.

추가 발견: 기존 집기 정렬 옆걸음은 목표 오차 최대0.849m(s1066)/0.920m(s1068)였다.
새 옵션은 시각 정렬의 먼 이동 제안도 회전/전진 펄스로 바꾸고 coast+최신 추정을 기다린다.
미끄럼 BackUp은 목표10cm 밖에서 기존 전후 펄스만 후보로 유지한다.

기준 s1068은 v141의 동시 쌍 실행이었다. 새 세 실행은 직렬이므로 wall/SIM 차이는
방향 제어 효과와 호스트 동시 부하를 분리해서 해석해야 한다.
