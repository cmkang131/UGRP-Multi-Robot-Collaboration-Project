# T05 — tile west 낮은 파지 후보

**구현·오프라인 검사 전용. 물리/렌더/모델 호출 0. Draft PR, 병합하지 않는다.**
T10b 복도 제어는 이 작업 범위가 아니다. 기존 등록 실행기에서 tile 배송이
지원된다는 선언도 아니다. 물리 실행 조건은 [PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)를 따른다.

## 기준과 소유 범위

- 작업 시작 main/HEAD: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`.
- 제출 전 base: `26545c2499f94c3f99a5d650f7cc8ea992f24196`로 fast-forward.
  #307·#332의 main 변경을 받아 CI 파일 차이를 없앴다. 새 후보의 146개 정적
  Python 의존성 및 기존 관련 테스트는 이 base 갱신에서 바뀌지 않았다.
- P09 #302 병합 SHA: `09081b3c46f0d51e02ef625e4be8c7d6f6e67963`.
  요구/정적 감사와 작업 분할이 선행이다. 정적 경로 PASS를 학생 성공으로 승계하지 않는다.
- #328 병합 SHA: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`.
  로컬 offline pytest는 호스트 잠금 없이 실행한다. Claude의 물리 잠금은 건드리지 않는다.
- CI 소유 #300 병합 SHA: `e6cc2a8850f35dd8e29cb20a7615c7e0901f795f`.
  workflow/CI 설정을 수정하지 않는다. 새 검사는 기존
  `tests/test_zone_own_executor*.py` glob에 들어간다.
- T03 #325는 열린 red/green 상자 후보다. 이 작업은 새 tile 모듈만 추가하여
  상자 구현·봉인 소스·공용 registry·원본 시나리오·지도를 수정하지 않는다.
- 새 bundle/workflow ID 없음. 선행 draft의 물리 결과를 이 후보의 근거로 합산하지 않는다.

## 구현 계약

`harness/tile_own_skill.py::TileWestSkill`은 opt-in 하위 조작 제어기다.
`harness/tile_own_vision.py`가 자기 JPEG와 자기 발행 PWM으로 가까운 tile 및
holding을 추정한다. robot_cam의 로봇 ID·frame ID·유한 시각·freshness·JPEG hash를
검사하고 **그 JPEG를 직접 decode**한다. 별도 RGB 배열, 측정 관절, GT 좌표,
partner state, setup inventory, 심판 receipt를 입력받지 않는다. 영상 봉투의 추가
private 필드와 `actuator_state`는 읽지 않는다. 자세는 `on_command` 이력으로만 갱신한다.

지원 공개 주문은 `kind=tile`, `count=1`, `required_robots=1`,
`identity=kind_fungible`, `item_ids=[]`, 목적지 B 또는 C, 역할 west다.
공개 `zone_study_inputs.FORMATIONS['tile'] == ('west',)`를 그대로 따른다.
catalogue의 `(('west',), ('east',))` 중 **east는 이 후보에서 거절**한다.
specific identity·다중 count·목적지 A·can/상자·T10b는 지원 밖이다.

흐름: 서로 다른 두 영상의 안정된 낮은 tile 후보 → 열기 → 7 mm 낮추기 →
닫기 → 70 mm 들기 → 두 새 영상의 holding → 운반 허용 → 자기 정책의 방출
요청 → 7 mm 낮추기 → 열기 → 초기 관측 자세 복귀 → 두 새 영상의 grip 부재와
근처 바닥 tile → 하위 조작 완료. 명령을 반환한 것만으로 다음 단계로 가지 않는다.
해당 PWM이 자기 발행 이력에 들어오고, 0.5초 뒤의 새 영상이 있어야 한다.
단계별 12 SIM초, 전체 900 SIM초이며 미관측/unknown/미발행은 멈춤 또는 실패다.

`carry_permitted(now)`가 false면 호출자가 주행을 멈춰야 한다. 운반 중 unknown은
즉시 주행 허용을 내리고 12초 안에 회복하지 못하면 실패한다. `request_release`
인자는 자기 고수준 정책의 의도이지 host의 도착 정답이 아니다. `done` /
`skill_complete` / `own_rgb_released`는 **하위 조작 판단뿐**이다. 목적지 포함·착지·
접촉·배송 완료는 기존 평가 심판이 별도 판정한다. 모듈에는 배송 성공 반환값이 없다.

네 통신 조건은 같은 생성자·제어·인식·센서·자기 기억·상태 enum을 쓴다.
condition 이름은 allowlist 검증에만 쓰며 통신으로 holding/완료를 덮는 경로는 없다.
호출자는 `manifest()`의 controller/config와 `role_assignment()`를 별도 해시로
기록해야 한다. actor 선택은 공개 요청이며 host private state로 고르지 않는다.

## 낮은 팔 자세와 남은 물리 문제

정적 cargo 사양: .060×.040×.012 m, .025 kg, grasp z=.007 m.
명령 목표 높이는 .006–.008 m로 제한하고 기본은 .007 m다. 상자 높이 .024 m를
넣으면 clamp하지 않고 거절한다. 최종 v3 physical-pad FK/IK를 사용한다.

v3의 기존 **상자용 arm-axis 보정 범위**에서는 7 mm 해를 찾지 못했다.
그래서 이 후보는 별도 이름의 좁은 개발 범위(자기 base 기준 x=.176–.180 m,
|y|≤.005 m, preferred pitch −40°)만 허용한다. 그 안에서 PWM 500–2500과
command-FK 잔차(높이 1 mm, XY 2 mm)를 검사한다. 이 계산은 실제 관절·접촉의
안전 보정이 아니다. .155 m catalogue station에서 가능한 저위 자세는 예상 tile이
영상의 95%를 넘게 덮어 holding 판단을 거절한다. 로봇 외관·카메라·FOV는 바꾸지 않는다.

가까운 관측의 synthetic 예제 초기 PWM은 `{1:2000,3:510,4:2234,5:1753,6:1500}`다.
이것은 **발행 명령 fixture**이며 실측 자세·물리 성공 기록이 아니다. 실제 접근은
자기 RGB navigation이 이 범위와 west 정렬을 만들어야 한다. 범위 밖에서 강제로
닫거나 GT station으로 옮기는 fallback은 없다.

인식은 magenta+저위 평면 footprint 가설, 크기/방향/다중 후보 거절,
v3 physical-pad 기준의 grip 예상 영역, 영상 정보량·경계 검사를 연결한다.
동일 투영의 magenta 바닥 패턴과 실물 tile은 단일 영상만으로 구별되지 않을 수
있다. 따라서 바닥 후보만으로 holding을 주장하지 않는다. 합성 성공은 정확도나
실제 최종 환경에서의 가시성 증거가 아니다. 마찰·접촉·25 g 하중·최종 영상
보정은 미측정이다.

## 검증 기록

2026-10-01 Batch H의 H334-1/H334-2 수정과 dev2 검사 결과는
[REVIEW_FIXES.md](REVIEW_FIXES.md)에 별도로 남긴다. 아래의 최초 검증 기록은 보존한다.

[VERIFICATION.md](VERIFICATION.md)에 실제 pytest, mutation 결과와 원본 해시를 적는다.
로컬 테스트에는 공용 잠금·물리·렌더·모델 호출이 없다. 정상 GitHub CI는 별도로
확인하며 skip/cancel하지 않는다. 구현 PR은 draft로 유지한다.

이 기록은 코드 회귀검사로, 학생 trial이나 인식 데이터셋 채점이 아니다. 로봇
성공률/TensorBoard 실험 스냅샷을 만들지 않는다. 실제 두 셀의 결과가 생기면
성공/실패 모두 primary `outputs/tensorboard` 새 snapshot과 영상·원본 해시를
확인하는 작업은 조정자가 수행한다. Drive는 사용하지 않는다.

## 참고 자료

- [P09 요구](../2026-09-30-scenario-capabilities/REQUIREMENTS.md), [T05 prompt](../2026-09-30-scenario-capabilities/TASKS.md)
- `sim/zone_cargo.py` tile 사양, `harness/zone_study_inputs.py` 공개 west 계약
- `harness/visual_arm_v3.py` 명령 FK/IK, `harness/zone_own_perception_v3_1.py` 영상 정보량 검사
- `harness/zone_study_referee.py`, [TensorBoard](../../docs/tensorboard.md)
- 새 외부 논문·OSS·의존성·모델 없음. 기존 Python/NumPy/OpenCV 재사용.
