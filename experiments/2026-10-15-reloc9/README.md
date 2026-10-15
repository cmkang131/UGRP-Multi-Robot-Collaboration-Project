# reloc9 — 회전 적분·벽 윗선·재획득 묶음

기준은 carry `0459c03c`(PR505), selfmap `66928f23`(PR506)이다. **오프라인 후보이며 ready=false**다. 이번 작업의 실제 시뮬레이션·렌더·모델 호출·원격 접속은 모두 0이다. 기존 원본은 읽기만 했다. 실행 소스는 이 기록이 포함된 커밋, 정확한 SHA는 커밋 뒤 생성하는 로컬 비활성 큐에 고정한다.

## 변경과 입력 경계

| 토글 | 기본 | carry | selfmap |
|---|---|---|---|
| `reloc9_rotation_calibration_v1` | false | `CommandPose.issue`에서 순수 동일 듀티 제자리 회전의 yaw만 오프라인 계수로 보정. 공유 적분 결과를 카메라·기억·지도 코드에 한 번만 전달 | 기존 `s2_pulse_v122_rotL_v1` 펄스 응답 재사용. carry의 정상상태 계수를 중복 적용하지 않음. 계획과 적분의 선택 모형도 일치시킴 |
| `reloc9_wall_height_guard_v1` | false | 기존 hash 고정 OpenCV 검출 뒤, endpoint 변환 전에 실제 윗선 필터 | 높이 무관 벽 검출 뒤, 선분 맞춤·바닥 ray·문 검출의 벽 열 입력 전에 같은 필터 |
| `reloc9_reacquisition_v1` | false | 명령 적분 기억 방향 복귀 → 거리 1/.6/1.6배에 맞춘 틸트·전체 팬 → 최대 한 바퀴 몸 회전. 가장자리 색 성분 방향으로 몸 돌리기 2회 한도 | 해당 없음 |

벽 높이는 고정 장면의 0.40 m다. 측정 윗선이 영상 안에 없거나, 발행 서보 FK가 계산한 높이 위치와 맞지 않거나(4px+예상 밴드 높이의10%, 최대12px), 실제 밝기/색차 step이4 미만이면 열을 버린다. 윗선이 화면 밖인 진짜 벽도 보수적으로 버린다. 원래 `opencv_wall_observation.py`와 `zone_solo_cyan_amcl_sensor.py`는 바이트를 유지했다. 기본 off에서는 필터 계산을 하지 않고 기존 관측 객체를 그대로 반환한다.

재획득 출처: **act10 PR504 `567dc12041b4562ab0d972764f350684a2f267f0:harness/grasp_act_search.py`**. carry의 공유 명령 적분·유한 회전 예산에 맞춰 같은 원리로 구현했다. 기억/색 성분은 시선·몸 회전만 정하고 평행 이동·파지·성공 판정을 하지 않는다. 노랑 차체/구역 같은 같은 색 오인이 가능한 단서이므로 두 번만 쓴다. 교사의 기존 새 유효 가시 측정만 재획득을 끝낸다. 자기 RGB·자기 명령·고정 지도/카메라만 사용하며 GT와 접촉·측정 관절·공용 카메라는 제어에 추가하지 않았다.

## 저장 원장 검증

- 회전: gcp1 `n4-highcpu-64` 네 실행만 사용. seed93261의 `8c6f219c`/`0459c03c` **27구간**으로 원점 통과 최소제곱 맞춤, seed93262 `0459c03c`와 seed93266 `d9e0073f` **15구간**은 검증 전용이다. 구간당 추정 회전≥8°, RGB full fix가 끼인 구간은 제외했다. 검토자의 43구간과는 추출·분할이 달라 별도 코호트다.
- 고정 계수 **0.5752851597**. 별도 검증 실제/추정 중앙 **0.6194→1.0767**, p10–p90 **0.5091–0.6689→0.8850–1.1628**. 0.9–1.1 안은 **8/15**, 밖은 **7/15**다. 중앙 기준을 충족했으나 전 구간 충족은 아니다. 학습 표본의 최대 상대 잔차를 따라 회전 불확실성 비율은 **0.4921**(최소0.40)로 유지한다. 공분산이 실측 보정됐다는 주장은 하지 않는다.
- −7.5°에서 발행 서보가 0.8초 이상 같은 **자기 저장 프레임67장**: 바닥 벽점 **4,921→4,529**, 평가상 실제 벽5cm 이내 **3,237→2,849**. **63/67장**에 실제 벽과 맞는 밑점의 측정 윗선이 남았다. 체커선2cm 이내는 **621→606**이며 실제 벽과 겹칠 수도 있다. 제거392점 중 실제 벽점388점이므로 이 가드는 유효 벽점 손실이 크고 체커 제거 효과가 작다. 윗선 존재 가드만으로 벽 오인을 해결했다고 판단하지 않는다.
- 위 프레임은 회수된 **320×240 검토 JPEG를640×480으로 확대한 진단**이다. 실제 발행 팔 자세와 원장 시각을 맞췄으며 다른 자세를 가정한 프레임은 쓰지 않았다. 전체 원본 해상도에서의 재현·정탐률·재획득 개선은 미검증이다.
- 보정은 **5°/10cm 절대 초과**와 **전후 `max(xy/.10,yaw/5°)` 악화**를 나눠 세며 축별 악화도 남긴다. 93262 t129.3: yaw **69.221→0.601°**, xy **19.944→16.639cm**, 정규화 오차 **13.844→1.664**이므로 절대 초과지만 악화가 아니다. 새 reloc8 93262의 full2/partial포함3건은 절대 초과2/3건, 정규화 악화0건이다. 비교 `d9e0073f` 93266은 full2/partial포함4건 중 악화0/1건으로 따로 기록했다.
- **정정:** selfmap **113/123**은 바뀌지 않은 selfmap6 관문 회귀 재생이다. reloc8 성능 근거에서 제외한다. 5°/10cm 절대 초과 **11/113**, 정규화 악화 **53/113**, xy/yaw 축별 악화61/52건이다. 두 selfmap6 실행은 PR506의 별도 `selfmap6-regression.json`에 있다. 현재 GCP93571 결과를 추정하거나 완료 처리하지 않았다.

분할 원장·결과·원본 경로/해시·중단 상태는 `rotation-replay.json`, `wall-replay.json`, `correction-replay.json`, `summary.json`에 있다. 현재 source의 새로운 인과 실행이나 실제 성공률로 해석하지 않는다.

## 대기열

커밋 뒤 이 worktree의 **Git에서 제외된 `tmp/20261015-solo-carry-<sha8>.json`**에 생성한다. Git source를 깨끗하게 유지하면서 전체 source SHA와 추적된 계획 해시를 고정한다. 첫90°좌/180°우 회전 점검1 + 정확한 재현3/신규8개 배치×후보3 = **34개 직렬**이다. 후보는 회전만/회전+벽/회전+벽+재획득이고 같은 시드·배치를 쓴다. 승인·enabled·ready·stage_ready·execute·submitted는 전부 false다. 점검 명령 자체도 기본 prepare-only이며 승인 뒤 `--execute`를 별도로 붙여야 한다. 두 회전의 실제/추정이 각각0.9–1.1이고 원장을 검토한 뒤에만 조정자가 다음 단계를 결정한다. 각 후보 첫30초 원본·위험 및 악화·새 유효 관측 수를 따로 확인한다. selfmap 큐는 만들지 않았다.

PR511 질감 장면에 대한 **의견**: 질감으로 체커선 오인이 줄어도 벽 높이를 입증하지는 않으므로 독립 가드는 유지할 이유가 있다. 현재 가드의 유효 벽 손실도 크므로 질감 장면의 원본 RGB로 별도 비교한 후 선택해야 한다. 미병합 코드에 의존하거나 새 성능을 주장하지 않는다.

## 재현 명령

```sh
cd /Users/changmin/projects/ugrp-wt/map-carry-zone
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
mkdir -p tmp
"$PY" -m scripts.analyze_reloc9_rotation --calibration-runs solo-carry-93261-8c6f219c solo-carry-93261-0459c03c --validation-runs solo-carry-93262-0459c03c solo-carry-93266-d9e0073f --output tmp/reloc9-rotation-NEW.json
"$PY" -m scripts.analyze_reloc9_walls --output tmp/reloc9-walls-NEW.json
"$PY" -m scripts.analyze_reloc9_corrections --runs solo-carry-93261-8c6f219c solo-carry-93261-0459c03c solo-carry-93262-0459c03c solo-carry-93266-d9e0073f --output tmp/reloc9-corrections-NEW.json
"$PY" -m pytest -q -p no:cacheprovider --basetemp=tmp/pytest-reloc9-NEW tests/test_reloc9_carry.py tests/test_reloc9_shared.py
"$PY" -m scripts.prepare_reloc9_carry_queue --queue-out "tmp/20261015-solo-carry-$(git rev-parse --short=8 HEAD).json"
```

출력 경로는 새 이름을 쓴다. 관련 carry129개 통과와 최종 새 기능 시험은 로그에 보존했다. 처음 mock 시험의 subprocess patch가 zstd까지 가로챈 시험 격리 오류는 수정 후 재시험했으며 실패 로그도 보존했다. mock 시계 시험은 MuJoCo 구성/step이 없고 평가 yaw를 바꿔도 발행 명령이 같음을 확인한다. selfmap pytest는 carry 종료 뒤에만 실행했다.

## 참고 자료

- [Thrun·Burgard·Fox, Probabilistic Robotics, MIT Press 2005](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/): 공식 출판사 서지·소개 확인. 명령 이동 모형/불확실성과 관측 갱신을 구분하는 원칙을 따른다. 책의 정식 보정 절차를 모두 구현했다는 의미는 아니다.
- [Borenstein·Feng, Measurement and Correction of Systematic Odometry Errors in Mobile Robots, IEEE TRA12(6),869–880,1996](https://ieeexplore.ieee.org/abstract/document/544770/): 출판사 초록·서지 확인. UMBmark의 체계적 오도메트리 계수 보정과 검증 분리 원칙을 참고했다. 여기서는 제자리 회전의 원점 통과 맞춤이며 UMBmark의 양방향 사각 주행을 수행하지 않았다. 차동 구동 연구의 수치를 메카넘 로봇에 그대로 적용하지 않았다.
