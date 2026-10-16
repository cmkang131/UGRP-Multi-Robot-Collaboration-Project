# egomap14 — 자기 명령 이동과 영상 시차로 벽점 삼각측량

## 구현·재생 전 사전 등록 (2026-10-07)

시작 `a3f04693`, PR #405. 탐색 PR #409는 동결된 실패 결과에서 중단했다.
사용자의 새 접근으로 이 실험만 시작하며 기존 floor_boundary/servo_fk/online_vp 실패는 바꾸지 않는다.
MuJoCo·렌더·모델 호출0, 기존 녹화의 own RGB/발행 명령만 사용한다.

### 방법과 고정 옵션

[REFERENCES](REFERENCES.md)의 (c) **시간상 두 시점 점 삼각측량**을 선택한다.
OpenCV Shi–Tomasi+LK forward/backward 추적, OpenCV DLT triangulatePoints,
ORB-SLAM2의 시차/양의 깊이/재투영 검사 원리를 사용한다. ORB-SLAM 전체 이식이나 line SLAM이라
부르지 않는다. (a)의 수직 선 대응은 좋은 후보지만 수평 pixel만으로 pitch 독립 방위를 얻는다는
가정은 하지 않는다. (b)의 SVO depth filter는 pose 오차를 픽셀 잡음만으로 흡수하지 못하므로
첫 단계는 두 자세의 상관 공분산을 포함한 명시적 삼각측량으로 제한한다.

- `wall_detector=off` 기본: 기존 검출/메모리 출력 bytes 동일. 새 상태를 만들거나 사용하지 않는다.
- `wall_detector=parallax_v1`: 자기 RGB, 자기 명령 DR/공분산, 고정 K/21자세 보정만 입력.
  기존 픽셀 검출기(egomap10 precision94–99%)의 접점 ±3px에서 특징을 시작·유지한다.
  이 ROI는 기존 range/horizon 후보 제한을 포함하므로 **전체 검출 경로가 바닥 가정과 독립이라고
  주장하지 않는다**. 벽점의 깊이/xyz는 바닥 교점을 읽지 않고 시차만으로 계산한다.
  임의 floor/물체 특징을 벽으로 세거나 서로 다른 점을 벽 선으로 연결하지 않는다.
- LK 공개 예제 고정값:15×15, pyramid2,10회/epsilon.03, FB<1px;
  GFTT max500/quality.3/minDistance7/block7, 재검출5frame, 기존점 반경5px 제외, history10frame.
  LK status 둘 다 유효, ROI 밖/영상 경계/미보정·미정착/팔 자세 변경/관측 gap>.5s면 추적을 끊는다.
  ≥3시점 후 oldest/current DLT; 0<cos(parallax)<.9998, 각 관측 z>0,
  모든 보존 시점 재투영 제곱오차≤5.991px²(σpixel1), 현재 카메라 거리≤4m.
  pure rotation/작은 baseline/일치 실패는 보류/거부로 남기고 바닥 투영으로 대체하지 않는다.
- 이동은 기존 M1 command predictor 평균과 V7CommandOdometry 공분산 그대로.
  M1 계수 `calibration_m1_dev.json`; v7 잡음은 e7b229b6의 구동 deadzone/마찰 범위에서 만든
  구조 사전이며 **실측 펄스 잡음이 아니다**. 측정 pose/관절/접촉을 공급하지 않는다.
  두 자세의 공통 과거 공분산 `P_ab=P_aa F_ab^T`를 유지하고 pixels1px와 함께 Jacobian 전파한다.
  동일 팔 자세의 잔여 pitch는 공통3° 표준편차 사전(이전0.9–2.8° 오차를 포괄), 미래 결과로 조정하지 않는다.
  covariance/깊이σ/역깊이σ를 출력하며 confidence는 `s0²/(s0²+trace(Cxy)/2)`,
  s0²=0.1²/12(기존 지도 cell 양자화 분산). σ를 임의로 작게 자르지 않는다.

### 자료·비교·분모

s1042/1043 개발 → 코드/설정 동결 → s1044–1047/s1050/s1051 확인 재생 각1회.
이미 본 녹화이므로 새 독립 확증이 아니다. 개발 결과로 임계값 재튜닝하지 않는다.
8건 모두 `r3`, 매2 frame, 기존 명령 정착(.25/2.25s)·무하중21자세 eligibility를 재현한다.
운반/미보정/미정착 제외도 전체 분모와 함께 남긴다. s1050–1051 전체 운반 성능이라고 부르지 않는다.

1. 모든 eligible 프레임의 parallax/기존 바닥 투영 예측을 먼저 저장·해시 봉인하고 그 뒤에만
   GT 차체 pose/실제 벽을 평가기로 읽는다. 같은 프레임의 벽 경계 거리≤.15m precision,
   거리오차 중앙/P90/RMSE와 [0,2),[2,3),[3,4]m 구간별 표를 분리한다.
   현재 추정된 body-local 점을 평가 GT body로 옮겨 검출 거리를 채점한다. 별도로 DR 출발 정렬
   누적 점 오차도 보고하며 둘을 합산하지 않는다.
2. recall은 기존36 수동 주석 프레임/96열의 가시 벽 접점 분모를 유지한다.
   s1050/1051도 eligible 목록의6개 중앙 분위 프레임을 결과 계산 전에 선택·RGB만 주석한다.
   nominal 양의 깊이/4m와 ignore 규칙은 예전 평가 그대로다. 이는 실제 camera GT 가시 분모가
   아니며 거리 bin에도 nominal 보정 한계가 남는다. 새 주석은 평가에만 쓴다.
   sparse point는 가장 가까운 고정 열 한 개(열 간격 절반 이내)로 대응하고 행 차≤3px,
   벽 거리≤.15m이면 metric TP. 여러 점이 한 열에 와도 recall1회만 센다.
   빈 출력의 precision=NA/recall0이며 공통 검출점만 골라 recall 분모를 줄이지 않는다.
   검출수 차이를 구분하려고 parallax가 낸 **같은 픽셀**의 바닥 투영 오차도 별도 병기한다.
3. 점 covariance 신뢰도별 precision/수, 시차/추적/깊이 거부 사유·baseline·깊이σ를 기록한다.
   자신감 높은 점만 사후 선택해 주 관문을 다시 계산하지 않는다.

### 사전 관문

8건 **각각** 전체 point precision≥90%, 주석 metric precision≥90%/recall≥70%,
점 거리오차 중앙≤.10m/P90≤.25m, 기존 같은-frame 전체 precision 비감소,
주석 가시 접점≥50·주석 metric TP≥30. 기존 검출기 관문/투영 관문의 수치를 유지한다.
off 골든 bytes 동일, 허용 입력만 사용, accepted behind-camera0도 모두 필요하다.
모든8건 통과할 때만 RBPF100+pose_graph 지도 재생·회색 실제벽/신뢰도 음영/경로 그림을 갱신한다.
실패/자료 부족이면 튜닝·추가 녹화·지도 재생 없이 원인만 기록하고 멈춘다.

raw `/Users/changmin/projects/ugrp/outputs/wall-parallax-v1/`에 새로 저장하며 원본은 보존한다.
ENOSPC=HOST_ERROR. 실험 source commit/push 후 실행, 시험은 변경1–3파일·off golden만.
기존 venv/OpenCV/NumPy 재사용, 새 dependency 설치0. timing benchmark가 아니므로 잠금 없음.
다른 worktree 수정/force/reset/병합0, #405 DRAFT, 모든 커밋 Codex trailer.
TensorBoard 기존 사용자 면제/Drive 프로젝트 예외 유지.
