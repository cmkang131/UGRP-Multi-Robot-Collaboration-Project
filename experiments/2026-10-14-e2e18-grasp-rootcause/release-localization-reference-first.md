# 놓기 재위치 추정: 조사·입력 감사·전역 위치 재추정 후보

**재개 결과는 문서 끝의 “전역 위치 재추정 구현”에 있다. 아래 초기 회수 대기 기록은 당시 상태로 보존한다.**

2026-10-14. 작업 HEAD `e14fa729d1bbb80acb7706d4d53e99b19fe122ba`,
브랜치 `claude/grasp-act-probes`. PR #491의 실제 head는 `claude/grasp-act-release`이며 별도 브랜치다.
`/Users/changmin/.claude/CLAUDE.md`의 “같은 문제로 두 번 막히면 … 선행 논문, 공개 코드, 공식 문서를 조사” 지침을 읽었다.
제어 코드를 고치기 전 조사와 원본 검증을 수행했다. 사용자 지시의 회수 요청 후 중단 지점을 따른다.

## 이번에 직접 실행한 검증

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-14-e2e18-grasp-rootcause/audit_release_localization_inputs.py
```

- cdace35e의 40개 result와 회수 RGB 282개의 SHA-256이 해당 실행의 원격 SHA256SUMS와 **322/322 일치**했다.
- 저장된 검출값을 넣고 현행 `LookaroundLocalizer.finalize()`를 실행했다. 마지막 결정 **80/80이 원본과 동일**, 수락 **0/80**이다.
  이것은 검출 원장의 종료 결정 재생이다. RGB 검출 재생이나 개선된 localizer 검증이 아니다.
- 관측 648/648에 `update_skipped=map_pose_unknown`, 마지막 결정 80/80에 같은 이유가 있다.
  벽 점 45,283개·바닥 구역선 1,871개·문 0개는 반복 검출 합계이며 고유 랜드마크 수가 아니다.
- `map_pose_known=False`가 80/80이다. `sim/lookaround_localization.py:299`에서 지도 대응 전에 반환하고,
  `finalize()`도 같은 조건에서 반환한다. **게이트 기록 0/648**, 지도 대응 잔차는 미계산이다.
  “Mahalanobis 임계값이 너무 작아서 80개를 거절”이라는 가설은 이 실행 경로의 원인이 아니다.
- 저장된 임계값: 벽 χ² 6.63, 공동 χ² 11.34, 구역선 0.20 m/10°, 문 0.30 m. 이번 경로에서는 실행되지 않았다.
- 관측 시 사전 σ 중앙값 x=0.050703 m, y=0.050734 m, yaw=2.002321°;
  범위 x=0.050189–0.051698 m, y=0.050462–0.054038 m, yaw=2.000622–2.005660°.
  모두 `arbitrary_command_start` 좌표계다. 이를 지도 중심의 좁은 사전분포로 취급하면 안 된다.
- 평가 전용 마지막 스윕 상대 오차 중앙 9.335→9.650 mm, 최대 29.548→30.099 mm.
  평가용 spawn으로 명령 원점에 맞춘 변위 오차이며 지도 오차 개선이 아니다. 지도 오차는 미정의다.

결과: [요약 JSON](release-localization-audit.json), [파일별 해시·영상 목록](release-localization-audit-inputs.json.zst).
Mac 시뮬레이션·렌더·학습·모델 호출 및 원격 배치 제출은 0이다. 이번 세션은 RGB 내용을 시각 검토하지 않았으므로 물리 실패 원인을 새로 단정하지 않는다.

## 동일 RGB 재생에 필요한 자료의 차이

회수 282장은 9개 실행의 검토 프레임이다. 자기 RGB **188장은 모두 320×240**, 나머지 **94장은 overview 640×480**이다.
40회 관문 중 자기 RGB가 있는 실행은 6개뿐이다. localizer가 실제로 소비한 640×480 자기 RGB는 로컬에 **0장**이다.
`scripts/run_grasp_act_release.py:250`는 검토 자기 영상을 320×240으로 줄여 저장하며,
`:316`의 `look_capture()`는 별도 시각의 640×480 입력을 검출한 뒤 검출 원장만 남긴다.
따라서 단순 확대나 overview 대체로 “동일 RGB 80건 재생”을 주장할 수 없다.
GCP에 별도 입력 캐시가 있는지 확인 요청한다. 없으면 그 사실을 명시하고,
이미 보존된 648개 body-frame 검출값의 추정기 재생과 후속 GCP의 실제 RGB 검증을 분리해야 한다.
보존되지 않은 입력을 새 렌더로 만들거나 평가 정답으로 제어 관측을 보충하지 않는다.

e14fa729의 7개 결과는 조정자 요약만 로컬에 있다. 0/7, 중심 중앙 0.448454 m/최대 0.768352 m는 그 요약값이다.
요약 서술의 18.4초와 각 실행 `sim_s`의 26.7초(ep00 54.2초)는 시간 기준 확인이 필요하다.
감사 위반값 0은 분모가 검증되었다는 뜻이 아니다. 원본 audit와 teacher/eval 원장을 먼저 요청한다.

## 실제 확인한 1차 출처와 적용 범위

| 출처 | 확인 범위 | 적용할 원칙·필요한 변경 |
|---|---|---|
| Fox, Burgard, Dellaert, Thrun (1999), [Monte Carlo Localization](https://www.cs.cmu.edu/~thrun/papers/fox.aaai99.pdf) | 원문 서론·§MCL: global localization/position tracking 구별, 초기 belief, 다중 가설·관측 갱신 | 지도 자세가 미지이면 지도 자유공간과 방향에 걸친 초기화가 먼저다. 임의 명령 원점의 ±3σ 격자를 지도 원점으로 쓰지 않는다. 센서 모델만 자기 RGB의 벽·문·색 구역 관측과 명령 기반 이동으로 바꾼다. |
| [Nav2 AMCL 공개 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/amcl_node.cpp) | `uniformPoseGenerator`와 `globalLocalizationCallback` 본문, 2026-10-14 main 열람 | 자유 셀과 전체 yaw에서 초기화하는 실제 구현을 확인했다. 이동하지 않고 관측을 갱신하는 `nomotionUpdateCallback`도 있다. 이 코드의 `initial_pose_is_known_`는 초기화 플래그이지 정확도 보증으로 복사할 값이 아니다. 복사·vendoring 시 commit과 라이선스를 고정한다. |
| [OpenCV 4.13 PnP](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html) | RANSAC PnP, pose refinement, planar/multiple solutions 본문 | 실제로 식별된 지도 모서리·문 모서리와 영상 대응이 있으면 `solvePnPRansac` → inlier만 `solvePnPRefineLM`을 그대로 쓴다. 선 검출의 잘린 끝점을 지도 모서리라고 간주하지 않는다. 평면 복수해는 독립 시야/다른 특징으로 구별한다. |
| [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) | loss·f_scale·method 설명 | 점/선 잔차 모델은 `loss='huber'` 또는 `soft_l1`의 표준 강건 최소제곱으로 정련한다. 단위와 측정 오차로 정규화하고 GT 성패에 맞춰 임계값을 조정하지 않는다. LM은 robust loss를 지원하지 않으므로 LM+Huber라고 잘못 구현하지 않는다. |
| Berman (2014), [Outliers Rejection in Kalman Filtering](https://www.ion.org/publications/abstract.cfm?articleID=11714), DOI 10.1109/PLANS.2014.6851466 | **학회 공식 초록만 확인, 유료 원문·세부 수식 미확인** | 정상 측정까지 계속 거절하는 상태의 복구로 reset/복수 필터가 필요하다는 결과를 확인했다. 무조건 게이트를 완화하는 처방은 아니다. 이번 0/80은 해당 게이트 자체에 도달하지 않았으므로 직접 원인 인용으로 쓰지 않는다. |
| Fox, Burgard, Thrun (1998), [Active Markov Localization](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated4/fox_active_loc.pdf) | 원문 초록·§1: 기대 entropy 최소화, 센서 방향과 이동 방향 선택 | 관측 부족이면 다음 정보가 생길 시야를 선택한다. 원 논문은 초음파 기반이라 RGB 실증으로 인용하지 않는다. 알고리즘 원칙은 유지하고 관측 모델/FOV만 우리 카메라로 바꾼다. |

이 출처들은 우리 구현의 성공을 입증하지 않는다. 이번에는 코드 적용 전 조사까지 완료했다.
조사에서 확인하지 않은 논문의 식·성능 수치나 임계값을 검증된 사실로 인용하지 않았다.

## 재개 시 구현·검증 순서

1. `map_pose_unknown` 전역 초기화부터 구현한다. 기존 `harness/zone_solo_cyan_*`/`own_map_amcl_vendor`의
   likelihood field·랜드마크·샘플링 코드를 확인해 표준 MCL 초기화/갱신을 재사용한다.
   점 대응을 확정할 수 있는 장면만 PnP/RANSAC 경로로 다룬다. 벽 한 면이나 평행 선의 낮은 잔차만으로 수락하지 않는다.
2. 전역 가설→지도 좌표 확정→국소 추적을 구분하고, 새 기본 off 토글로 넣는다.
   `map_pose_known=True`를 강제로 켜거나 spawn/평가 pose를 넣지 않는다.
   정답은 별도 평가기에서 위치·방향 오차를 계산할 때만 읽는다.
3. 자기 관측 부족이면 팬 스윕→물러나 재관측→몸 회전 순서로 진행한다.
   각 로봇이 자기 영상으로 판단하고 GO/ACK·기존 margin 보고 외에 상대 좌표나 영상 통로를 추가하지 않는다.
   이동 상한은 자기 RGB의 여유 공간·명령 오차·정적 지도 안전 여유와 펄스 길이로 도출한다.
   아직 해당 원장/시야를 확인하지 않아 상한 숫자를 새로 정하지 않았다.
4. 원장 기반 개선 n/80과 RGB 기반 검증의 분모를 분리하고 전체 오수락·거절·오차를 함께 보고한다.
   카메라 해상도와 시각이 다른 검토 프레임으로 80회 입력을 대체하지 않는다.
5. 관련 offline 시험을 통과한 뒤만 commit/push하고 원격 SHA를 대조한다.
   새 진단은 기존 시작 7개, 관문은 미실행 시드 40개(74200–74239 사용 이력은 아직 미확인)로 등록한다.
   새 대기열을 ready=true로 만들 때 이전 e14 큐를 superseded로 연결한다.

PR #496은 자연 바닥 희소 지도의 자기 시작 좌표 SLAM이며 정적 지도 없는 작업이다.
이번 정적 지도 재위치 추정과 결과를 합치지 않으며 상대 브랜치를 수정하지 않는다.

## 중단 상태

- 제어 수정·개선 수락/오차·관련 회귀시험·commit/push·새 실행 SHA·새 대기열은 아직 없다.
- 기존 e14 큐는 진단 실패인데도 ready=true가 남아 있어 ready=false와 진단 실패 차단 상태로 변경하고 재확인했다.
  대체 구현이 없으므로 superseded로 완료 표시하지 않는다. 원본/기존 실행 목록은 보존한다.
- `/Users/changmin/projects/ugrp/outputs/e2e18-admin/fetch-requests/release4.txt`에 가벼운 원장 우선 요청을 저장한 뒤 멈춘다.

PR #491에 [진행 상태 3줄](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/491#issuecomment-6169864376)을 남겼다. 완료 코멘트가 아니다.

## 전역 위치 재추정 구현 (2026-10-14 재개)

조정자가 회수한 release4 77개 파일의 로컬 SHA-256을 **77/77** 대조했다.
현재 실행기의 실제 입력을 재렌더하지 않았다. 모든 새 검증은 오프라인이며 Mac 물리·렌더·모델 호출은 0이다.

### 출처와 실제 적용

- [Fischler & Bolles 1981, SRI 원문](https://www.sri.com/wp-content/uploads/2021/12/ransac-publication.pdf)
  §II의 최소 표본→합의 집합→최소제곱 정련 순서를 적용했다. 벽 점은 고정 난수의 2점 RANSAC→TLS로 선을 만든다.
  지도 대응에서는 선이 적은 작은 정적 지도이므로 최소 비평행 선 2개의 대응을 무작위로 버리지 않고 전부 열거한다.
  벽의 어느 면·구역의 어느 변인지와 전체 방향을 가설로 남긴다. 선의 잘린 끝점은 지도 모서리로 취급하지 않는다.
  ACM DOI 주소는 403이었으나 SRI의 원문 §II(pp.383–384)를 직접 확인했다.
- [Fox et al. 1999, MCL](https://www.cs.cmu.edu/~thrun/papers/fox.aaai99.pdf)
  pp.1–3의 전역 위치 재추정/추적 구분과 다중 가설 원칙을 적용했다.
  **MCL 입자 필터를 구현했다고 주장하지 않는다.** 이번 구현은 지도 전체의 랜드마크 대응 가설이다.
  명령 원점의 좁은 Gaussian을 지도 prior로 쓰지 않으며, 자기 명령의 상대 SE(2) 이동으로 여러 관측을 현재 몸 좌표에 맞춘다.
- [Olson 2009](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf) §I–III:
  약한 사전 위치에서 국소 최적화 하나에 의존하지 않고 여러 변환을 비교한다는 근거를 확인했다.
  논문의 GPU/다중 해상도 구현을 이식했다고 주장하지 않는다.
- [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html):
  `loss='huber', f_scale=1`, 기본 `trf`를 그대로 호출한다. 거리 4 cm·각도 5°로 단위를 정규화한다.
  4 cm는 기존 구역선 모델의 `SIGMA_EDGE_M`, 5°는 기존 랜드마크 각도 모델에서 가져온 값이다.
- [Fox et al. 1998, Active Markov Localization](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated4/fox_active_loc.pdf)
  §4.1–4.3의 관측 행동으로 위치 모호성을 줄이는 원칙을 확인했다. 이번 행동 순서는 사용자가 지정한
  **팬 스윕→후퇴 재관측→몸 회전**이다. 기대 entropy를 적분한 next-best-view 최적화라고 부르지 않는다.
- [Berman 2014 공식 초록](https://www.ion.org/publications/abstract.cfm?articleID=11714)의 reset/복수 필터 복구를 재확인했다.
  유료 원문과 상세 수식은 **미확인**이다. 게이트 임계값을 임의로 풀어서 이번 문제를 고친 것은 아니다.

변경 파일은 `sim/global_landmark_localization.py`, `sim/lookaround_localization.py`,
`sim/release_global_observation.py`, `scripts/run_grasp_act_release.py`다.
새 선택은 `--lookaround setdown_global_v1 --placement global_localized_release_v1`이고 기존 기본값은 유지한다.
지도 전체 벽·같은 색 구역 변 대응을 검색한다. 문 검출은 기존 원장에서 0개이므로 이번 후보의 지지로 사용하지 않았다.
형상·색 서명·여러 시야가 충분하지 않은 사례를 무조건 수락하지 않는다.
최소 선 3개·시야 2개·비평행 법선 rank 2, 정규화 잔차 2.5 이내, 떨어진 가설과 점수 차 0.75를 요구한다.
이는 이번 DEV의 명시적 수락 규칙이며 확률적으로 보정된 신뢰도/95% 성공 보증은 아니다.

### 고정 입력 재생 결과

재현 명령:

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-10-14-e2e18-grasp-rootcause/replay_global_localization.py
```

| 입력 | 수락 | 평가 위치 오차 중앙 / 최대 | 거절 |
|---|---:|---:|---|
| cdace35e 저장 검출, 기존 | 0/80 | 지도 좌표 미정의 | map_pose_unknown 80 |
| 같은 40실행×2로봇 저장 검출, 새 후보 | 77/80 | 4.23 / 8.72 cm | 모호 2, 지지 부족 1 |
| e14fa729 진단 7×2 저장 검출, 새 후보 | 13/14 | 3.44 / 8.54 cm | 모호 1 |
| 별도 320×240 검토 RGB, 9실행×2로봇 | 1/18 | 1.35 / 1.35 cm | 나머지 17은 지지/안정된 프레임 부족 |

- cdace35e 수락 자세의 방향 오차 중앙 0.454°·최대 2.978°다. 평가 오차 15 cm 초과 오수락은 0/77,
  e14는 0/13이다. 전체 분모 80/14는 그대로 남겼다. cdace35e 거절은 gate09 r1, gate16 r2, gate24 r2이고
  e14 거절은 diagnostic05 r1이다. 거절 가설의 큰 오차를 수락 오차 평균에 섞거나 숨기지 않고 상세 원장에 남겼다.
- 가설 수는 80건에서 최소 31·중앙 625·최대 2,853개다. 수락 지지 선은 최소 5·중앙 24·최대 39개,
  지도 선분 대응 RMS는 수락 77건에서 중앙 3.54 cm·최대 4.72 cm다. 지지 선은 반복 시야의 검출 수이며 고유 랜드마크 수가 아니다.
- **이전 지도 오차는 미정의다.** 기존 9.65 mm는 평가 spawn으로 정렬한 명령 상대 변위 오차이며 새 지도 오차와 비교할 수 없다.
  따라서 확인한 개선은 지도 위치 수락 **0→77/80**이다. 동일 척도의 전후 위치 오차 감소를 확인했다는 주장은 하지 않는다.
- 0/80의 원인은 648/648 관측의 `map_pose_unknown` 조기 반환이다. 벽점 45,283·구역선 1,871·문 0,
  게이트 실행 0회, 잔차 미계산이다. 명령 좌표 prior σ는 x/y 약 5.07 cm·yaw 약 2.00°였지만 지도 prior가 아니다.
- 검토 RGB는 자기 188장 중 명령 카메라 미적격 40장·서보 변경 후 0.8초 미만 116장을 제외한 **32장**을 처리했다.
  원본 크기 그대로 K를 절반으로 조정해 기존 구역선 검출을 호출했고, 65개 선이 나왔다. 픽셀 검출 임계값은 그대로다.
  이 비교에는 벽 검출을 넣지 않았다. 640×480 실제 입력과 시간·크기·검출 경로가 달라 동등한 RGB 재현이 아니다.
- 새 실행에는 실제 소비한 640×480 JPEG를 `eval-lookaround-input/<rid>/`에 드문 검토 입력으로 저장하고
  각 검출 행에 경로·SHA-256을 기록한다. 학습용 카메라 스트림 기록은 계속 끈다.

[요약·모든 분모](release-global-replay.json), [실행별 수락/거절·평가·원본 해시](release-global-replay-detail.json.zst).
재생기는 허용 검출/명령만으로 `finalize()`를 호출한 다음 평가 정답을 결합한다. 정답을 기준으로 가설을 고르지 않는다.
다른 행동을 했을 경우의 결과나 폐루프 성공을 저장 입력 재생으로 추정하지 않는다.

### 놓기 제어와 이동 예산

- 수락한 자기 RGB 지도 자세와 자기 발행 내려놓기 명령의 FK로 자기 끝의 구역 margin을 계산한다.
  상대에게는 기존 `PairReleaseCode.post/deliver/ready`의 margin·옆 여유·상태만 보낸다.
  상대 영상·좌표·지도 가설을 공유하지 않는다. 자기 위치 확정 전에는 구역 prior를 정답으로 초기화하지 않는다.
- 위치가 모호하면 넓은 팬(−90/−45/0/45/90°, 주변+바닥)→**0.10 m 후퇴**→**45° 몸 회전 관측 후 원래 방향 복귀** 순서다.
  각 로봇은 자기 검출로 필요 여부를 판단하고, 다른 로봇은 기다린다. 세 단계 뒤에도 모호하면
  `active_observation_exhausted`로 끝내며, 첫 `insufficient`에서 즉시 끝나지 않는다.
- 후퇴 0.10 m는 기존 후퇴 0.15 m보다 작은 재관측 한 단계다. 기존 명령 속도 0.129 m/s·0.10초 펄스는 약 1.29 cm이고
  펄스 상한은 기존 0.15초 그대로다. 정적 벽에 대한 몸 반경 0.18 m+3×0.05 m 여유를 모든 보존된 유력 가설과 경로에서 검사한다.
  여유가 미확인이면 해당 이동을 생략하고 추가 팬 관측을 남긴다. 실제 동적 장애물 안전/무하중 회전 이득은 GCP에서 확인해야 한다.
- 운반 보정은 한 번 **0.20 m**, 최대 **5회** 후 매번 내려놓고 재관측한다. 이 장면의 축방향 총 여유
  1.4−0.6=0.8 m의 1/4로 한 구간을 제한했다. 총 1.0 m 예산은 등록 시작 오프셋 상한 0.8 m를 포함한다.
  이전 3×0.10 m 상한과 구별한다. 실제 이동량은 명령량과 별도로 평가한다.
- 원장·평가 프레임이 지도 확정 전후 서로 다른 좌표계를 명시한다. `own_rgb_localization_inputs`에
  로봇별 프레임 수·검출 처리 프레임 수·원본 해시 수를 남겨 0/0 감사를 성공으로 해석하지 않는다.

### 시험·등록·미확인

관련 시험 6개 파일의 **80개 통과**(기하, 실제 저장 검출 fixture, 모호한 지도의 거절, 명령 좌표 원점 불변성,
이동 정합, 기존 v1/v2, margin 메시지, clock-only 실행 루프의 재관측/후퇴 생략/이동 후 재관측).
clock-only backend는 물리·렌더가 아니며 실제 놓기 성공을 입증하지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_global_landmark_localization.py tests/test_lookaround_localization.py \
  tests/test_active_lookaround.py tests/test_release_zone_servo.py \
  tests/test_grasp_act_release_teacher.py tests/test_grasp_act_release_run.py
```

cdace35e 검토는 9개 실행에서 처음·중간·끝에 걸친 8시각씩, 개요·r1·r2 합계 **216장**을 직접 보았다.
두 로봇은 반대 끝을 향했고, 들어 올린 빔이 가리는 시야와 내려놓은 뒤 서로 다른 벽/구역선 시야를 확인했다.
이번 e14 회수에는 새 영상이 없어 e14의 물리 실패를 독립 영상 진단했다고 하지 않는다.
[본 프레임·SIM 시각](release-global-visual-review.json).

`release-global-diagnostic-plan.json`은 e14 진단 7개의 시작·역할·시드를 그대로 보존했다.
`release-global-gate-plan.json`은 미실행으로 보고된 74200–74239의 40개 시작을 승계했다.
main/열린 PR 18개에서 해당 `seed` 정의 0개, 로컬 회수 실행 plan에서도 0개였다.
[예약 점검](release-global-seed-reservation.json). GCP 원격 실행 이력 자체는 조회하지 않았으므로 조정자가 제출 직전 중복을 확인한다.

소스를 커밋·push하고 원격 SHA를 확인한 뒤 `outputs/e2e18-admin/vm3-queue/20261014-release-gate-<sha8>.json`을
`ready=true`로 등록한다. 진단 7개가 통과하고 첫 30 SIM초·영상·입력/위치 오차를 검토한 뒤에만 gate 40을 연다.
e14 큐는 대체 SHA에 연결해 superseded로 전환한다. **큐 등록은 실행 제출/관문 성공이 아니다.**
PR #491의 실제 head는 `claude/grasp-act-release`; 실행 소스는 지정된 `claude/grasp-act-probes`의 고정 SHA다.
실제 640×480 새 폐루프, 능동 관측의 이동/회전 효과, 7/7·38/40 관문, E2E 연결, CI 서버 결과는 아직 미확인이다.
