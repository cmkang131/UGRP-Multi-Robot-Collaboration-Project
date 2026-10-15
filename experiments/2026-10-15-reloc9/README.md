# reloc9 selfmap — 기본 off 보정·벽 윗선 토글

기준 PR506 `66928f23c45f7b430b4467dd07d55e0916d271f1`. carry PR505의 reloc9와 한 묶음이지만 브랜치는 따로 커밋한다. 새 물리·렌더·모델 호출·원격 접속은 0이고 **ready=false**다. GCP에서 진행 중이던93571의 완료 여부나 결과를 추정하지 않았으며 **selfmap 큐는 만들지 않았다**. 조정자가 그 결과를 본 뒤 결정한다.

- `reloc9_rotation_calibration_v1=False`: 기본은 이전 펄스 모형 그대로다. true는 기존 `harness/self_pulse_rotation.py` / `s2_pulse_v122_rotL_v1`을 명시적으로 재사용한다. 이미 보정된 selfmap에 carry 정상상태 모형의0.575배를 다시 곱하지 않는다. `Options.motion_model`도 같은 값으로 정해 계획·적분 간 불일치를 막았다.
- `reloc9_wall_height_guard_v1=False`: true는 고정 높이0.40m의 측정 윗선이 없는 벽 열을 버린다. 명령 FK 예상 위치와4px+밴드 높이의10%(최대12px) 이내이고 영상 밝기/색차 step≥4여야 한다. 영상 밖 윗선은 허용하지 않는다. 선분 맞춤·바닥 지우기·문 검출 벽열 어댑터 전에 필터링하며, 판정 원장을 trace에 남긴다. 기본 off에서는 기존 scan·계산·행동이 유지된다.
- `harness/reloc9_rotation.py`, `harness/reloc9_wall_guard.py`, `scripts/reloc9_metrics.py`, 공유 시험은 carry와 같은 바이트다. 기존 hash 고정 OpenCV observer와 endpoint 함수는 수정하지 않았다. 제어에는 자기 RGB·자기 발행 명령·고정 지도/카메라만 쓰고 GT는 오프라인 보정·평가에만 쓴다.

## 기록 정정과 검증

**113/123은 바뀌지 않은 selfmap6 관문 회귀 재생**이다. reloc8의 효과 근거에서 제외한다. `scripts/analyze_reloc8.py`와 이전 README/summary도 정정했다. 기존 10°/15cm 위험 수락0은 당시 기준의 값이다. 새 평가 기준은 절대 오차>5° 또는>10cm와 보정 전 대비 `max(xy/.10,yaw/5°)` 악화를 따로 센다. 축별 악화도 별도 보존한다. 이 평가 GT로 제어 관문을 바꾸지 않았다.

| selfmap6 저장 실행 | 제안 | 수락 | 5°/10cm 초과 | 정규화 오차 악화 | xy/yaw 축별 악화 |
|---|---:|---:|---:|---:|---:|
| 93560 c8d9b6e5 | 52 | 52 | 0 | 19 | 29/19 |
| 93561 c8d9b6e5 | 71 | 61 | 11 | 34 | 32/33 |
| 합 | 123 | 113 | 11 | 53 | 61/52 |

각 원장/평가 경로와 sha256, 후보별 판정은 `selfmap6-regression.json`; 요약·시험 로그 해시는 `summary.json`이다. 작은 악화도 집계한 것이며 새 정책의 실패율로 해석하지 않는다. 관련89시험 통과 후 연결·로그 변경을 포함한36시험을 직렬로 재검증했다. off bundle 동일성, 기존 pulse/CW 응답 보존, 윗선 없는 열의 벽 삽입·바닥 clearing 차단, 실제 mapper로 토글 전달과 audit 출력도 확인했다.

carry의 별도 기록은 로컬 `/Users/changmin/projects/ugrp-wt/map-carry-zone/experiments/2026-10-15-reloc9/`와 PR505에 있다. 회전은 seed93261의27구간으로 맞추고 seed93262/93266의15구간으로 검증했다. 실제/추정 중앙0.6194→1.0767이지만 **7/15구간이0.9–1.1 밖**이다. −7.5° 저장 자기 검토 프레임67장에서 실제 벽점3,237→2,849, 체커선 근처621→606으로 윗선은63장에 남았지만 유효 벽 손실이 크고 오검출 제거는 작았다. 320×240 검토 JPEG를 확대했으므로 native640×480 전체 RGB의 성능 근거가 아니다. 새 GCP90°/180° 점검과 세 후보의 동일 시드 비교가 필요하다.

PR511 질감 장면 의견: 체커선 감소가 벽 높이 검증을 대신하지는 않는다. 가드를 독립 조건으로 남기되 현재 유효 벽점 손실을 고려해 질감의 원본 RGB로 별도 비교해야 한다. 미병합 코드에 의존하거나 질감 장면의 효과를 측정했다고 주장하지 않는다.

## 재현 명령

carry pytest 종료 뒤 아래를 실행한다. 원본은 기록된 로컬 회수 경로가 필요하고 출력에는 새 이름을 쓴다.

```sh
cd /Users/changmin/projects/ugrp-wt/map-selfmap
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests
mkdir -p tmp
"$PY" -m scripts.analyze_reloc8 --flow selfmap --output tmp/reloc9-selfmap6-NEW.json
"$PY" -m pytest -q -p no:cacheprovider --basetemp=tmp/pytest-reloc9-NEW tests/test_reloc9_shared.py tests/test_reloc9_selfmap.py tests/test_reloc8_selfmap.py tests/test_self_pulse_rotation.py tests/test_self_pulse_odom.py tests/test_selfmap4.py tests/test_selfmap5.py tests/test_selfmap6.py tests/test_self_map_executor.py tests/test_self_map_integration.py
```

`run_self_map_diagnostic`의 prepare-only CLI에 `--reloc9-rotation-calibration-v1 --reloc9-wall-height-guard-v1`을 주면 번들에 연결된다. 실제 실행은 별도 조정자 결정이며 이번 작업에서는 실행하지 않았다.

## 참고 자료

- [Thrun·Burgard·Fox, Probabilistic Robotics, MIT Press2005](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/): 공식 서지·소개 확인. 명령 이동 모형·관측 갱신의 분리 원칙을 참고하며 정식 보정 절차 전체를 구현했다는 주장은 하지 않는다.
- [Borenstein·Feng, Measurement and Correction of Systematic Odometry Errors in Mobile Robots, IEEE TRA12(6),869–880,1996](https://ieeexplore.ieee.org/abstract/document/544770/): 출판사 초록·서지 확인. UMBmark의 체계적 오도메트리 보정과 검증 분리 원칙 참고. 이번 제자리 회전 맞춤은 양방향 사각 주행 UMBmark 실행이 아니고 차동 구동 수치를 메카넘에 이식하지 않았다.
