# S3 동료 로봇의 벽 오인: 저장 RGB 오프라인 진단

기준 main `b07f33aba278fda7434acaed0974c3d38f7b9ef0`, 브랜치 `codex/owncam-robot-mask`.
**DRAFT 후보, 병합 금지.** 시뮬레이션·MuJoCo·새 렌더·모델 호출은 0회다.
S3 #394의 관측 위험만 다루며 S3 실행기·다른 PR·worktree·프로세스를 수정하지 않는다.
실행 번들·기본 제어기에는 연결하지 않았고 새 RUNNABLE_ID도 만들지 않았다.

## 먼저 조사한 방법과 선택

2026-10-06, 아래 원문/공개 코드를 읽은 뒤 구현했다. 라이브러리 실행·논문 성능 재현은 하지 않았다.

| 방법 | 확인한 내용 | 이번 적용 |
|---|---|---|
| 고전 HSV 분할 + 형태학 연산 [1,2] | `cvtColor`, `inRange`, opening/dilation/closing으로 색 영역·작은 잡음·틈을 처리 | OpenCV 함수를 그대로 사용. 로봇의 기존 주황색 외관에 맞춘 범위만 명시 |
| AMCL beam skipping [3] | 지도와 대다수 입자가 불일치하는 관측 제외, 수렴 시에만 작동, 과다 제외 시 복구 | PF를 바꾸는 대신 이번에는 RGB에서 먼저 제외. AMCL을 구현했다고 주장하지 않음 |
| DynaSLAM 2018 [4] / VDO-SLAM [5] | 동적 물체 마스크로 정적 구조와 분리. VDO 공개 README는 OMD 물체의 색 분할 사용을 명시 | 물체 영역 제외라는 설계 참고. 학습기·깊이·optical flow·정답 label 연결은 사용하지 않음 |
| VAR-SLAM 2025 [6] | 알려진 물체 필터와 강건 오차 함수를 결합. 깊이로 배경 특징의 과다 제거를 줄임 | RGB만 있는 현재 경계에서는 깊이 기반 복원 불가. 과다 제외를 별도 비용으로 보고 |

## 1단계: 자료·채점·결과

먼저 `outputs/s1-placement-settle-35034c5b-*/*robot_cam.jpg` 12장을 육안 확인했다.
동료 로봇이 보이지 않아 동료 오인의 양성 자료로 쓰지 않았다. S1 저장물에는 이 진단에 필요한
프레임별 발행 servo 기록도 없어 임의 자세를 넣어 수치 결과를 만들지 않았다.

짝 운반의 기존 완료 DEV 자료
`outputs/v98-dev-case-carry-24144281-s912-v105light8b/zone_wide_door_geometry_v3/`
(실행 소스 `24144281dad169ce6fb87e7a2b1bd18ff67eb19e`)에서 r1/r2 각각
전체 저장 프레임 인덱스의 등간격 18장, 합계 36장을 선택했다. 같은 실행의 고정 unloaded
카메라 보정에 자세가 있는 **16장 전부**를 채점했다. 나머지 20장은 해당 보정이 없어 제외했다.
카메라 보정은 기존 발행 servo로 조회한 고정 행렬이며 현재 위치·관절 정답을 사용하지 않는다.
카메라의 z축 pan 회전은 행 투영을 바꾸지 않아 생략한 오프라인 관측 진단이다.
불안정 자세/실제 PF가 채택한 시점까지 재생하지 않았으며, PF 위치 오차나 누적 실패율이 아니다.

동료가 보이는 7장에는 **왜곡을 편 자기 RGB에서 눈으로 그린 로봇 외곽**을 평가 label로 붙였다.
채택한 위/아래 경계 중 하나가 그 외곽 안에 있으면 그 열을 오인 1개로 센다(두 경계를 중복 계산하지 않음).
외곽은 관측 호출이 끝난 뒤 채점에만 쓰고 관측기에는 전달하지 않는다. 숨겨진 벽 위치를 추정해
오차 정답으로 만들지 않았으며, 경계 근처의 수작업 label은 근사치다.
나머지 9장은 동료가 보이지 않는 비교 자료다. 관측과 mask는 RGB만 사용한다.

| 지표 | 기존/옵션 OFF | `orange_columns_v1` ON |
|---|---:|---:|
| 동료가 보이는 프레임 | 7 | 7 |
| 오인이 나온 프레임 | 3/7 | 0/7 |
| 동료를 벽으로 받아들인 열 | 4/391 채택 열 (전체 검사 672열) | 0/368 채택 열 |
| 동료가 보이는 프레임의 채택 열 | 391 | 368 |
| 동료 외곽으로 표시하지 않은 열의 추가 제외 | 0 | **19** |
| 동료가 없는 9장의 채택 열 | 293 | 293 |

오인 사례는 fixture 02의 `(362, 14.08)`, 03의 두 열, 21의 한 열이다.
정확한 소수 좌표는 [result.json](result.json)의 `false_edges_before`를 따른다.
기존 채도 필터가 주황색 부품은 거르지만 검은 팔/몸체에서 나온 경계를 남기는 현상이다.
추가로 빠진 19개는 정상 벽을 포함할 수 있다. 배경 정답을 전부 붙이지 않았으므로 이를
"정상 벽 19개" 또는 "오인 19개 추가 제거"로 해석하지 않는다.

이것은 한 실행에서 찾은 **탐색·회귀 자료**다. HSV/연산 크기는 이 외관에 맞춘 후보이며
독립 검증/확증 코호트가 아니다. 현재 0/7을 모든 동료 가림에 대한 해결로 승계하지 않는다.

## 2단계: 명시적 옵션

```python
from harness.opencv_wall_observation import OpenCVObserver, masked_observations

# 기존 호출은 그대로 OFF. 새 옵션을 명시할 때만 적용한다.
observer = OpenCVObserver(vl, camera_callback, gates, robot_mask='orange_columns_v1')
obs = masked_observations(vl, own_bgr, camera, gates, robot_mask='orange_columns_v1')
```

`observations()`의 소스는 원래 바이트 그대로다. 기본 `OpenCVObserver.observe()`는 기존 함수를
직접 호출하고 `record()`의 OFF 형식도 그대로다. 알 수 없는 옵션은 즉시 거절한다.
옵션 ON의 기록에는 프로필·수치·RGB 전용·미등록 후보 상태를 남긴다.
기존 exact 가속의 소스 지문과 memo 호환도 시험했다. 제어기/실행 번들 기본값은 바꾸지 않았다.

마스크는 HSV `H=5..25, S=100..255, V=60..255` → 3×3 opening → 5×5 dilation →
열 방향 합치기 → 31열 closing이다. 검은 부품의 작은 틈을 메우고 해당 열의 위·아래 관측을
`NONE/NaN`으로 제외한다. VGA 전용이며 값은 `ROBOT_MASK_CONFIG`에 명시돼 있다.
색 범위·31열 크기는 논문이 보장한 값이 아니라 기존 MasterPi 주황색 외관과 이 해상도에 맞춘
개발 후보다. 단일 RGB에서 가려진 배경을 복원할 근거가 없어 열 전체를 버리는 보수적 선택이다.
픽셀을 덧칠해 새 벽을 찾지 않고 원래 영상의 관측 중 일부만 뺀다.

한계: 주황색 배경도 빠질 수 있다(그림의 문 뒤 주황색 선 포함). 주황색이 안 보이는 회색 로봇,
어두운 장면, 큰 검은 틈, 다른 외관에는 효과를 보장하지 않는다. 관측 감소가 PF에 끼치는 영향,
새 프레임/새 장면·실제 운반·실물은 미검증이다. 다음 실행 적용에는 별도 번들/인수 검증이 필요하다.

## 재현·검증·보존

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_opencv_wall_robot_mask.py

/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  scripts/diagnose_owncam_robot_mask.py --output /absolute/path/to/NEW-output
```

변경 모듈용 시험 파일 하나만 실행: **13 passed**. 저장 프레임·옵션 OFF 배열 바이트 동일·
기존 record 동일·가속 호환·입력/캐시 보존·잘못된 옵션·프레임 거절·색 없는 로봇의 한계·
원본 해시 변조 거절을 확인했다. 전체 로컬 시험/시뮬레이션을 실행하지 않았다.
CI 목록에 이 시험을 등록했으며 원격 CI는 PR에서 별도로 확인한다.

원본 JPEG와 카메라 행렬·발행 명령·수작업 외곽은
[`tests/fixtures/owncam_robot_mask`](../../tests/fixtures/owncam_robot_mask/manifest.json)에
원본 경로·SHA-256과 함께 약 272 kB로 보존한다. 원래 raw는 수정/삭제하지 않았다.
이 작은 fixture 복사본만 Git 보존이며 원래 실행 전체의 원격 백업은 아니다.
전체 진단 산출물·원자료 점검·시험 로그는
`/Users/changmin/projects/ugrp/outputs/owncam-robot-mask-offline-20261006/`에 있다.
Git에 [수치](result.json)와 [검증 기록](validation.json)을 보존한다.

작업 기록: 관리 도구의 worktree 상한 9/8에 한 번 걸려 사용자 지정 worktree 생성/다른 작업 보존
요청을 사유로 `--allow-over-cap --reason`을 기록했다. 첫 survey는 두 번째 과거 실행에
동일 경로의 보정 파일이 없어 중단됐고, 보정 출처가 있는 첫 실행으로 범위를 명시했다.
같은 막힘을 반복하지 않았다. Google Drive·실험 잠금·다른 PR/프로세스에는 쓰지 않았다.

## TensorBoard

기본 공용 `outputs/tensorboard/1006-owncam-robot-mask/`에 OFF/ON 새 snapshot 2개를 추가했다.
EventAccumulator와 기존 서버 API에서 오인 **4→0**, 추가 제외 **0→19**, 비교 관측 **293→293**을
원자료와 대조했다. Chrome `강`의 기존 탭에 비교 필터와 고정 카드를 열고 두 run을 선택했다.
새 영상은 없다. 기존 서버(PID 52016, 공용 logdir)는 재시작/수정하지 않았다.
공용 HParams 스키마에 새 `condition`/`offline/*` 열이 없어 **HParams 전체 표시 확인은 미완료**다.
표시 가능한 `policy`/`result/model_calls`만 적용했다. 링크·요청 열·미완료 사유는
`outputs/tensorboard-view.json`의 `owncam_robot_mask_offline_20261006` 키에만 추가했다.
[고정 비교 화면](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpeer_false_columns%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fextra_removed_not_peer%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcontrol_kept_columns%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E1006-owncam-robot-mask%2F#timeseries) · [검증 기록](validation.json)

## 참고 자료

확인일 2026-10-06. 직접 적용한 것은 [1,2]의 표준 OpenCV 연산이다.

1. [OpenCV HSV inRange 공식 튜토리얼/코드](https://docs.opencv.org/4.x/da/d97/tutorial_threshold_inRange.html)
2. [OpenCV Morphological Transformations 공식 튜토리얼/코드](https://docs.opencv.org/4.x/d9/d61/tutorial_py_morphological_ops.html)
3. [Nav2 AMCL likelihood_field_model_prob.cpp 공개 코드](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model_prob.cpp): beam skipping 및 수렴/과다제외 처리 확인.
4. Bescos et al., [DynaSLAM (2018) 논문](https://arxiv.org/abs/1806.05620), [공개 코드](https://github.com/BertaBescos/DynaSLAM).
5. [VDO-SLAM 공개 README](https://github.com/halajun/VDO_SLAM#5-processing-your-own-data): OMD 색 분할 설명 확인. 세부 MATLAB 파일은 직접 확인하지 못했으므로 동일 구현 주장에 사용하지 않음.
6. Soares et al., [VAR-SLAM (2025) 논문 §IV-A](https://arxiv.org/html/2510.16205v1), [공개 코드](https://github.com/iit-DLSLab/VAR-SLAM): 필터와 강건 추정 결합·깊이로 배경 보존하는 방법 확인.
