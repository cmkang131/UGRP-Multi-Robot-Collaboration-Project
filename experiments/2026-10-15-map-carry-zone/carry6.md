# carry6 — rank를 따지는 재관측과 trim yaw 상수 후보

기준 carry5 `c6d2f5a436da4822d1c05d288604d2e542d43c82`, PR #505.
C1 `carry5_rank_aware_views_v1`, C2 `carry5_trim_yaw_calibration_v1`은 모두 **기본 off**다.
새 프로필·결과는 carry5 및 이전 결과와 합산하지 않는다. 저장 원장 수치 재생과
오프라인 회귀만 했으며 새 시뮬레이션·렌더·학습·모델 호출·원격 서버 접속·weld는 없다.

## 근거와 변경

사용자 지정 Claude 보고서 `outputs/e2e18-admin/analysis/relocalization-carry5-selfmap4/report.md`
3절 및 같은 디렉터리의 carry5 분석 스크립트 4개·로그 3개를 먼저 읽었다.
93240은 남쪽 재관측 3장이 모두 거부됐고, 2·3번째 장면의 잘못된 보정을 거부한 것은 옳았다.
원본 보고서 출처·원장의 위치와 해시는 `summary-carry6.json`, `carry6-replay.json`에 보존한다.

- C1: 후보 heading마다 최대 3개 pan의 모든 조합을 검사한다. 공분산 Cholesky의
  각 축 {−2σ, 0, +2σ}를 조합한 **27개** 자세마다 네 화면 경계에서 **100px** 이상
  여백이 있는 예측 특징만 정보 행렬에 넣는다. 모든 표본의 최소 고유값 **≥100**을
  요구한다(좌표 단위 m/rad의 DEV 가정; 보정된 확률·일반 관문 기준 아님).
  pan 조합이 미달이면 몸 +90°/−90°/180° 후보를 평가한다. 모두 미달이면
  `robust_feasible=false`와 함께 가장 나은 탐색용 몸 회전을 고른다. 미달을 성공으로 바꾸지 않는다.
- 기존 `fix_acceptance`의 full-fix 판정식과 문턱을 유지했다. 거부된 rank 2 중
  inlier≥0.8, innovation χ²≤11.345, 정보 증가≥0.05인 것만 관측 행의 SVD 부분공간에
  투영한다. null 방향 이동은 0, 그 분산은 이전 값 그대로 남긴다. 부분 보정은
  `rgb_fixes`·마지막 완전 fix 시각·누적 발행 거리/회전을 초기화하지 않는다.
  이미 포함한 예산을 중복 가산하지 않고 이후 명령 오차를 추가한다.
- 부분 보정 후 새 자세·불확실성으로 다시 계획한다. 한 시도에서 부분 관측 3회면
  다시 몸을 돌리는 다음 복구 시도로 넘어간다. full fix가 없으면 한 번 만에 종료하지 않고
  기존 총 **12회** 한도에서 +90°/−90°/180° 재시도를 한다. 자세·장애물 트랙의 좌표 보정도 함께 반영한다.
- C2: 혼합 이동에서 바퀴 pulse 시간 차가 만드는 yaw만 고정 상수로 곱한다.
  순수 몸 회전·이동량·relay 상태는 기존 공용 모델을 따른다. 로봇당 1회 적분 결과를
  지도·상대 기억·lookback에서 공유한다. 온라인 GT 입력은 없다.

## 93240 저장 원장 재생

`python -m scripts.audit_solo_carry6` → `carry6-replay.json`.
원장 171개 명령 구간(t=1.3–18.4), 정적 지도, 실제 첫 바닥 선 검출을 사용했다.
계획에는 자기 추정 자세와 예산만 주고, GT는 계획 완료 뒤 평가에만 썼다.

| 항목 | carry5 | carry6 후보 |
|---|---:|---:|
| 평가 진실 자세에서 100px 여백의 x 법선 지형지물 포함 시점 | 0/3 | **2/3** |
| 시점 | 몸 0°, pan −90/−60/−45° | 몸 +90°, pan −60/+45/+60° |
| 같은 100px 조건의 진실 자세 정보 행렬 최소 고유값 | 0 | **0** |
| 27개 표본 중 최소 고유값≥100 | 미검사 | **1/27** |

**강건한 full-rank 조합은 아직 없다.** 현재 고정 카메라 자세에서 100px 조건을 만족하는
후보는 진실 자세에서도 주로 `pickup:e3`만 본다. x 법선 가시성은 개선됐지만 전체 SE(2)
관측·검출·완전 fix·운반 완주는 입증하지 못했다. 카메라/FOV를 바꾸거나 여백을 낮추지 않았다.
오프라인 투영은 핀홀/FK/정적 가림 예측이며 새 픽셀·물리·검출 성공률이 아니다.

실제 첫 검출의 격자 갱신을 다시 계산하면 full fix는 계속 거부되고,
부분 이동은 **(0, +0.20106m, +10.1653°)**다. x σ **0.401973m 유지**,
y σ 0.100307m, yaw σ 4.71165°이며 fix 수는 증가하지 않는다.
원래 2·3번째의 inlier 0.589/0.755는 부분 수용 조건도 통과하지 않는다.

## C2 보정 자료와 별도 검증

`carry6-trim-calibration.json`: scale **0.7569222672**.
보정 자료는 **93220/870c0c59, t=1.3–18.4**만 사용하고,
검증 자료는 **93240/c6d2f5a4, 같은 시각 구간**으로 분리했다.
GT의 총 yaw 변화에서 비-trim 예측 yaw를 빼고 trim 예측 합으로 나눈 상수다.
두 실행 각각의 원장·GT 파일 전체 SHA-256은 replay JSON에 있다.

| 자료 | 기존 예측 yaw 변화 | 보정 후 | GT 변화 | 절대 yaw 오차 |
|---|---:|---:|---:|---:|
| 보정 93220 | +60.206° | +45.571° | +45.571° | 14.635°→0° (적합 자료) |
| 검증 93240 | −11.029° | −8.348° | +0.787° | **11.816°→9.135°** |

별도 실행의 회고 검증이며, 알려진 실패 자료이고 동일 지도/작업이다.
블라인드·전향 일반화 검증이나 UMBmark 정사각형 양방향 주행을 수행한 것은 아니다.
잔여 오차가 커서 **C2는 새 GCP 계획에서도 off**로 보류한다.

공용 모델은 이미 병합된 **01703ed2790dadad666e53d1b276b97f2b510bda**의 relay+확인된 감쇠다.
PR #510 **7b223e30b2a4d5044641ce23ca502bf82d176092**는 GitHub에서 OPEN(미병합)으로 확인했다.
그 접촉 손실/관성 모델은 이 소스·프로필에 **미포함**이다. 보정 상수는 현재
`harness/drive_model.py` 전체 해시에도 고정하며 모델 파일이 달라지면 거부한다.
#510 모델을 쓰는 프로필로 옮길 때 별도 보정·검증이 필요하다.

## 검증과 실행 대기열

관련 8개 시험 파일만 단일 pytest 프로세스로 실행해 **123 passed in 50.50s**를 확인했다. 최종 수치는
`offline-tests-carry6.txt`, 최초 실패도 `offline-tests-carry6-initial.txt`에 보존한다.
최초 실패는 계획 생성과 시험 읽기의 순서 경합(JSON 빈 파일)이었고, 계획 생성 완료 뒤 재실행했다.
저장 검출 기반 부분 보정, 나쁜 inlier/rank3/NaN 거부, 27개 표본, 몸 후보,
12회 재시도, 실제 teacher 재진입, 부분 보정 뒤 재계획/3관측 한도,
상수 적분 공유·순수 회전 유지·프로필 해시 거부·구형 off 회귀를 검사한다.

`diagnostic-plan-v6.json`: **93240 재현 1 + 새 시드 93260–93266 7**, 4색 각2회.
새 시드 로컬 등록부·기존 vm3 대기열 충돌은 0이다(93240은 명시적 재현 예외).
원격 미사용은 접속 금지에 따라 미확인이다. 기존 큐는 수정하지 않는다.
C1만 명시적으로 켰고 C2는 껐다. 큐는 최종 커밋 후
`outputs/e2e18-admin/vm3-queue/20261015-solo-carry-<carry6 SHA8>.json`으로 새로 만든다.
root·coordinator·run·stage의 `approved/enabled/ready/stage_ready`는 **모두 false**다.
1개 실행 회수·검토 뒤 나머지7 직렬이라는 단계 장벽을 유지한다.
제출·승인·비용/디스크·첫30초·검토 영상·VM 종료는 이번 작업에서 미수행이다.
강건한 조합이 없는 탐색 계획이라는 한계를 실행자가 확인해야 한다.

## 참고 자료 — 출처와 웹 확인 범위

- Claude 원인 분석: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/relocalization-carry5-selfmap4/report.md` §3,
  `scripts/carry5_{view_geometry,camera_projection,odometry_decomposition,timeseries}.py`, `logs/carry5_*.txt`.
  로컬 원문 확인; 외부 출판물·독립 성능 검증으로 취급하지 않는다. 보고서가 인용한 다른 논문 전체는 **웹 미확인**이다.
- [Fox, Burgard, Thrun, Active Markov Localization for Mobile Robots (1998)](https://publications.ri.cmu.edu/active-markov-localization-for-mobile-robots):
  CMU RI 공식 서지·초록을 웹에서 확인했다. 운동/센서 방향을 능동 선택한다는 연결만 사용한다. 논문 전체 구현·성능 재현 아님.
- [Borenstein & Feng, Measurement and Correction of Systematic Odometry Errors in Mobile Robots (1996)](https://ieeexplore.ieee.org/abstract/document/544770/):
  출판사 검색 결과에서 제목·초록·12(6):869–880 확인, 본문 URL 직접 열람은 418로 **미확인**.
  [대학 보관 PDF](https://web.cecs.pdx.edu/~mperkows/CLASS_479/S2006/Paper-correction-odometry-error.pdf)는 접근되지만
  도구의 본문 텍스트 추출이 없어 절차 상세는 **미확인**이다. 체계적 오차를 오프라인 상수로 보정한다는 취지만 참고했다.
