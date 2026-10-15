# release24 — 빔 축 추정 융합·재관측 (2026-10-15)

release23 실행 `8d24a525`·기록 `f3e3db02` 위의 새 교사다. 이전 release21/23 결과와 합산하지 않는다. 학습 RGB OFF, weld OFF, 카메라/FOV, 4cm 수용 문턱, 18° 누적 yaw cap, 180 SIM초, 3회 보정 상한을 유지한다.

## 수정 전 gcp1 원본 분포

`release24-baseline-rejections.json`에 거부표·funnel·재현 명령·원본 표 경로/해시를 보존했다. 원본 manifest는 VM에 유지하고 Mac에는 축약표만 둔다. release21 A/B 80회 194쌍은 상관된 관측이다. release23 DEV1/2/3은 각각 별도이며 중단 trace도 오차 분석에만 포함했다. 성공률에 복구 집계하지 않는다.

| 집단 | 동시 보고 쌍 | r1 오차 평균/SD (°) | r2 오차 평균/SD (°) | 두 보고 절대 차 p95 (°) | 10° 발동 중 정답상 불필요 |
|---|---:|---:|---:|---:|---:|
| release21 A40/B40 |194|0.150/0.870|0.076/0.838|2.315|발동0, 비율 정의 불가|
| release23 DEV1 |18|0.641/0.581|−0.490/1.431|6.447|1/1|
| release23 DEV2 중단 |1|0.314/0|−0.197/0|0.511|발동0|
| release23 DEV3 |18|0.241/1.215|−0.543/1.439|6.447|1/1|

거부 종료는 baseline에서 cap_end2, DEV1/2 HOST_ERROR/감독중단11, DEV3 회차 상한1이다. 앞 두 결함은 release23에서 수정됐고 이번 수정 대상은 DEV3의 축 추정 불일치다. 수치 관문 발동과 에피소드 실패를 합산하지 않는다.

10°는 `14ddb6ad33b7a86ad68eee0e5c98762a8771e14c`의 `release_global_observation.py`에 처음 들어갔다. 주석은 축 방향 운반 가정만 설명한다. 관련 release 기록·상수 감사·초기 diff에서 실기 사양/분포/문헌 유도는 발견하지 못했다. **근거 미확인인 기존 값**으로 표시하고 변경하지 않는다. 분포로 맞춘 후보는 판정 방법과 일관성 문턱이며 물리 허용각을 늘리지 않는다.

## 표준 방법과 적용 범위

- Noack et al., *Decentralized Data Fusion with Inverse Covariance Intersection*, Automatica 2017, [저자 공개 원문](https://isas.iar.kit.edu/pdf/Automatica17_Noack.pdf), 1–3절과 CI 식(10): 상관을 모를 때 독립 가정의 공분산 축소를 피한다. 같은 두 센서의 CI 혼합계수 1/2를 사용한 정보 가중 평균을 축 각도 tangent 공간(180° wrap)에 그대로 적용한다. release21 원본의 편향 포함 MSE r1=.7802676717621957, r2=.7079446501165835 deg²를 고정한다. 경험 MSE는 보증된 공분산 상한이 아니므로 CI의 이론적 보증을 우리 데이터에 주장하지 않는다. 평균 편향 자체를 빼지 않는다.
- ROS `robot_localization` [공식 FilterBase 원문](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/rolling-devel/src/filter_base.cpp)의 `checkMahalanobisThreshold`: 혁신의 불일치를 행동/갱신 전에 거부하는 표준 구조를 적용한다. 여기서는 보증된 온라인 공분산이 없으므로 임의 sigma 배율을 복사하지 않고, **release21 194쌍의 절대 차 higher p95=2.3145519571195257°**를 경험 게이트로 사용한다. 정규분포 검정의 유의수준을 주장하지 않는다. 재관측은 기존 자기 카메라 3방향 실제 pan sweep이며 같은 회차 번호만 재전송하지 않는다.
- 히스테리시스는 선택하지 않았다. 이 실패는 반복 경계 진동의 증거가 없고 첫 잘못된 회차가 비싸다. 새 히스테리시스 상수를 만들 근거가 없다. 짧은 들기/회전 경로도 음성 안전 검증이 없으므로 이번 두 후보에 넣지 않는다.

자료 열람: 2026-10-15. CI와 혁신 게이트의 표준 원칙을 적용하며, 우리 경험 오차의 백분위 값은 위 원본에서 따로 산출했다.

## 기본 OFF 후보와 비교 계획

1. `axis_fusion=axis_fusion_v1`: 같은 epoch·SIM시각의 기존 PairReleaseCode scalar 축 두 개를 융합하고 동일10°로 판단한다. 각자 margin·lateral interval은 자신의 geometry로 계산하며 융합각으로 끝 위치를 다시 만들지 않는다. 기존 margin lower bound·sweep·regrasp·안전 관문을 보존한다.
2. 위와 함께 `axis_disagree_reobserve=axis_disagree_reobserve_v1`: 차이가 경험 p95를 넘으면 행동 전에 새 RGB pan sweep을 수행한다. 변화 없는 선택 3회 연속이면 공통 규칙에 따라 명시적 사유로 중단한다. 기존 전체 cap·회차 cap은 초기화하지 않는다.

새 후보는 `compute_budget_v1` ON, 같은 여섯 장면(110622 A/B, 88639 A/B, 110618 A/B)을 같은 대기열에 둔다. 후보별 결과는 따로 n/6으로 보고하며 최대3라운드다. 소유동시≤6·gcp1전체≤40. source 커밋 후 실행하고 원인 확인 시 같은 결함의 소유 실행/대기는 즉시 정지한다. 학습·모델 호출은0. 관문 A40/B40는 선택 후보6/6·실패 seed 해결·감사0·프레임 검토 뒤에만 미승인으로 만든다.

실패 RGB 버퍼는 기본 ON인 기록 전용 옵션 `failure_rgb_recording=own_rgb_last10_10hz_v1`이다. 기존0.1 SIM초 루프에서 자기 JPEG만 저장하고 실패/중단 시 마지막10초를 디스크에 남기며 바이트/해시/범위를 기록한다. 제어/학습 입력으로 읽지 않는다. 성공 때 파일을 쓰지 않는다.

## 수정 전 영상 직접 검토

VM에서 ffmpeg으로4배속 동영상(각≤8MiB)을 만들고 ffprobe로 검증했다. Mac 화면 앱은 열지 않았다. Mac 경로 `outputs/e2e18-admin/playback/release24-baseline/`. 전체2Hz 프레임 띠6장과 마지막10초10Hz 띠2장을 직접 읽었다. 원본은1Hz라 중복 프레임을 명시했으며 빠른 진동 검증으로 세지 않는다. 두 실행 모두 overview 원본0장이므로 검은 칸에 unavailable을 표시했다. 없는 overview를 렌더링/발명하지 않았다.

- 실패 `r23d3-02-8d24a525`: release 상대0–157초 전체315시점. 0–6초 들린 빔이 시야 대부분, 7–14초 내려놓기·팬, 15–24초 양측 반대색 끝 접근, 25–51초 들기/이동, 52–72초 내려놓기/재접근, 73–98초 들기/이동, 99–119초 재관측/접근, 120–146초 추가 들기/이동, 147–157초 내려놓기·팬 뒤 종료. 마지막10초101시점도 확인했다. 같은 끝 접근·상호 막힘은 보이지 않았다. 추가 회차의 존재는 보이지만 축 각도 수치는 영상만으로 계측하지 않고 원본 원장/평가로 대조한다.
- 성공 `r23d3-04-8d24a525`: release 상대0–74초 전체149시점. 0–6초 유지, 7–19초 내려놓기/둘러보기, 20–28초 양측 자기 끝 접근, 29–57초 들기/이동, 58–70초 내려놓기/둘러보기, 71–74초 물러나 종료. 양측 청록/파랑 끝 유지.

듬성한 프레임과 다른 점은 동작 반복의 순서와 각 구간 길이를 확인할 수 있었다는 점이다. 1Hz 한계 때문에 진동 부재를 확정하지 않는다.

## 실행 전 비물리 검증

관련 회귀126개 중125개 통과, 신규 OFF 재생 시험은 fixture가 대체한 subprocess 경로 때문에 실패했다. 검증용 원본 읽기를 기존 release23 시험과 같은 실제 subprocess.run으로 고친 뒤 신규10개 모두 통과했다. 제어 코드 실패가 아니며 실패 기록도 보존한다. Mac 물리/렌더/모델 호출0.

## Round1 중단·세 번째 후보

실행 `b20bb52a0eddf3aca0034444661b434a07c51c0d`: fusion 5/6, gated는 성공2·HOST_ERROR1·감독중단3이다. 합산하지 않는다. 새 원인은 `release24-round1-rejections.json`에 기록했다. fusion의110622 B는120.6초에 융합−9.034°로 불필요한 축 회차를 피했지만169.7초에 r1 lateral .0355826m가4cm보다4.4mm 작다고 추정하여 네 번째 옆이동을 요구했다. 실제 빔은 평가상 영역 안(최소 end-center 여유 .11805m)이나 이를 제어로 반환하거나 성공으로 덮지 않았다.

해당 실패 release0–159.6초2Hz 전체320시점·149.6–159.6초10Hz101시점, 성공110618 A의0–74초 전체149시점을 직접 봤다. 반대 색 끝 유지, 같은 끝·상호 막힘 없음. 실패 마지막10초는 진짜10Hz이며149.6–151초 팬/시선 변화,151–154초 끝 가까이 접근·물러남,154–157초 재관측,158–159.6초 끝을 본 채 대기했다. 주기적 바퀴 진동을 원인으로 볼 증거는 없었다. 전체 과거 구간은1Hz 제한이 남는다. 영상/띠 경로는 `outputs/e2e18-admin/playback/release24-baseline/r24d1-f-{02,04}-b20bb52a/`. 개요 원본은 없어 unavailable로 표시했다.

VM `epoch-replay.json`은 실패1·성공2의마지막두보고, 로봇별 총12회 저장 관측 재생이다. 기존 matcher는 최근18 views를 발행 명령으로 현재 몸체 좌표에 옮겨 함께 맞춘다. 이전 이동 전 관측이 남으면 명령 이동 오차를 현재 RGB가 설명해야 한다. 현재 내려놓기 이후6장만 같은 matcher에 주니12/12가 기존 관문을 통과했다. 실패169.7초 r1의 평가 yaw 오차는−2.4595°→+.3113°, r2는−2.4111°→+.0166°였다.120.6초 r2는−4.5730°→−.8045°였다. 새 궤적 성공은 아니며 정답은 여기 오프라인 평가에서만 읽었다. 원인 확인 후 같은 추정 경로의 gated 소유 활성3개를 PID·명령·SHA 확인하고 SIGINT로 정지했다. 다른 작업은 유지했다.

세 번째 기본 OFF 후보 `axis_observation_window=axis_current_setdown_v1`은 융합과 함께 쓴다. 새 수치 문턱 대신 기존 내려놓기 이벤트를 관측 epoch 경계로 삼고, 그 뒤 실제 자기 RGB로 얻은 관측만 global matcher에 준다. 모든 원본 views는 그대로 보존한다. 이 방식은 [Nav2 AMCL 공식 current-scan sensorFunction](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp)의 현재 측정을 현재 위치 가설에 맞추는 관측 모형 원칙을 따른다. AMCL 알고리즘/레이저 입력/기본값을 복사하지 않는다. 오차의 실측 반례는 위 재생이다. 기존 RGB 선·view 수·rank·점수 차·4cm·10°·18°·180초·3회는 모두 유지한다. Round2는 새 소스로 같은6장면을 처음부터 잰다.

Gated HOST_ERROR는 release19 경로의 일반 ScriptRunner에 없는 `reused_waits` 기록 속성을 읽어서 발생했다. 기록부가 속성 미제공 시 빈 reuse 목록을 남기도록 고쳤고, 실제 clock-only reobservation 경로를 회귀 시험한다. 중단에도 선택 로그·예외 사유를 보존한다. 상태 전환만 하고 SIM 시각이 같은 loop의 중복 ring capture도 기록부에서 제거한다. 제어 동작·대기 시간은 바꾸지 않는다.

Hiwonder [공식 제품 사양](https://www.hiwonder.com/products/masterpi)·[조립/보정 안내](https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html)도 열었다. 서보 동작각·조립 편차는 설명하지만 공동 운반 빔의10° 허용각을 뒷받침하는 사양은 찾지 못했다. 이를 기존10° 근거로 전용하지 않는다.
