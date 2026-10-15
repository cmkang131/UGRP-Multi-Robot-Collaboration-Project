# 비물리 검증

`PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_reloc18_innovation.py tests/test_selfmap6.py tests/test_reloc17_servo_wait.py`

27 passed (1.79초). 물리·렌더·모델·GUI 실행 없음.
작은 P에서 시각 영향 감소, yaw wrap·교차 공분산, Joseph PSD,
관문 거부·특이 행렬의 무변경, 실제 empty/nonempty static handoff 이전의 가중 융합,
관측 상관 솎기·원본 R 바닥·기본 off·명시적 실행 번들 전달을 확인했다.
폐루프 성능과 place 성공은 별도 실행 결과로만 판정한다.
