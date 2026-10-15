# 비물리 검증

명령: `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_reloc17_servo_wait.py tests/test_camera_robot_port.py`

결과: **12 passed, 27 subtests passed in 0.87s** (도구 stdout 확인).
실행 소스의 제어기/테스트 파일은 `47670d1428abfbb09756627c1a2be31caf650465`와 동일하다.
MuJoCo/물리·렌더·GUI를 실행하지 않은 fake port 통합 시험이다.

- 0.0005초 tick에서 pan1500→2000 뒤0.2초 정상hold: 기존1899PWM 절단을 재현.
- 후보 정상대기: 바퀴0·카메라2000PWM 완료.
- terminal hold: 기존과 같은1899PWM 절단/취소 유지.
- 기본off bundle byte-equivalent 구조, true일 때만 옵션 표기, 잘못된 bool 거부.
- 기존 CameraRobotPort의 소유 입력/동작·기한 검증 회귀.

실물·ACT 학생·운반·폐루프 성공을 증명하지 않는다. 폐루프 결과는 별도 원본으로 센다.

생성자·command hook의 기존 호출자 호환성을 추가 확인: `python -m pytest -q tests/test_self_map_executor.py` → **16 passed in 2.27s**. 새 코드 변경 없이 이 영향 경로만 검증했다. 합계28 passed·27 subtests, 물리/렌더0.
