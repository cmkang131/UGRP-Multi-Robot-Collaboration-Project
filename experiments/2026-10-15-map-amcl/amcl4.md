# AMCL 기록 4차 — 표준 갱신 프로필·운동 잡음 감사, 실행 보류

기준 `e45eaba342422041d9c9da514c972e7b1bb25649`, `claude/map-amcl`, PR #507.
**목표 미달 / not-ready.** 새 실제 기록 첫30 wall/SIM ≤6.0을 뒷받침하는 재생 결과를 확보하지 못했다. 새 프로필을 채택하지 않았고 새 기록은 0회다. 원격 접속·Mac 시뮬레이션·카메라 렌더·모델 호출은 모두 0이다.

## 먼저 확인한 두 제약

1. 실제 기록기는 `scripts/record_map_amcl.py → e2e_live_mapping.Robot → GoalRoute`의 자기지도 제어기다. `harness/map_amcl.py`의 정적 지도 AMCL은 **사후 비교 후보**이며 기록 제어기에 연결되지 않았다. amcl3의 49.108→39.613초는 첫3 SIM초 **기록 제어기 전체 재생**이다. 이를 AMCL 측정 모델 시간으로 부르거나 AMCL 후보의 절감률로 실제 기록 속도를 예측하면 안 된다.
2. 로컬 원본 위치는 `/Users/changmin/projects/ugrp/outputs/gcp1-runs/map-amcl-record-b2387ac1/recordings/map-amcl-record-s65101/raw`다. 프레임·명령·위치 원장, 정적 지도, 평가 궤적은 있지만, 원장에 지정된 JPEG는 **r1 0/301, r2 0/301**이다. amcl3 회수본도 같은 제한이며 검토용 합성 이미지는 원본 JPEG를 대신하지 않는다. 원격 접속 금지를 유지했다. 새 재생 CLI는 누락을 빈 관측으로 대체하지 않고 종료 코드 2와 `BLOCKED_MISSING_SAVED_RGB`를 기록했다.

## 시간 분해와 목표 예산

아래는 같은 gcp1/n4-highcpu-64의 **기존 b2387ac1 원본 첫30**이다. 새 Mac 재생 실측이 아니다. 중첩 타이머를 더하지 않았다.

| 항목 | 초 | 확인 범위 |
|---|---:|---|
| 전체 첫30 | 485.492217 | wall/SIM 16.183074, N=1 |
| 물리 진행 전체 | 62.693716 | 순수 physics step 외 tick 포함 |
| 자기 카메라 602장 전체 | 35.964223 | 렌더·인코딩·해시·디코딩·저장·원장 |
| 그중 port.capture | 34.940902 | 렌더·인코딩·해시 포함; 순수 렌더의 상한으로만 사용 |
| 평가·평가 I/O | 0.152161 | 제어 입력에 미전달 |
| 위 세 범주 밖 잔여 | 386.682117 | 제어 계산·진행 기록·디스크 검사 등 |
| 순수 렌더 / 기록기 자기지도 측정 모델 / 리샘플 단독 | 미계측 | 과거 원본에서 분리 불가 |
| 정적 지도 AMCL 후보 측정 모델 / 리샘플 | 해당 없음 | 이 기록 제어 경로에는 호출이 없음(소스 확인) |

물리·카메라·평가 비용을 유지한다는 가정이면 이미 **98.810100초, wall/SIM 3.293670**이다. ≤6.0에 남은 기타 예산은 **81.189900초**라서 잔여 386.682117초를 **79.00% 이상** 줄여야 한다. ≤3.5에는 6.189900초만 남아 **98.40% 이상** 줄여야 한다. 이는 필요 절감량 계산이며 달성 예측이 아니다.

amcl3 첫3 재생 비율 `39.612850/49.107987`을 첫30의 모든 잔여 비용에 그대로 적용해도 조건부 값은 **13.690879**다. 구간 대표성과 비용 구성이 검증되지 않은 설명용 계산이고 승인 근거가 아니다. selfmap 1대 2.574233도 카메라 수·제어 경로가 달라 이 2대 기록의 예측값으로 쓰지 않았다. 유효한 새 `predicted_wall_per_sim`은 **null**이다.

## 기본 off 새 프로필

`map_amcl.create(..., profile='off')`가 기본이다. 실제 기록기의 설정은 바꾸지 않았다. `RGBPipeline`과 `scripts.profile_map_amcl`에서 다음 후보를 명시적으로 고를 수 있다.

| 프로필 | 영상 추출 전 이동/새 시야 관문 | resample_interval | KLD 입자 범위 | 벽 점/랜드마크 상한 |
|---|---|---:|---|---|
| off (비교 기준) | 없음, 필터 내부 관문은 기존대로 | 1 | 500–2000 | 60/32 |
| amcl4_motion_v1 | 있음 | 1 | 500–2000 | 60/32 |
| amcl4_resample2_v1 | 있음 | 2 | 500–2000 | 60/32 |
| amcl4_kld250_v1 | 있음 | 1 | 250–2000 | 60/32 |
| amcl4_features30_v1 | 있음 | 1 | 500–2000 | 30/4 |
| amcl4_balanced_v1 | 있음 | 2 | 250–2000 | 30/4 |

- 기존 `update_min_d=.25m`, `update_min_a=.2rad`와 KLD를 재사용한다. 관문을 **비싼 영상 특징 추출 앞으로** 옮긴 것이 첫 후보의 변경이다. 마지막 유효 측정 이후 명령 변위를 누적하고, 매 프레임 명령 전파·보고는 유지한다. 새 카메라 시야는 기존 RGB 예외를 유지하되 0.7초 안정화 뒤 사용한다. 빈 관측은 관문을 소비하지 않으며 과거 특징을 현재 관측으로 재사용하지 않는다.
- 리샘플 주기는 프레임 수가 아닌 **수용한 측정 갱신 수**로 센다. 리샘플하지 않은 갱신에서도 정규화한 사전 가중치를 다음 likelihood에 곱한다.
- KLD는 시작 최대 2000입자와 기존 격자 0.5m/0.5m/10°를 유지한다. 최소 250 후보도 전역 미확정 분포를 처음부터 250개로 줄이지 않는다. 상한 도달 여부를 기록한다. `pf_err=.05`, `pf_z=.99`는 기존 ROS 구현 관례를 유지하며 **99% 보장이라는 뜻이 아니다**(정규 분위수 2.326과 다름).
- 특징 제한은 고르게 뽑은 likelihood 입력의 수를 제한한다. CV 검출 전체 시간이 특징 수에 비례해 줄어든다고 가정하지 않는다.
- `rgb_features`, `motion_model`, `measurement_model`, `resample`, `filter_other`, `decode_io`를 초 단위로 분리한다. nested inclusive 대신 exclusive를 합산한다. 별도 `--include-controller`는 실제 기록 제어기의 측정·리샘플·나머지를 재며 저장된 발행 명령을 적용한다. 새 닫힌 루프 주행 결과는 아니다.

6프로필 모두 동일 RGB **평가 0/2구간**, 실제 단계 시간·정확도 **null**, 채택 false다. 합성 센서 시험에서 motion 후보와 off의 매 프레임 입자·가중치·pose·공분산 일치, 빈 측정의 누적 변위 보존, resample2의 사전 가중치 보존을 확인했다. 이는 실제 저장 RGB의 정확도 검증이 아니다.

재생 도구는 최초·미수렴·실패 프레임을 제외하지 않고 절대 위치/방향 median·p95와 SE(2) 정합 지표를 함께 기록한다. 후보 비교 허용 증가량은 사전 고정한 위치 median 2cm/p95 5cm, 방향 median 2°/p95 5°이며 로봇별 모두 통과해야 한다. 상대 비열화가 절대 정확도 합격을 뜻하지 않으며, 이 자료만으로 온라인 채택하지 않는다.

## α=.2 운동 모델 점검

`scripts.audit_map_amcl_motion`이 **기존 빔 원본 40회×2대=80구간 전체**를 읽었다. search17의 기존 `command_delta(..., mode='off')` 소스 함수를 재사용했고 보정 상수·새 보정 경로는 구현하지 않았다. 원장 시각과 평가 시각을 대조했으며 GT는 증분 잔차·궤적 오차 계산에만 썼다.

현행 모델의 축별 σ는 `sqrt(.2 × (dx²+dy²+dyaw²))`다. 총 23,664전이 중 명령 변위가 0이 아닌 **10,595개**에서 위치 잔차는 1σ 내 10,398/10,595, 3σ 내 **10,595/10,595**다. 방향은 3σ 내 **10,546/10,595**다. 정지 명령 13,069전이 중 **250개**는 실제 위치 잔차가 1mm를 넘었다. 정지 명령에는 모델 분산이 0이므로 이 예외를 움직임 분모에 숨기지 않았다.

GT 이동거리 >0.5m인 동일 부분집합 **59/80구간**의 명령/GT 거리비 중앙 **1.31765276**를 재확인했다. 그러나 독립 영평균 잡음으로 공분산을 1차 전파한 누적 위치 오차는 최대축 3σ 안 **58/80**, 밖 **22/80**이다. 최대축 원형 경계는 실제 공분산 타원보다 느슨한 진단이다. 한 전이의 잡음 포괄이 지속 편향의 제거를 뜻하지 않는다. 이번 구간별 궤적 중앙 오차의 중앙 297mm·종료 오차 중앙 326mm는 사용자 참고값 393mm와 정의가 같다고 확인하지 못해 대체하지 않는다.

실제 AMCL 기록 원장도 별도로 평가했다. 위치 증분 3σ 내 **470/470**, 방향 **422/470**이고, 누적 오차는 **1/2**만 최대축 3σ 안이다. r2는 종료 위치 차 **1.2823m**, 전파 최대축 σ **0.1742m**였다. 이 값으로 물리적 원인이나 보정 상수를 단정하지 않는다. 실제 측정 갱신 시점은 RGB 부재로 모르며, 이동량 관문만 가정한 43/43(지도 기록), 983/983(빔)의 위치 잔차 3σ 포괄은 별도 가상 스케줄 진단이다.

## 검증·대기열·남은 작업

관련 4개 시험 파일 **56 passed**(10.48초). 실제 MuJoCo world/카메라를 만들지 않는 합성 비트맵·모의 센서·저장 원장 시험이다. `scripts/run_ci_tests.py`에 새 프로필과 기존 기록기 시험을 등록했다. CI 원격 결과는 별도다. 소스·원본·시험 해시는 `amcl4-validation.json`, 전체 40개 새 미제출/80구간과 기존 HOST_ERROR 분모는 `amcl4-summary.json`, α 상세는 무손실 압축·해제 검증한 `amcl4-alpha.json.zst`다.

새 큐는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-map-amcl-record-<SHA8>.json`에 생성한다. 기존 큐는 수정하지 않는다. `approved=false`, **모든 ready 계열 false**, 실행권한 false, 예측값 null과 위 산식·차단 이유를 넣는다. 첫 기록 65102 한 개 → 첫30 속도·정확도 및 전체601장 확인 → 나머지39 순서이며 자동 승격은 없다. 기록기 admission에도 오프라인 속도·정확도 증거와 첫 기록 결과/원본 manifest 해시에 묶인 정확도 검토를 별도 조건으로 추가했다.

**이 SHA는 실제 기록 속도 수정 완료 후보가 아니다.** 먼저 원본 JPEG 602장을 로컬에서 확보하고 실제 기록 제어기 병목을 재프로파일해야 한다. 그 경로의 기본 off 수정과 동일 입력 정확도 비교가 있어야 ≤6.0 예측을 만들 수 있다. AMCL 사후 비교만 빨라진 결과로 기록을 승인하지 않는다. 원격 접속을 하지 않았으므로 원격 시드·머신·예산 상태도 새로 확인하지 않았다.

## 참고 자료

- [ROS AMCL 소스](https://raw.githubusercontent.com/ros-planning/navigation/noetic-devel/amcl/src/amcl_node.cpp): `fabs(dx)>d_thresh || fabs(dy)>d_thresh || fabs(dyaw)>a_thresh`, 센서 갱신 횟수에 따른 `resample_interval`을 직접 확인했다. [laser 모델](https://raw.githubusercontent.com/ros-planning/navigation/noetic-devel/amcl/src/amcl/sensors/amcl_laser.cpp)의 `max_beams` 균등 간격 표본과 [pf.c](https://raw.githubusercontent.com/ros-planning/navigation/noetic-devel/amcl/src/amcl/pf/pf.c)의 점유 bin·입자 상하한·KLD 공식을 확인했다. ROS 레이저를 영상으로 그대로 동일시하지 않고 특징 추출·새 시야 예외는 프로젝트 어댑터로 표시한다.
- [Nav2 공식 Jazzy 설정](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/others/configuring_amcl/): update_min_d=.25, update_min_a=.2, resample_interval=1, 500–2000입자, max_beams=60 및 pf_z의 정규 분위수 의미를 확인했다.
- Fox (2003), [Adapting the Sample Size in Particle Filters Through KLD-Sampling](https://cis.temple.edu/~latecki/Courses/RobotFall07/PapersFall07/fox-ijrr-2003.pdf): §3.2, 식(14), Table 2 원문과 표 이미지를 확인했다. 입자 생성 중 점유 bin 수와 통계적 오차 한계로 필요한 수를 갱신한다. 저자의 논문을 보관한 대학 미러이며 저장 파일 해시를 남겼다. 표의 종료식 표기와 달리 본 구현은 기존 ROS의 종료·최소/최대 조건을 유지한다.
- Thrun·Burgard·Fox, *Probabilistic Robotics*, [열람본](https://roboticsjtu.github.io/CS7355/Probabilistic-Robotics-en.pdf), [저자 사이트](https://robots.stanford.edu/probabilistic-robotics/): 8장 §8.3.2 MCL, §8.3.7 KLD, Table 8.4(p.264) 및 §8.5 특징 추출의 속도/정확도 교환을 직접 확인했다. 열람본 ISBN은 9780262201629, 도서관 연도 2005·저작권 표기 2006이며 **2005 초판 인쇄본 자체는 미확인**이다. 처음 찾은 1999–2000 early draft는 2005판 근거에서 제외했다. Table 8.4 이미지는 최소 입자 수와 KLD 한계 중 어느 하나가 미달이면 계속 표본을 뽑는 `or` 조건을 확인하는 데 사용했다.

출처별 URL·열람 범위·파일 SHA-256은 `amcl4-references.json`에 있다. 논문·교재 본문은 Git에 넣지 않았다.
