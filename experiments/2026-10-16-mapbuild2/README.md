# mapbuild2 — 실제 MJWarp 주행·부분 지도 산출/채점 완료, NOT_READY

[PR #556 DRAFT](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556). mapbuild1의 남은 관문1→2→3을 실행·진단했다. **관문 통과나 지도 완성은 아니다.** warp10 같은 시드 비교(4), 장시간 frontier 탐색, 경로/도착·운반은 실행0이다.

## 실제 주행에서 확인한 결과

`zone_hardmaps1_h1_final_v3`, 장면 `walls_floor_contrast_v5_indigo110_s80` / `no_mip_v1`, gcp2 L4 **shared4세계**(FOLDED/HIGH closed × 초음파 OFF/ON). 세계별4 SIM초·16,000물리step, 자기 프레임164/164를 정상 `cap_end`로 기록했다. 41.11분은 공유 수집 시간으로 속도 판정에 쓰지 않는다. CPU 물리step0이다.

|FOLDED|LK 기존→RGB 열 제외|xy ATE p95 기존→후보|yaw ATE p95 후보|
|---|---:|---:|---:|
|초음파 OFF|37/40→37/40|2.53→1.05cm|0.80°|
|초음파 ON|37/40→38/40|2.42→1.89cm|1.17°|

정확한 수정 yaw 채점은 [tracking-scores.json](tracking-scores.json). HIGH는80/80쌍 미자격·unknown이다. 비교에 쓰인 HIGH는 **화물을 들지 않은 closed 명령 조건**이며 실제 운반 카메라 자격은 여전히 없다. 원시 `2*atan2(qz,qw)` 라벨과 별도로 정규화 quaternion의 몸체 x축 yaw를 평가기에만 적용했다(최대 차이0.00720°). 추정 궤적을 저장한 뒤 평가 정답을 열었고, 척도/궤적을 정답에 맞춰 최적화하지 않았다.

**짧은 펄스의 실제 변위가 작아 기존 명령 척도를 채택할 수 없다.** OFF의1–2 SIM초 전진 구간은 실제 약0.402mm인데 v122 명령 예측은 약12.9mm(32.15배)다. 횡이동 예측/실제2.11배, 회전3.13배다. LK의 cm급 ATE를 넓은 이동·미터 척도 검증 성공으로 해석하지 않는다. [구간별 실제/예측/추정](command-phase-scale.json).

ON은 자기 거리 판독41회씩 모두 `ok`, 중앙0.443/0.441m, 최대2.475m였다. OFF에는 판독0이다. 측정 대상의 이름은 입력에 없다. 동일 명령을 낸 별도 세계의 xy 차이도 최대0.327mm였으므로 추적 n 차이를 센서 효과로 해석하지 않는다. **이번 ON/OFF는 기록/추정 비교이며 센서 융합 제어가 아니다.** [센서 비교](sensor-comparison.json).

## 원인 분포와 카메라/ORB 진단

|경로|입력→카메라→특징→기하 추적|확인한 거부|
|---|---|---|
|LK 기존|160→80→[funnel](all-gates-funnel.json)→74|HIGH80, FOLDED rigid/texture6|
|LK RGB 열 제외|160→80→80→75|HIGH80, rigid consensus5|
|희소 ORB 지도(기존·FAST7 열 제외 각각)|160→80→80→0|HIGH80, FOLDED `insufficient_matches`80|
|지도 프레임|164→82→77→77|HIGH82, 시각 pose unknown5|

- **검출·인접 쌍 대응과 지도 정합을 분리했다.** FOLDED OFF의 OpenCV 기본 ORB500/Hamming/ratio0.75/RANSAC은40/40쌍에서 essential 행렬을 반환했다. 기존 바닥 마스크+800에서도 인접 mutual 대응 중앙26.5개다. 반면 희소 지도는0/80이다. 실제 예:0.5초 프레임의 특징35개·지도 대응5개(<기존 최소8), 지도 landmark11개를 유지한 채 계속 실패한다. 초기 앵커/지도 대응 경로를 먼저 다뤄야 한다는 근거이며, 원인을 단순히 "ORB 특징점 부족"이나 압축/조명 탓으로 확정하지 않는다. essential 행렬 반환은 미터 추적/SLAM 성공이 아니다.
- [ORB48조건 표](orb-table.json): raw/보정, 마스크, nfeatures500/800/2000, pyramid1/4/8, 10Hz/2Hz, VGA/절반, Gaussian3x3, PNG/JPEG를 비교했다. 기존 수용 상수는 바꾸지 않았고 새 수치는 API 기본값 또는 계산량/영상 진단 조건이다. [공식 OpenCV matcher](https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html), [ORB](https://docs.opencv.org/4.x/db/d95/classcv_1_1ORB.html), [calib3d](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).
- **평평한 차체를 가정한 지면 카메라 기하가 맞지 않았다.** 평가에서 몸체 tilt 중앙 FOLDED6.11°/HIGH6.27°, 지면 기준 카메라 회전 오차p95 7.17°/7.98°, 위치 차이23.45/26.62mm를 측정했다. 몸체 상대 팔/카메라 오차p95는1.04°/1.55°로 더 작다. 이 정답은 평가에만 쓰고 교정값·수용 상수로 채택하지 않았다. [카메라 평가](camera-summary.json).
- mapbuild1과 이번 reset0 프레임 JPEG는 **전체 SHA 동일·RGB MAE0**이다. 초기 렌더 한 장의 동일성만 확인한 것이며 전체 물리/영상 동등성은 아니다. 조명·밉맵·질감 변경 실험은 추가하지 않았다. 현재 직접 확인한 기하/지도 정합 문제를 이미지 질감 부족으로 덮지 않는다.
- 실제 카메라 원본은 지정 ZIP·백업 폴더 경로에서 미발견이다. 사용자에게 다른 경로를 요청했지만 아직 같은 파이프라인의 실기 비교는 하지 못했다.

## 자기 추정 pose → 지도 결과

정답이나 공용 top 없이 자기 RGB의 기존 벽 접점·색 검출과 LK 추정 pose를 OdomGrid에 누적했다. 별도 평가기가 정적 지도 사각형-셀 교차와 첫 원점 SE(2) 정렬만 사용했다. 미관측은 unknown이다. 문은 관측 free 횡단과 양쪽 벽을 가진 격자 후보이며 통과 인증이 아니다.

|조건|전체 격자 커버리지|정답 안 관측/전체|틀린 free 벽 셀|점유 TP|지도 밖 예측 셀|
|---|---:|---:|---:|---:|---:|
|FOLDED OFF|1.237%|37/2990|7|0|38|
|FOLDED ON|1.271%|38/2990|7|0|40|
|HIGH OFF/ON|각0%|각0/2990|0(미관측)|0|0|

FOLDED의 벽점19/20개 중 일부는 초기 가까운 벽에 맞지만, 예측→정답 거리 중앙은0.40m다. 문 후보7개는 정답과 수m 차이이고, 목적지 표본65/67개도 오검출이다. **부분 지도가 출력됐다는 뜻이지 쓸 수 있는 지도라는 뜻이 아니다.** [정적 지도 채점](map-scores.json). 실제 reset 화물 collision box는 평가기에서만 별도 장애물 양성 표적으로 추가했다. [화물 장애물 별도 채점](evidence-extra/obstacle-evaluation.json). reset 화물 collision box5개에서 만든 격자 표본22개는 네 조건 모두 예측0/22(미관측)다. 표본 수를 물체 인스턴스 성공률로 바꾸지 않는다. 이 원점 주변 관측에서는 장애물 예측이0이며, 정적 지도에 장애물 표적이 없다는 이유로 누락을 성공 처리하지 않는다.

지도 실행은1차 불필요한 과거 명령 보정 파일 의존성,2차 NumPy 정수 JSON 오류를 보존·수정한 뒤3차에 산출/채점까지 끝냈다. 현재 같은 경로를 더 조정해 성공으로 포장하지 않고 멈췄다. 다음 대기열은 [WITHHELD](next-queue.json)이며 실제 존재하는 원격 `all-gates-funnel.json` 절대경로를 연결했다.

## 영상·기록 수정·무결성

- [전체 시간순 검토](playback-review.md): HIGH 실패·FOLDED 지도 실패·추적 유지 구간의3조건, 개요+r1+r2 합성3배속 영상 각41프레임/1.366667초/78–88KB. 전체2Hz와 전체10Hz 띠18장을 직접 파일로 확인했다. 임무 성공 실행은 없다. Mac은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/mapbuild2/`. 앱/브라우저/QuickTime 실행0, `ffprobe`는 원격에서만 썼다. [회수 검사](retrieval-verification.json).
- 원본667파일·24,049,270 bytes의 SHA 불일치0. 원본의 누적 pose 공분산은 보존하고 자기 발행 명령만으로 독립 프레임 증분 공분산164/164를 재생했다. 평가 yaw도 별도 파일로 바로잡았다. 실제 명령·카메라·물리·원본 결과를 덮어쓰지 않았다.
- [모든 시도와 감독 중단](evidence-extra/attempts-final.json). 초기EGL 오류, funnel 경로 거부, 원장 보정 전 감독 중단, 지도2회 오류, 영상 중복/CLI 오류, 장애물 평가기2회 오류까지 남겼다. 감독 중단은 wall 상한 종료나 관측된 NaN 실패가 아니다.
- 큰 JSON8개는 zstd 무손실 압축 뒤 실제 해제 bytes/SHA 일치를 확인했다. 프레임·PNG·npz는 원격 영속 디스크에 남겼다. [압축 영수증](evidence-extra/archive-receipts.json), [현재 payload hash](evidence-extra/payload-hash-receipt-v2.json). 재생 전에 [restore_json.py](restore_json.py)로 원문 JSON을 복원한다. 원격 경로는 `/home/ugrp/ugrp-sim/runs/mapbuild2/`이며 Mac 전체 raw 회수·Drive 업로드는 하지 않았다.
- [실행별 SHA](source-receipt.json): capture `b68315d0b128de2d267fd4684d6e34c4d809bcfc`, replay `ef0dd1d74dcc02cf4e9c4b68fd20d3c9972d0e03`, mapper `e39dc1cc8…`, vision `5974a181a2cec9731339a6ce3aadc0464b8dddcf`. 후속 소스에는 독립 명령 공분산·정확한 평가 yaw·RUN_META/자원 기록도 고쳤지만 이번 물리 수집 소스를 소급 변경하지 않았다.

## 운영과 남은 관문

관련 비물리 **14 passed**(신규8+기존mapbuild1의6), whitespace·컴파일 검사, 표준 workflow 등록(`mapbuild2-issued-diagnostic`, 기본off)을 확인했다. 실제 관리 CLI를 통한 물리 인수와 전체 CI·승인·병합은 별도다. 공통 runnable 번들·기본 제어기·카메라/FOV·공유 설치 변경0, LLM 호출0, 실제 운반0, gcp1/gcp3/gcp4 접근0이다. `COORDINATOR_NOTE.md`는 기존 미추적 파일 그대로 보존했다.

자기 Python PID/lease0 확인, 다른 lease 보존, VM 정지0. 실행기에 wall 상한을 넣지 않았다. L4에 남아 있던 기존8h 호스트 설정은 공유 작업 중 정지해야만 해제할 수 있어 [설정 차이](host-scheduling-note.md)로 알렸다. idle20/budget-stop은 유지했다. 실제 청구 비용은 별도 측정하지 않았다. 이 결과는 다음을 통과하지 못했으므로 **NOT_READY / PR DRAFT**다:

1. MJWarp에 맞는 명령 척도와 충분한 실제 이동 범위, RGB만으로 유효한 지면 카메라 보정.
2. HIGH 실제 하중 자격과 희소 지도 초기화/재정합 회복.
3. 보인 벽을 free로 지우지 않는 점유 누적, 동료/벽의 목적지 색 오인 제거, 실제 frontier 커버리지.
4. warp10 결과 뒤 같은 시드의 지도 있음/자기 지도 위치·경로·도착 비교.
