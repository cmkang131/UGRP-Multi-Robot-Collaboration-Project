# OpenCV 벽 관측기 열별 진단과 부분 고정(partial fix) 판정 (2026-10-05)

상태: DEV 오프라인 분석(시뮬레이션·렌더·모델 호출 없음). 확증 아님. 기본 off 플래그 후보 한 개.
기준 SHA: 9018369c(#383 라이트 모드) 위 브랜치 `claude/llm-eye`. 원본 결과: `/Users/changmin/projects/ugrp/outputs/llm-eye-20261005/`.

## 1. 질문과 결론

질문(조정자): light2 r1 `rgb/02334.jpg`(pan 1500), `02719.jpg`(pan 1230, 137.25 s)에서 벽 경계가 뚜렷한데 고정이 0개였다. OpenCV 관측기가 열을 버린 이유는?

결론: **관측기는 열을 거의 버리지 않았다.** 원인은 관측기가 아니라 그 다음 단계의 "고정 영수증" 판정(`zone_final_pair_scan.quality`)이다.

| 프레임(파일) | pan | 통과 | 후보 0개 | 후보 2개 이상 | 행 가장자리 | 단차 미달 | 채도 마스크 |
|---|---|---|---|---|---|---|---|
| 02334 (frame_id 2335, 118.0 s) | 1500 | 58 | 36 | 0 | 0 | 0 | 2 |
| 02719 (frame_id 2720, 137.25 s) | 1230 | 85 | 11 | 0 | 0 | 0 | 0 |
| 02724 (frame_id 2725, 137.5 s) | 1230 | 85 | 11 | 0 | 0 | 0 | 0 |

- 통과 열의 경계 행은 정답(평가 전용: 궤적+정적 지도로 계산)과 중앙값 0.5 px, 대부분 4 px 안(02334 58열 중 2열, 02719 85열 중 1열만 4 px 초과).
- 같은 보정·게이트 값(`own_image_gates_floor_light_v1`: S<140, 단차>=10)으로 실제 `observations()`를 불러 열별 분류를 계산했고 통과 열 수가 일치함을 확인했다(`consistent_with_observer: true`).
- 체크무늬 바닥/밝은 띠로 인한 "후보 2개 이상"은 이 프레임들에서 0열이다. 세 실행 약 300프레임(40프레임 간격) 조사에서도 후보 2개 이상은 0열이다(`survey_*.json`).
- 시각화: `columns_r1_02335.png`, `columns_r1_02725.png`(열 색: 통과 초록 / 후보 0개 회색 / 채도 빨강; x는 정답 경계).
- 파일 번호는 frame_id-1이다(02334.jpg = frame_id 2335). 직전 프레임(frame_id 2719, 파일 02718)은 pan 1242로 이동 중이라 보정된 자세가 아니어서 관측기가 처리하지 않는다.

고정이 0개였던 진짜 이유(오프라인 재생으로 확인): `quality()`는 3x3 정보행렬(x, y, yaw)의 **가장 작은 고유값 > 1**을 요구한다. 칸막이/동쪽 벽처럼 직선 벽 하나만 보면 벽을 따라가는 방향(y)은 관측되지 않아 가장 작은 고유값이 0이다(`geometric_curvature: 0.0`, 인라이어 비율 1.0, 지지도 1.0). 거리·방향은 mm 수준으로 관측돼도 영수증이 거부된다. 재생 중 pan 1230 첫 프레임(137.4 s)에서만 곡률 172로 통과했고 다음 프레임에서 다시 0이었다(수치 미분이 불안정한 경계).

## 2. 변경: 고유값 두 번째 기준(기본 off)

`harness/zone_pair_highpose_partial_fix.py` (동결 파일 수정 없음). 곡률 검사만 `lambda_min > 1` 에서 `lambda_second > 1`(강한 방향 2개 이상)로 바꾼다. 인라이어 비율·지지도·포화·정착 검사와 단위 임계값 1은 그대로이며 새 상수가 없다. 영수증에 `observed_rank`, `weakest_direction_xy_yaw`, `partial: true`를 남겨 약한 방향이 측정되지 않았음을 표시한다. PF 가중치는 이미 같은 방식으로 동작한다(약한 방향의 우도는 평평). `build_source_class()`가 `PartialFixHighPoseSource`를 만든다. 기본 `HighPoseSource`는 그대로다. 실행기 연결(공급자 선택)은 따로 하지 않았다.

참고: light2 r1 재관측 구간(132-138.8 s)을 이 공급자로 오프라인 재생하면 relook 시작 뒤 첫 정착 프레임(136.4 s대)부터 `informative_fix`가 참이 된다(기본 공급자는 같은 구간에서 137.4 s에 1프레임만). 이 재생은 PF 상태·시드가 실제 실행과 같지 않아 근사다.

## 3. 평가(평가 전용 정답, 관측기·판정에는 정답 미사용)

방법: 정착된 보정 자세 프레임을 표본(DEV는 10프레임 간격, 확인은 20프레임 간격)으로 뽑아, 정답 자세에 무작위 어긋남을 준 가우시안 입자 구름을 만들고 한 프레임을 반영해 두 판정과 사후 평균 오차를 비교한다(`scripts/eval_partial_fix_gate.py`). 튜닝 상수 없음(위 규칙 고정). 분할: DEV = light2 + light3(두 실행은 같은 궤적이라 사실상 한 실행), 확인 = v103a, wtX-n0b, light4(다른 실행).

| 사전(prior) | 구분 | 프레임 | 기존 수용률 | 새 수용률 | 새로만 수용된 프레임의 xy 오차(사전→사후, mm 중앙값) | 새로만 수용 중 사후 xy>100mm 또는 yaw>3도 |
|---|---|---|---|---|---|---|
| tight (2cm/0.6도) | DEV | 202 | 0.386 | 1.00 | 21.3 → 17.1 | 0.00 |
| tight | 확인 | 285 | 0.228 | 0.635 | 21.4 → 18.2 | 0.00 |
| dock (5cm/1.7도) | DEV | 202 | 0.366 | 0.99 | 55.7 → 31.7 | 0.016 |
| dock | 확인 | 285 | 0.267 | 0.635 | 56.7 → 37.7 | 0.029 |
| wrong (20cm/8.6도 어긋남) | DEV | 202 | 0.178 | 0.416 | 164.8 → 123.9 | 0.625 |
| wrong | 확인 | 285 | 0.161 | 0.302 | 183.2 → 156.1 | 0.775 |

- 새로 수용된 프레임을 반영해도 오차가 사전보다 나빠진 비율은 0~1%(xy, yaw).
- 정직한 한계: 사전이 크게 틀린 경우(wrong) 기존 판정이나 새 판정이나 수용된 프레임의 78%가 여전히 크게 틀린다(기존 수용 78%, 새로만 수용 78%로 같음). 즉 새 판정이 틀린 사전을 더 못 거르는 것은 아니지만, 이 판정은 위치 오류 탐지기가 아니다. 수용된 프레임의 사후가 기각된 프레임(98%)보다는 낫다.
- 약한 방향(벽을 따라가는 방향)의 오차는 줄지 않는다. 이 영수증은 "벽 법선+yaw를 새로 고정했다"는 뜻이다.
- 범위: 무적재(unloaded) 보정 자세만 평가했다. 적재(높은 자세) 프레임은 평가하지 않았다. 실제 폐루프(정렬 재관측 이후 제어 흐름) 결과는 없다.

## 4. 별도 관찰(미해결, 이번 변경 범위 밖)

v103a r2 `frame_id 4000`(t=201.25, 바닥 파지 자세 3:770, 4:1982, 5:1876, pan 1500)에서 카메라가 바닥을 내려다보는데 관측기가 77열을 "통과"시키고 모두 정답 경계와 크게 다르다(중앙값 188 px 어긋남; 바닥 타일의 밝기 경계를 벽 밑단으로 오인, 후보는 열당 1개라 "후보 2개 이상" 필터가 걸리지 않는다). v103a/wtX 조사에서 pan 1500 통과 열의 약 75%가 4 px 이상 어긋났다(`survey_*.json`의 `pass_row_err_gt4px`). 이 열들은 PF 우도의 이상치 혼합이 흡수하는지는 확인하지 않았다. 후속 후보: 바닥 응시 자세에서는 벽 관측을 쓰지 않는 자세 게이트, 또는 벽 윗단(상단 에지) 보임 조건.

## 5. 참고 자료 (V=원문/초록 확인, U=확인 못함)

- V: Zhang, Kaess, Singh, "On degeneracy of optimization-based state estimation problems", ICRA 2016, pp. 809-816. 정보행렬 구조를 분석해 퇴화(degeneracy)를 완화. 이 변경의 근거(퇴화 방향은 갱신하지 않고 나머지 방향만 사용).
- V: Li, Birchfield, "Image-based segmentation of indoor corridor floors for a mobile robot", IROS 2010. 벽-바닥 경계 후보 수평 에지를 여러 단서로 평가. 이번에는 구현하지 않음(관측기가 이미 경계를 잡고 있음).
- V: Delage, Lee, Ng, "A dynamic Bayesian network model for autonomous 3D reconstruction from a single indoor image", CVPR 2006. 영상 열마다 바닥-벽 경계를 인식하는 모델. 현 열 단위 관측기와 같은 형태.
- V: Hedau, Hoiem, Forsyth, "Recovering the spatial layout of cluttered rooms", ICCV 2009. 바닥-벽 경계는 가려지기 쉬워 전역 상자(소실점) 구조로 보강. 후속 후보(U 구현).
- U: Thrun, Burgard, Fox, Probabilistic Robotics (2005), 다중 후보 처리(최근접 연관, 혼합 우도)와 선분 특징은 법선·방위만 제약한다는 설명. 책 본문은 이번에 다시 읽지 않았다. 다중 후보 혼합은 실제 후보 2개 이상이 0열이라 구현하지 않았다.
- U: LSD(von Gioi et al. 2010), 능동 위치추정(Burgard, Fox, Thrun 1997)은 조회하지 않았다.

## 6. 재현

```
# 열 분류 + 시각화 + 조사
python3 scripts/diagnose_opencv_columns.py --run <outputs>/v98-dev-case-carry-b322d8a8-s911-v105light2/zone_wide_door_geometry_v3 \
  --calibration <outputs>/v98-dev-case-carry-b322d8a8-s911-v105light2/dev_pilot_calibration.json --robot r1 \
  --frame 2335 --frame 2720 --frame 2725 --survey-every 40 --out <dir>
# 판정 비교
python3 scripts/eval_partial_fix_gate.py --outputs <outputs> --run <run> ... --out <json> --every 10 --max-frames 150
```
원본 JSON: `outputs/llm-eye-20261005/partial-fix/dev_split.json` sha256 e90c6d02709790c2f4636fbb1eb922fe3f5c71ad7f622ca6e79a24ff530c045f, `confirm_split.json` sha256 abec837c5328310bd3ad45523f9f150edde162a24a83c5aac4883ff8a0dd547a.
보정 JSON은 실행 폴더의 `dev_pilot_calibration.json`을 DEV 승인 검사 없이 읽는다(실행 폴더에 sibling manifest가 없음). 등록된 무적재 모션 채움만 `harness/zone_pair_highpose_contract.dev_pilot_admission()`에서 적용한다.
