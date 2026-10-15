# 자기 지도 3차 — 93510 연속 RGB의 초기화 실패와 기본 off 수정

판정: **NOT_READY_FOR_COMPLETE_MAPPING_OR_DRIVING**. 초기화의 막힌 경로는 저장 RGB에서
해소했지만, 지도 완성·새 정책의 실제 주행·GCP 실행 속도는 미검증이다.
PR #506, 브랜치 `claude/map-selfmap`, 기준 `7b5d1924624545b44bc30804701809635663130e`.
최종 수정 소스는 이 기록을 포함한 커밋이며, 재생 시에는 기준 HEAD 위 미커밋 수정이었다.
`selfmap3-summary.json`의 실행 파일 해시로 구별한다. 기준 SHA로 수정 결과를 소급하지 않는다.

## 원본과 직접 확인 범위

- GCP 원본: `gcp1:/home/ugrp/ugrp-sim/runs/selfmap-93510-7b5d1924/raw/`.
- 로컬 원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/selfmap-93510-7b5d1924/raw/`.
  기존 fetch-lite의 원장/평가 자료와 필요한 `robots/r3/rgb` 301장만 개별 회수했다.
  자기 RGB 301/301의 SHA-256을 원장과 대조했고, 두 재생의 입력 manifest 해시가 같다.
  기존 원본·감독 정지 기록은 변경하지 않았다. 이전 180초 두 실행은 미제출 상태다.
- 생성 분석: `/Users/changmin/projects/ugrp/outputs/selfmap3-analysis/`.
  프레임별 검출/실패 사유는 `diagnostic-fixed/frame-detections.json[.zst]`, 평가 전용
  가시성은 `eval-only-visibility.json[.zst]`, 비교는 `analysis-summary.json`에 있다.
- 직접 연 RGB: frame **1/31/61/91/101/121/151/181/211/225/271/301**,
  경과 **0/3/6/9/10/12/15/18/21/22.4/27/30초**(절대 SIM은 +1.3초).
  `review.jpg`로 처음·중간·끝을 확인했다. 단색 벽, 큰 반복 체크 바닥, 문 개구부,
  벽 모서리, 구역 색 표시가 팬/회전 중 달라진다. 새 물리/렌더/모델 호출은 0회다.

## 계측과 원인

| 301장 전체 검출 | 최소 / 중앙 / 최대 | 양수인 프레임 |
|---|---:|---:|
| 바닥 마스크 안 ORB 후보 | 5 / 36 / 77 | 301/301 |
| 직접 검출 벽–바닥선 segment | 0 / 1 / 4 | 291/301 |
| 바닥 관측 ray | 1349 / 2430 / 3311 | 301/301 |

ORB는 물체 종류를 붙인 지형지물 검출기가 아니다. `floor_mask_orb`는 바닥 투영 후보이고,
벽선·바닥 ray는 별도 직접 관측이다. 카메라 안정화 전 검출량과 실제 제어에 넣은 특징 수를
프레임별로 따로 적었다. 초기 3장은 안정화 대기로 제어 특징 0개이며, 전체 33장은 삽입 보류다.

첫 유효 frame 4(SIM 1.6)의 **후보 35개가 2.5 cm 간격 중복 제거 후 landmark 5개**가 된다.
이후 은행에 점을 추가하는 분기는 시각 정합 성공 안에만 있다. mutual ratio 매칭은 최대 5개인데
`min_matches=8`을 요구하므로, 다른 방향에서 후보 77개를 보아도 은행은 영구히 5개다.
결과는 bootstrap 4회, `insufficient_matches` **297/297회**, 시각 갱신 0회다.
프레임 누락이나 실제 둘러보기 누락으로 설명할 수 없는 초기화 순환 의존이다.

팬 명령은 1500→1750→2000→1750→1500→1250→1000→1250→1500이다.
기존 sweep은 절대 SIM **11.3–23.7초**에 실행했고, 명령 오도메트리 적분은
6.31615 rad(361.89°), 평가 궤적의 unwrap 회전은 **6.34812 rad(363.72°)**다.
그 뒤 영상이 다시 팬으로 바뀐다. 팬 값은 발행 pulse이며 측정 관절각이 아니다.

정답 카메라 pose·정적 벽 상자는 검출을 끝낸 **평가 함수만** 읽었다. 실제 카메라 보정,
정면 투영/FOV, 4 m 거리, 벽 상자 가림, 5 px 이상 선분 기준으로 각 프레임의 예상 벽을 계산했다.
예상 벽 물체는 **1/2/3개**, 벽–바닥선은 **1/2/4개**, 모서리는 **0/1/4개**(최소/중앙/최대)다.
시작 영상에서는 divider 1개, 문 방향에서는 divider 2개, 반대 방향에서는 외벽이 보인다.
프레임별 예상 이름/종류를 저장했다. 동적 물체·자기 몸체의 정밀 가림 및 ORB가 실제 검출할
정확한 수는 **미확인**이다. 따라서 이 수는 정적 기하상 가시성 상한이며 검출 recall 분모가 아니다.
같은 평가에서 ORB 후보 11,769개 중 1,483개 ray는 바닥보다 정적 벽에 먼저 닿는다.
바닥 마스크 후보를 전부 실제 바닥점으로 간주할 수 없다는 한계도 남는다.

`min_matches=8`은 PR #496의 `15b1768d`부터 있던 설계 기본값이다. 원본 문서·커밋에서
8이라는 숫자의 검증/문헌 근거는 찾지 못했다. 현재 정합은 바닥 투영으로 이미 미터 단위가 정해진
SE(2)이며, 두 대응점으로 후보 회전을 만들고 넓이·잔차·합의율을 검사한다. ORB-SLAM2의
3D 단안 초기화 임계값을 이 문제의 근거로 옮길 수 없다. 이번에는 **8/6/12 대응·inlier 기준,
0.60 합의율, 2.5 cm 잔차 상한/공간 spread 하한을 그대로 유지**하고 추가 관측 경로를 고쳤다.

## 수정과 입력 경계

- `bootstrap=command_prior_v1`(기본 off): frozen `natural_floor_slam.py`를 수정하지 않고
  별도 subclass가 관측 부족 시에도 명령 prior에 새 자기 RGB 특징을 추가한다.
  기존 위치/각도 불확실성 상한(0.15 m, 5°) 안에서만 추가하며, 상태는 `command_only`다.
  실제 기하 정합을 통과한 경우에만 `visual_update`로 센다.
- 같은 토글에서 시각 pose가 없어도 기존 벽–바닥선 검출기의 직접 ray를 점유 격자에 넣는다.
  ORB 특징 자체를 장애물로 넣지 않는다. held/카메라 미안정/불확실 pose/미해결 지도 재구성은
  계속 보류한다. prior 프레임·그 영향을 받은 셀을 `prior_frame_ids`/`prior_cells`로 표시한다.
  그 관측들이 과거 pose 재정합으로 해소되기 전에는 `prior_map_unverified`로 완료를 막는다.
  frontier는 불확실성 상한 안의 제안이며 실제 이동 성공이 아니다.
- prior로 만든 landmark는 독립 정답이 아니다. 시각 정합 후에도 이전 명령 공분산 전파량을
  버리지 않고 fit 공분산을 더해 보수적 envelope로 유지한다. 이는 통계적으로 보정된 posterior나
  전역 pose graph 최적화가 아니다. 시간이 길면 상한을 넘어 재관측이 필요할 수 있다.
- `initial_sweep=required_360_v1`(기본 off): 시작 팬→기존 몸 회전이 완료되기 전에는
  지도 완료 선언/이동으로 넘어가지 않는다. timeout·충돌 보류 뒤 incomplete sweep은 재시도한다.
  시작 sweep 중 지도 갱신 이벤트가 팬을 계속 재시작시키지 않게 했다. 완료 기준은 **자기 발행
  명령의 회전 적분**이며 실제 360° 보장은 새 실행 영상·평가에서 따로 확인해야 한다.
- writer의 모든 제어 입력을 `InputAudit` allowlist로 통과시켜 `result.input_audit`에
  자기 RGB/명령 전달 수, 거부 수, top/peer/정답 pose 전달 수,
  `invisible_measurements`, `held_world_reads`를 저장한다. 마지막 두 값은 result에도 둔다.
  HOST_ERROR·snapshot 저장 실패에도 감사 결과를 남긴다. 카메라/명령에 금지 필드를 주입하는
  시험은 전달 전 거부를 확인했다. 이 측정은 **writer→controller 전달 경계**이며 물리 엔진/
  평가기의 모든 메모리 읽기를 가로채는 감사는 아니다. 과거 93510의 미계측 값을 0으로 소급하지 않는다.

제어 입력은 자기 RGB·자기 발행 명령·고정 카메라 보정뿐이다. 정답/접촉/측정 관절/상부 RGB를
제어에 주지 않으며 정적 지도도 제어에 제공하지 않는다. ACT 근거리 동작은 변경하지 않았다.

## 동일 301장·동일 명령의 전후 재생

| 지표 | 기준 | 수정 |
|---|---:|---:|
| 처리 RGB | 301/301 | 301/301 |
| 시각 갱신 | 0/301 | 56/301 |
| 지도 삽입 | 0/301 | 268/301 |
| 지도 셀 | 0 | 2,010 |
| frontier 제안이 있는 프레임 | 0/301 | 152/301 |
| 마지막 계획용 raw 경계 셀 | 12 | 113 |
| 점유 IoU | 0/282 (0%) | 57/438 (13.0137%) |
| free 커버리지 | 0/2773 | 1656/2773 (59.7187%) |
| 위치 RMSE (평가 전용) | 0.022405 m | 0.022118 m |
| yaw RMSE (평가 전용) | 0.020348 rad | 0.007992 rad |
| 지도 완료 선언 | 0 | 0 |

기준의 raw 경계 12는 `current_footprint_v1`이 계획용으로만 넣은 차체 지지 영역이며,
실제 관측 frontier나 지도 셀은 0이다. 서로 다른 수를 혼동하지 않는다.
수정의 raw 경계 최댓값은 164, 최종 landmark는 122개다. 수정 후 실패 분기는
매칭 부족 238회, 강체 합의 실패 3회이고, 56회만 실제 시각 정합이다.

**제한:** 수정 지도 2,010셀 중 1,986셀에는 prior 기여가 있고, 삽입 268회 중 212회는
시각 pose 없이 삽입했다. 예측 점유 213셀 중 94셀은 평가 지도 범위 밖이며 벽 RMSE는
0.1470 m다. 초기화가 진행된다는 근거이지 정확한 완성 지도/주행 안전 근거가 아니다.
저장 행동을 고정한 재생이라 새 frontier 선택에 따른 카메라·행동 변화와 실행 속도는 검증하지 않았다.
낮은 IoU, 벽을 바닥으로 투영하는 후보, prior에 의존하는 지도의 장시간 드리프트가 남는다.

모든 시도는 요약 JSON에 남긴다: 기준 재생 완료, 첫 후보 재생 301장 처리 뒤
`prior_cells`의 NumPy 정수 직렬화 HOST_ERROR, 수정 재생 완료.
첫 비교 분석은 재생 저장 완료 전 실행해 입력 map 파일이 없어 HOST_ERROR였고,
완료 후 `diagnostic-fixed`에서 다시 계산했다. 실패 디렉터리는 보존했다.
관련 시험은 세 파일의 최종 합계 **36 passed**(integration 14, executor 16, offline 6).
최초 묶음은 34 passed/1 failed였고, 실패는 incomplete-sweep 시험 fixture가 기존
`issued_twist` 계약과 달리 hold를 반환한 것이었다. fixture 수정 후 해당 파일만 재실행했고,
writer 오류 보존 시험 추가 후 해당 파일 16 passed를 확인했다. 전체 로컬 시험은 실행하지 않았다.

## 승인 전 실행 준비

새 대기열은 `outputs/e2e18-admin/vm3-queue/20261015-selfmap-<수정 SHA8>.json`이다.
`approved=false`, `ready=false`, `runs_enabled=false`, 각 run `enabled/execute=false`이며
자동 실행/승격은 없다. 시드 **93520/93521/93522**, **30/180/180 SIM초**, 동시 1이다.
로컬 소스·관련 원격 ref 7개·기존 대기열·gcp1 보관 run 디렉터리 712개에서 이름 중복 0을 확인했다.
원격 디렉터리 이름 밖의 숨은/삭제 이력까지 확인한 것은 아니므로 제출 직전 다시 대조한다.
GCP n4-highcpu-64, 프로젝트 `ugrp-act-train-1014`; 디스크 예약 192/384/384 MiB, 합계 960 MiB.
실제 머신/전체 여유·타 승인 작업 예약·예산 정지 상태는 제출 시 운영자가 확인한다.
첫 30초에서 새 입력 감사, 전량 RGB, 실제 회전, 지도 오삽입·위치 오차·속도를 검토한 뒤에만
나머지 두 실행을 별도 승인한다. 낮은 IoU를 완성으로 승격하지 않는다. 8시간 STOP·유휴 20분·
예산 정지를 유지하며 발동 시 다른 호스트로 자동 이전하지 않는다.

재현 명령(물리/렌더 없음):

```sh
python -m scripts.offline_self_map replay --raw RAW --images RAW --robot r3 \
  --output NEW_REPLAY --motion-model s2_pulse_v122_rotL_v1 \
  --self-map-integration natural_floor_frontier_v1 --pose-rebuild refit_history_v1 \
  --navigation-support current_footprint_v1 --bootstrap command_prior_v1
python -m scripts.analyze_self_map_bootstrap --raw RAW --output NEW_ANALYSIS \
  --replay BEFORE --replay AFTER
```

## 참고 자료

2026-10-15에 아래 공식 소스/저자 자료를 열람했다. 적용 부분은 위 수정 절의 설계 판단이며,
해당 SLAM 패키지를 통째로 도입하거나 검증 수준을 이어받았다는 뜻이 아니다.

- [ORB-SLAM2 Tracking.cc](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Tracking.cc):
  단안 초기화는 초기/현재 특징이 100개를 넘고 매칭이 최소 100개여야 다음 단계로 간다.
  [Initializer.cc](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Initializer.cc)는
  H/F 재구성에 1° 시차와 최소 삼각화 50을 전달하고, 양의 깊이·재투영·모호성·합의 비율도
  검사한다. F는 max(90% inliers, 50), H는 >50 및 >90% 등을 요구한다.
  이는 미지 3D 점/두 시점 초기화 조건으로, 현재 평면 미터 SE(2)의 최소 8개 근거가 아니다.
- [Cartographer 2D local trajectory builder](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/local_trajectory_builder_2d.cc):
  첫 pose를 identity로 초기화하고 submap이 비었으면 scan match가 pose prediction을 반환한다.
  [공식 알고리즘 안내](https://google-cartographer-ros.readthedocs.io/en/latest/algo_walkthrough.html)는
  pose extrapolator의 예측으로 scan matching/삽입을 시작하고 odometry를 사용할 수 있음을 설명한다.
  여기서는 LiDAR 대신 보정된 RGB 벽/바닥 ray와 **명령** 오도메트리라 오차 특성이 다르다.
- [Seegmiller & Wettergreen, IROS 2011](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf):
  저자 공개 원문에서 바닥 카메라 optical flow, 그림자 경계 회피, 불일치 이동 outlier 제거를 확인했다.
  [Zienkiewicz & Davison, JFR 2015](https://onlinelibrary.wiley.com/doi/abs/10.1002/rob.21547):
  저자/출판사 초록에서 평면 바닥 전체 texture의 dense alignment를 확인했다.
  sparse feature가 적을 때의 대안이나, 무늬가 전혀 없는 표면의 관측 가능성을 보장하지 않는다.
  JFR 전문 및 우리 카메라에서의 dense alignment 성능은 미확인이다.
- 직접 벽–바닥선 관측은 기존 `active_wall_vision.observe` 및
  `experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py`를 재사용했다.
  바닥 평면과 영상 수직 변화/수평 지속성으로 관측을 만들며 실행 중 벽의 정답 높이나 위치는 받지 않는다.
