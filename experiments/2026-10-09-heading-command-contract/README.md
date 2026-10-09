# 공통 heading REAL 명령 계약 (2026-10-09)

사용자 s3fix3 지시로 main 대상의 작은 수정으로 분리한다. S3 물리0, 새 번들0. v145 factory와 own-map adapter가 이미 공유하는 `zone_solo_cyan_path_heading` 한 곳을 수정한다. heading off는 명령·record·RNG의 이전 바이트를 보존한다.

원인: 공통 selector의 최종 정렬은 측정된 `.35/.06s` lateral을 허용하지만 자기 지도 REAL port는 최소 `.10s`를 요구했다. seed55002의218.9초 발행 전 제안은 이 불일치로 HOST_ERROR가 났다. S3 v147의23.2/23.3초는 별도 pair 접근기의 혼합 축 제안이 측정된 단일 축 계약을 위반한 같은 종류의 제어기/출력 경계 오류다.

결정: 짧은 펄스를 임의로 늘리거나 측정 응답을 합성하지 않는다. 공통 후보 선택에서 `.10–.80s` 단일 축만 허용하고, 최종 발행 경계에서도 짧은/혼합 축 제안은 사유와 원문을 기록하고 hold로 생략한다. 다른 유효 프로필이 없는 미세 정렬은 해상도 제한으로 남는다. 유효 lateral이 없고 위치 오차가 기존3cm 도착 반경 밖이면 동일한 회전→전진으로 최종 위치에 접근한 다음 목표 yaw를 맞춘다. 최종 yaw와 경로 yaw를 매 틱 번갈아 선택하는 회귀를 막는다. 위치/σ/성공 문턱·보정값은 바꾸지 않는다.

공동 빔 운반 예외는 S3 PR #416에서 별도 명시한다. 이 공통 수정은 두 로봇이 함께 잡은 빔의 기존 연속 옆걸음 제어기를 바꾸지 않는다.

검증: `tests/fixtures/path_heading/command-contract.json`은55002 자기 포즈/경로/명령과 S3 저장 명령2개의 원본 경로·SHA를 보존한다. GT·평가 입력0. 기존 REAL port가 원본3개를 거부하는 것을 재현하고 공통 selector 출력3개는 실제 port.apply의 명령 경로를 통과한다(모터 쓰기 stub, 새 물리0). 발행 경계의 생략/이유 기록, off 객체 동일성, 기존 공통 factory/off record/RNG 및 모델 내 북향 경로 완주를 관련2파일로 검사한다. 실제 이동 성공이나 wall/SIM 개선의 증거는 아니다.

표준 근거: [Nav2 RPP](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md)의 경로 추종/진행 방향 정렬과 도착 시 orientation을 구분하는 구조를 유지한다. REAL의 `.10s` 및 단일 축 제약은 이 프로젝트 `sim/s2_real_output.py`의 계약이며 Nav2의 수치로 주장하지 않는다. 변경이 필요한 이유와 불허 펄스 생략은 사용자 결정에 따른 출력 경계 수정이다.

로컬 검증 결과: 관련2파일의 고유 시험30개 통과(29개 통과 후 새 fixture의 읽기 전용 `terminal` 속성 대입 오류를 제거하고 해당1개 재검증). 프로그램 실패를 숨긴 skip/xfail0, 새 물리0, CI 대기0. 기존 북향 경로 모델 재생은 unloaded/loaded 모두 완료하고, heading off 초기 record SHA·명령·RNG 동일성을 유지했다.

## s3fix4 단계 probe 후속

S3 RGB 집기 정렬은 기존3mm 허용치를 쓰는데 공통 회전/전진 fallback은 경로용3cm 반경에서 방향 정렬로 돌아가, 옆방향1cm/2cm 입력에서 명령0으로 멈췄다. `select(..., position_tolerance_m=.03)`로 호출자의 기존 허용치를 받는다. 기본3cm 호출은 그대로이며 S3가 자체3mm 조건을 명시한다. 성공/위치 수렴 문턱이나 calibration을 바꾸지 않는다. 회귀 두 입력 모두 turn .35/0.10초로 진행하며 물리0. 최소 보정 펄스보다 작은 오차의 양자화 한계와 실제 파지 성공은 별도 인수 대상이다.

단독 cyan의 실제 `step()`도 최종0.10m 안에서는 불법0.06초 제안을 단순 생략하던 경로가 있어 같은 공통 selector로 대체한다. 기존 RGB 검출·view 전환·도착 판정·full pulse/coast/지연 관측 대기를 유지한다. 큰 오차와1cm·2cm의 실제 step 회귀를 함께 검사한다. 유효한 기존 명령과 heading off 경로는 그대로다.
