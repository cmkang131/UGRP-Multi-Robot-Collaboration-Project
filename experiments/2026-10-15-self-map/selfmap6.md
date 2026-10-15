# selfmap6 — 보정 전 공통 게이트·격리 롤백·반복 방 모호성 검사

2026-10-15 / PR #506 / 기준 selfmap5 `cfbab2afed755777383c45347062b593175a7cc5`.
**오프라인 정책 검증만 완료, 실제 지도/주행 개선 미검증.** 새 동작은 기본 off이며 이전 결과와 합산하지 않는다.
실행 소스는 새 큐 `20261015-selfmap6-safety-smooth.json`의 `source_sha`로 고정한다.

## 원본에서 확인한 원인

원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/selfmap5-smooth-93551-cfbab2af/raw/`.
운영 정정: `outputs/e2e18-admin/gcp-reports/selfmap5-cfbab2af.json`과 같은 이름의 `-ops/`.
아래 코드 줄은 **기준 cfbab2af**의 줄이며, GT는 오차 평가에만 사용했다.

| frame 254, t=26.6 / 경과 25.3초 | 수치 |
|---|---|
| ORB 제안 | features 69, matches 13, inliers 8; `visual_relocalized` |
| innovation | xy 0.02426 m, yaw +44.278812°, Mahalanobis 11.239333, NIS 126.322595 > 9 |
| GT 기준 보정 전 → 후 | xy 0.018645 → 0.038030 m, yaw +0.814320 → +45.093132°: **틀린 보정** |
| PF (별도 정적 등록 층) | xy 오차 1.008393 m, yaw +2.170786°; raw σ xy 0.062045 m, yaw 1.661570° |
| PF/선 증거 | PF resolved=true·cluster mass=1, feature_count=4; sweep 밖, buffer=0, 지지 선/축=0, 등록/확인=0 |

- `natural_floor_slam.py:245–249`의 global 맞춤이 제안했다. `attempt`의 최소 12는 입력 쌍 수 검사이며 최종 inlier 8/13은 일반 RANSAC 최소 6·비율 .60을 통과한다(`:230`, `:164–174`). 실제 대응점/해당 RGB가 없어 어떤 바둑판 점이 서로 잘못 대응했는지는 미확인이다.
- `natural_floor_slam.py:319–328`은 자세·특징점·keyframe을 먼저 갱신한다. 이후 `self_map_integration.py:371–407`에서 S1은 **11σ를 정상 검출했지만 거부하지 않고 `rebuild_required`만 켰다**. 정적 경로도 `:372–377`에서 먼저 덮어쓴 뒤 같은 검사를 받는다. 이번 정적 등록은 **0/576회**이므로 44°가 정적 보정이었다는 설명은 틀리다.
- 마지막 시각 앵커 frame 241은 이미 `pose_uncertain`로 미삽입이었다. 저장 지도 218개는 frame 237에서 끝나므로 앵커 뒤 재분배할 command_only 기록이 **0개**, 누적 명령 이동도 **0 m**다. `selfmap5_revision.py:51–57`은 거리 비례 가중치의 분모가 0인 것을 거부한다. 44°를 이전 시각 앵커들로 임의 분배할 근거가 없다.
- t=26.6/31.6의 재구성 2회는 모두 `zero_command_distance`, 커밋 0. `self_map_integration.py:304`의 성공 경로만 격리를 해제하고 실패 롤백은 없었다. 복구는 t=25.1에 시작했으며, t=58.7 시도 3에 진입한 뒤 t=58.8(경과 57.5초, 복구 후 33.7초)에 `attempts > 2`로 HOST_ERROR다(`self_map_executor.py:125–138`). 80초 시한 만료가 아니다.
- 앞서 frame 238부터 `pose_uncertain`가 있었다. frame 254 예측 yaw σ는 5.125155°로 삽입 상한 5°를 넘는다. 롤백은 이 불확실성을 인위적으로 줄이지 않는다. 이 문제와 PF의 틀린 모드는 실제 후속 관측에서 별도 확인해야 한다.

영상 검토: `selfmap5-cfbab2af-ops/selfmap5-smooth-93551-cfbab2af-montage.jpg`의 **frame 1/116/231/346/461/576 (경과 0/11.5/23/34.5/46/57.5초)** 6장을 직접 봤다. 단독 활성 r3이며 동료는 먼 문 너머에 보이고 같은 자리 접근·직접 가로막음은 보이지 않는다. 벽/반복 바닥/구역 표지가 pan·몸 회전에 따라 바뀐다. top·동료 카메라는 없다. 회수된 원본 JPEG는 **6/576장**이고 frame 254는 없다.
회수 RGB 선을 GT에 투영한 별도 평가에서, 가까운 frame 231의 같은 hue 최근접 지도 선 끝점 오차는 **.359/.040/.348 m**, 법선 오차 **.82/1.76/64.81°**다. frame 254의 4개 feature 종류·대응은 미저장이라 확정하지 않는다. PF 오차를 ORB 보정의 직접 원인으로 단정하지 않는다.

## 수정 — `--correction-safety selfmap6_correction_safety_v1`

- 기존 recovery·revision·multiframe 옵션을 함께 명시해야 켜진다. ORB와 정적 자세 제안을 **같은 pre-mutation 게이트**로 보낸다. 거부 시 자세는 예측 상태를 유지하며 특징점 갱신·추가·keyframe 생성·bootstrap 점 추가를 하지 않는다. 고정 PR496 코어 파일은 그대로 보존하고 subclass의 `_fit` 경계에서 심사한다.
- `dᵀ(P+R)⁻¹d <= 9`만 즉시 채택한다. 9는 **3차원 타원의 반지름 3σ 문턱**이며 3 DOF의 99.73% χ² 분위수라는 뜻이 아니다. 상관 공분산·각 감싸기·특이 축 검사는 기존 S1 수식을 재사용한다. P+R은 보수적 envelope이며 통계적으로 보정된 posterior라고 주장하지 않는다.
- 큰 제안은 5초 창에서 **연속 3회**, 간격 ≥.5초, 각 확인 간 광학 방향 ≥10° 또는 이동 ≥.1 m, 서로 겹치지 않는 대응 지도 ID를 요구한다. 프레임 반복·같은 점 반복은 확인이 아니다. 최대 8개의 서로 다른 SE(2) 보정 가설을 보류하고 경쟁 가설이 있으면 채택하지 않는다. 이 조건은 독립성의 보수적 대용이며 통계적 IID 증명은 아니다. 원장에 P/R/NIS·출처·확인 수·가설 수·대응 ID·시점을 남긴다.
- 확인된 큰 보정을 적용할 때만 마지막 일관 bank/자세/keyframe/등록 앵커를 저장한다. 재구성 **실패 2회 또는 10 SIM초**가 되면 기존 지도를 보존하고 bank/앵커를 복구한다. 그동안 허용된 이동 추정을 전파해 현재 시각으로 돌아오며, 완료 인증·공분산 축소는 하지 않는다. 시각 갱신이 없어도 시한을 검사한다. 실행기의 이전 복구 타이머·시도·목표도 초기화해 계속 관측/계획한다. 새 에피소드의 재구성 예산은 별도다.
- S2는 PF 밖에서도 누적 선의 독립 법선 쌍을 정적 지도 전체의 같은 hue·유향 선 쌍에 맞춰 후보를 만든다. **모든 버퍼 선**의 유한 끝점·법선·공분산 잔차를 검증하고, 분리된 후보 2개 이상이면 등록·보정을 거부한다. 2개에서 탐색을 중단하므로 count=2는 하한이다. 유일 후보가 PF와 .15 m/10° 안에서 일치해야 기존 새 장면 3회 확인으로 갈 수 있다. PF가 한 모드로 붕괴해도 다른 반복 방을 탐색한다. 정적 큰 보정 확인에는 버퍼 전체 ID가 아닌 **현재 관측이 지지한 ID**만 쓴다.

## 재생·시험·미확인

`scripts/analyze_selfmap6.py`는 **576/576 trace의 저장 제안 97개**를 재생한다. 정책 계산이 끝난 뒤 별도 함수가 GT를 열어 점수만 계산한다. frame 254의 11.239333σ/44.278812°는 거부된다. 별도 **강제 기존 격리 분기**에서 실패 영수증 2개를 재생하면 t=31.7(경과 **30.4초**, 격리 후 **5.1초**)에 롤백 해제 판정이 난다. 실제 selfmap6에서는 최초 제안을 거부하므로 이 격리가 생기지 않는다.

고정 제안의 이후 자세/특징점은 원래 오류에 영향받았으므로 폐루프 개선을 주장하지 않는다. 전체 RGB·대응점 bank 재생, 실제 전체 sweep의 모호성 검사, PF 편향 해결과 GCP first30/180초 성공은 미검증이다. raw·구현·재생·시험 해시는 [selfmap6-summary.json](selfmap6-summary.json)에 있다. 관련 5파일 최종 **73 passed** (유일 모드 채택·반복 모드 거부 모두 포함); pytest는 동시 1개다. Mac 물리·렌더·학습·모델 호출과 원격 서버 접속은 0회다.

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.analyze_selfmap6 \
  --raw /Users/changmin/projects/ugrp/outputs/gcp1-runs/selfmap5-smooth-93551-cfbab2af/raw \
  --images /Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/selfmap5-cfbab2af-ops/frames-selfmap5-smooth-93551-cfbab2af \
  --output /Users/changmin/projects/ugrp/outputs/selfmap6-analysis/NEW.json
```

새 큐: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-selfmap6-safety-smooth.json`.
smooth first30(seed93560) → 180초-a(93561) → 180초-b(93562), **직렬·매번 원본 검토**. 모든 승인·ready·enabled·execute·자동 승격 플래그 false이고 명령에도 `--execute`를 넣지 않는다. 로컬 기존 큐의 정확한 seed 충돌은 없었으며 원격 이력·GCP 비용/8시간/유휴20분·용량·속도는 운영자가 실행 전에 확인해야 한다. 기존 큐는 수정하지 않는다. 질감은 #511이 아직 OPEN이므로 포함하지 않으며 병합·통합 후 별도 새 SHA/큐가 필요하다.

## 표준 방법 확인 범위 (수정 전 웹 열람)

- [robot_localization 공식 FilterBase](https://github.com/cra-ros-pkg/robot_localization/blob/rolling-devel/src/filter_base.cpp#L396): Mahalanobis 제곱을 n_sigmas²와 비교해 측정을 거부하는 코드를 직접 확인했다. 같은 원리이며 소스를 복사하지 않았다.
- [ORB-SLAM3 공식 Optimizer](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/Optimizer.cc): χ² 잔차 분류·outlier 제외를 확인했다. [LoopClosing](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/LoopClosing.cc#L335)는 기하 검증을 후속 keyframe에서 반복하며 확인 3회를 요구한다. 우리의 광학/대응 ID 조건은 이 코드와 동일한 알고리즘이 아닌 추가 보수 조건이다.
- [Hsiao 외, ARAS (IROS 2020), CMU 공식 초록](https://publications.ri.cmu.edu/aras-ambiguity-aware-robust-active-slam-based-on-multi-hypothesis-state-and-map-estimations): 모호할 때 여러 가설을 유지·관측으로 줄이는 근거를 확인했다. 본문·ARAS 구현을 재현했다는 주장은 하지 않는다. 이전 로컬 분석 `relocalization-carry5-selfmap4/report.md` 4절의 반복 방 PF 과신 경고와도 구분해 읽었다.
