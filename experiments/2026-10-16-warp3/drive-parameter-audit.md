# 구동 명령 변환의 공통 파라미터 확인 (정적)

frozen teacher `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`의 `sim/masterpi_drive_friction_v7.py`, v2, v1과 실행 어댑터를 읽었다. v7 `build_world`는 명시적 params가 없으면 `DriveParameters()`를 만들고 이 실행 어댑터는 params를 덮어쓰지 않는다. start_fraction(.325), kinetic_fraction(.1/1.2), torque_cap_nm(1.2*9.80665/100)은 dataclass 기본값/고정 계산이며 seed 입력을 쓰지 않는다. 따라서 이 실행 프로필에서 배치 decoder가 공통 파라미터를 쓰는 근거가 있다. relay 상태/발행 명령/PWM 보간은 world별이다.

이것은 구동 파라미터 전달에 관한 정적 확인이다. 모터 실기 사양을 새로 확인한 것이 아니고 기존 `installed_motor_and_floor_verified=false`와 아날로그 모터 한계를 유지한다. 다른 로봇 보정/임의 params를 지원한다고 확장하지 않으며 교사 성공은 별도 GPU 관문으로 판정한다.
