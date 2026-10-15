# 비물리 검증

`PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_reloc18_innovation.py tests/test_selfmap6.py tests/test_reloc17_servo_wait.py`

27 passed (1.79초). 물리·렌더·모델·GUI 실행 없음.
작은 P에서 시각 영향 감소, yaw wrap·교차 공분산, Joseph PSD,
관문 거부·특이 행렬의 무변경, 실제 empty/nonempty static handoff 이전의 가중 융합,
관측 상관 솎기·원본 R 바닥·기본 off·명시적 실행 번들 전달을 확인했다.
폐루프 성능과 place 성공은 별도 실행 결과로만 판정한다.

운반 경로 연결 후 `reloc18 + reloc14 + reloc13`: **35 passed**, 그리고 실제 mapper receive
경계 검사를 추가한 `reloc18 + selfmap6 + reloc14`: **43 passed** (10.40초).
운반 PF의 1.24m/77도 반례 거부, 작은 P의 yaw 영향, 순수 명령 대조의 fix-age·거리/회전
예산 복원과 전체 자기 RGB/명령 입력 경계를 확인했다. 추가 검사도 전부 비물리다.

R3 준비: 같은3파일 **46 passed** (1.63초). map→odom 계산, 같은 RGB를 한 번만 소비하는
실제 mapper handoff, 로컬 명령 odometry 불변, DEV 예산 기록과 시각/finite 검사 보존을 추가 확인했다.
