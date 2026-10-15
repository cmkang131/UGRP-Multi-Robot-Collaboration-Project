# reloc15 — 운반 회전 원인·보정 전달 분리 탐색

**NOT_READY — gcp1 3라운드18회 종료, 원본18/18 해시검증, 소유 실행·임대·예약0. 후속큐미제출.** 시작 소스 562b77bccb918d997b4f2cb846b523aa675fc25a, 기준 물리 f3d0640829abede9f84c1b05cbc1ff877d78b8fe. 질감/v7이 주 조건이며 이전 결과와 합산하지 않는다.

최종 요약은 [summary.json](summary.json), 전체 누적 관문·거부표는 [rejection-table.md](rejection-table.md) / [JSON](rejection-table.json)이다. 자기 지도93584 동일조건 주행오류43/45→6/45는 부분개선이다. 운반은R3에서도실제0.221°를12.474°로오수용해정지했으며목적지놓기확인0이다. 최종기록수정의새물리검증0·같은조건운반성공영상없음까지차단사유다. 아래준비상태서술은각단계당시의기록이다.

수정 전에 GCP 원본 운반 13개(11개 원장 가용, 2개 HOST_ERROR 원장 없음)를 분석했다. [명령별 yaw](carry-yaw.md), [수정 전 관문표](rejection-table.json). 정답은 평가에만 쓴다. 0 명령 yaw의 비는 undefined다. 67.76°는 실제 yaw의 절댓값이 아니라 추정 오차다.

93315 R3 고정 명령 재생은 scene.xml 일치·1245틱 모두 원본 위치 오차 0m. 2Hz 전체·마지막10 SIM초10Hz, 개요(eval)/r1/r2(유휴), SIM4배속. MP4는 ffprobe 확인·235853bytes. 원본 카메라는1Hz로, 추가 프레임은 명령 재생이며 원본 저장 프레임이라고 부르지 않는다. 영상/프레임은 기본 checkout outputs/e2e18-admin/playback/reloc15에 보존한다.

## 분리할 후보

1. `reloc15_pose_handoff_v1` 기본off: map 측정의 exposure/release SIM시각과 map→execution/own-command odom 프레임을 명시한다. release 지연 동안의 body odom을 한 번만 재생한다(현재 동기 어댑터의 지연은0). PF 예측은 측정으로 다시 융합하지 않고 기존 명령 전파를 쓴다. 관측 없는 프레임은 `last_measurement_t`를 갱신하지 않는다. ORB bank가 비어 있어도 기존 correction gate를 통과한 지도 측정은 실행에 전달한다. 기존 안전/수용 오차는 유지한다.
2. `reloc15_rgb_heading_v1` 기본off: 들고 있는 동안 기존 S2 own-RGB homography 분해·모든 cheirality 유효해 yaw 구간을 재사용해 해당 영상쌍의 명령 yaw를 한 번 교체한다. xy·전체 RGB fix epoch는 갱신하지 않는다. 카메라 회전은 고정 v3 회전 사슬·자기 발행 PWM뿐이다. unloaded metric FK 자격 제한을 우회하지 않는다. loaded 회전 외부보정의 정확성은 미검증이다. 기존 5Hz·loaded settle2.25초와 S2 feature/pixel/pitch 수치를 그대로 쓴다(근거는 해당 S2 모듈; 새로운 수용 상수0). 불명확 영상은 보정하지 않는다.
3. 기록 전용 `--failure-rgb-buffer`: 실패/중단 직전10 SIM초 자기RGB10Hz, 학습 카메라와 분리. 제어 호출 주기·입력 불변. 5Hz selfmap은 중간 .1초에 기록만 한다.

조사 1순위를 먼저 비교하며 관측 모델 전체 교체·목적지 ACT 인계는 별도 검증이다. 참조: 사용자 제공 loc.md 72–86행, 기존 S2 `zone_solo_cyan_rotation_envelope.py`와 그 출처 OpenCV homography decomposition tutorial. 질량·마찰·토크·카메라 배치/FOV는 변경하지 않는다. 모델/학습0, weldOFF, held_object_hidden_v1 유지.

## 탐색 예산

최대3라운드, 라운드당 selfmap3+carry3. 동시 전체40 이하, 자기6 이하. GCP gcp1/n4-highcpu-64, 24h STOP·idle20m·budget-stop 유지. 첫30 SIM초 속도와 HOST_ERROR/cap_end 모두 기록. 후보를 합산하지 않고 동일 시드의 한 변수 변경부터 비교한다. 새 실행 소스는 커밋 고정한다. 통과 근거 없는 후속큐는 제출하지 않는다.

## R1 비교

소스9607de16. selfmap93584 기준/전달후보는 모두 오류152/214·주행오류43/45다. 예측을보정으로분류한횟수만변했으며 정확도개선아님. 93583후보는오류93/149·복구상한46.6SIM초(HOST_ERROR/제어예산소진). 운반93315 기준max67.76°/고오차106틱, 5Hz후보max66.47°/37틱, 놓기0/1. 93266후보max8.81°·150SIM cap_end·놓기0/1. [R1원본재집계](round1.json). 같은벽/바닥을보는카메라회전과실제base yaw가분리될가능성을추가평가중이다.

R2 준비 후보(당시준비단계): `reloc15_update_budget_v1` 기본off는조사loc.md의.05m/2.5°를기존10cm/5°과제오차목표의1/2로산출한관측기회가정이다. 문헌최적값·실측정확도보증아님. 기존.25m/.2rad와한변수로비교하고stationary영상은재측정하지않는다. `reloc15_heading_10hz_v1` 기본off는기존native.1SIM초주기만사용한다. 저장실패yaw속도p95/max16.87/17.99°/s이면간격내1.69/1.80°,기존.2초이면3.37/3.60°이므로기존5°목표아래관측기회비교다. 수용오차를완화하지않는다. 카메라실제회전과base회전의분리가확인되면주기만빠르게해도해결할수없으므로그실행은내지않는다.

## R2 추가 원인과 단일 변수 후보

추가평가재생은카메라/base회전분리를지지하지않았다. 운반27.8–125.7초actual-vs-command camera회전오차p95약.21°·yaw차최대.0067°([camera-summary](camera-summary.json)). 대신 R1 139.7→139.9초고오차영상쌍은35/39인라이어가이미지테두리에몰려H≈I가됐다. 실제floor특징4개는이상점으로버려졌다. 원본평가yaw−1.7448°에희소정합−.0244°,마스크ECC−2.6060°. 5개고오차쌍에서ECC오차.21–.86°로희소정합1.62–2.85°보다작다([분포](dense-check.json)). 이5쌍은이미열람한진단자료이며확증자료아님.

`reloc15_dense_yaw_v1` 기본off는관측주기5Hz를유지하고정합방법만바꾼다. 경계제외반경80px는기존LK창21px·pyramid3의전체지지반경(21−1)/2×2³에서계산한다. ECC정합각50회는[OpenCV공식기본count](https://docs.opencv.org/5.0/main_modules/video_track.html)를계산량상한으로사용한다. correlation수용상수없음. dense homography Jacobian의8개파라미터rank를기계정밀도로확인하고,정/역방향순환잔차·모든cheirality해·기존pixel/pitch불확실도를기록한다. 높은correlation은정확도인증이아니다. 실제제어입력은여전히자기RGB/발행명령뿐이며정답은평가에만쓴다.

R2 자기 지도93584의갱신후보는주행오류6/45(기준43/45)·전체73/216(기준152/214)로줄었지만0오류아님. 93583은주행29/33오류로남는다. R2dense운반은forward/backward82px·yaw75°·sigma7.8°인정합도적용한결함이확인돼2개모두SIGINT/SUPERVISOR_STOP했다. 새기본off `reloc15_heading_quality_v1`은기존S2 confidence3×σ가현행과제5°보다큰관측을unknown으로남기고자세/P/fix시각을바꾸지않는다. 5°는기존과제목표,3은기존S2값이며새보수오차를발명하지않는다. 해당분해능조건이실제정확도를보증한다는주장은하지않는다. R3은이한변수만비교한다.


## R3 종료와 남은 결함

운반93266 59.5SIM초실제.221°/시각12.474°/예측3sigma4.837°의오수용을확인해동일수용식의R3운반3개를소유PID/명령확인후SIGINT+SUPERVISOR_STOP했다. [수용감사](quality-admission-audit.json). 3라운드소진·추가물리0·승격/후속큐미제출이다. cycle consistency와ECC고상관만으로정확도를보증할수없고,고오차를포괄하지못하는관측불확실도/다중가설수용이남는다. 실패한기본off후보를기본값으로채택하지않는다.

기록옵션의추가결함도확인했다. R1–R3자기지도는중간10Hz기록에control port.capture()를호출해제어frame_id가1,3,5...로증가했다. 자연바닥RANSAC이ID를seed로쓰므로기록전용불변계약은충족하지못했다. 같은라운드동일시드짝은같은기록조건의비교지만기존기록off조건과동일행동이라고주장하지않는다. 3라운드후소스는recorder가world.render_jpeg만쓰게고쳤고control frame_id불변회귀를통과했다. **이기록수정의새물리검증0**이므로최종소스의자기지도폐루프검증은미완료다. 운반은기존10Hz제어capture의JPEG를buffer에넣었으므로이frame_id결함의대상이아니다.
