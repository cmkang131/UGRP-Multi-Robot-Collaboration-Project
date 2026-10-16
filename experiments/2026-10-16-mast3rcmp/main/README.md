# mast3rcmp2 — recording-r2 오프라인 비교 완료

**같은401프레임에서 MASt3R-SLAM은 추적을 끝까지 유지했지만 위치 오차는 LK/RBPF보다 컸다.** 비교 전용이며 최종 위치 추정은 OpenCV 계열로 유지한다. 제어기·지도·장면·다른 작업자 파일 수정0, 새 물리 실행0이다. `codex/mast3rcmp`, [PR #566 DRAFT](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/566).

## 같은 녹화의 카메라 중심 ATE

공통401/401장, 제외0, 프레임 ID·SIM시각 정확 대응. 단위는 **mm**, 수치는 정렬 후 카메라 중심 위치오차다. 방법·호스트·이전 noslip10 결과를 합산하지 않았다.

|방법|전체 분모와 추적/출력|ATE RMSE (a) GT척도 Sim(3), 참고|ATE RMSE (b) 허용척도 SE(3)|허용척도 p95 / 최대|
|---|---|---:|---:|---:|
|MASt3R-SLAM|초기화1+추적400 /401, 실패0·미처리0|63.261|65.643|133.384 /314.984|
|LK 기준선|LK측정390 /401, 명령예측11(초기 포함), 출력401|10.347|12.252|18.422 /21.253|
|RBPF|같은 LK/명령 이동 입력, 출력401|13.600|13.615|24.951 /29.154|

[전체 정렬·분모·척도·해시](comparison.json), [모든 실행을 포함한 요약](summary.json). MASt3R는 자기RGB+고정K/D만으로 추정한다. LK/RBPF는 같은 원시RGB와 자기 발행 명령 이력도 쓰므로 RGB만 사용하는 세 방법의 통제된 절제 비교는 아니다. LK 기준선은 시각 측정이 없는 프레임에서 명령 예측으로 이어진다. 출력이 있다는 사실을 시각 추적 성공으로 바꾸어 세지 않는다.

세 방법 모두 실제 저장 카메라 중심 정답에 맞췄다. LK/RBPF의 평면 차체 자세는 명목 고정 body-to-camera 변환으로 카메라 중심에 옮긴다. 차체 roll/pitch·높이·관절 처짐은 추정하지 않는다는 한계를 유지한다. 실제 카메라 정답은 제공자가 같은 XML SHA를 확인한 뒤 저장 qpos의 `mj_forward`로 계산했다(물리 적분0). GT 차체 위치에 명목 오프셋을 붙인 값을 실제 카메라 정답으로 대신하지 않았다.

## 입력·봉인·평가 순서

제공자는 mapbuild5c다. gcp5 `/home/ugrp/ugrp-sim/runs/mapbuild5/recording-r2/manifest.json` SHA256은 **de9addf5a7c268db99b0b8c7198e435a5adf90713bda7a718b4e6a7aec34e7d5**다. [수신 manifest](sender-manifest.json), [전송 검사](input-transfer-verification.json): 자기RGB401/401 및 fixed K/D·floor 보정 SHA 일치. gcp5→Mac RAM 파이프→gcp4이며 Mac 원시RGB 저장0·명령/정답/top 추정입력0이다. 시각은 기록기 `mapbuild5_capture.py`의 `t=k/10`, manifest의10Hz에서 생성하고 평가 시 전부 대조했다.

원 녹화는40 SIM초, `cap_end`, FOLDED·무하중·MJWarp `warp_native_contact_v1`/noslip0이다([원본 접촉 프로필](source-contact-profile.json)). 이번 작업에서 물리 실행이나 GPU 물리를 다시 수행하지 않았다. 이전 연습82장은 설치 확인 전용이며 이401장과 합산하지 않는다.

1. 공식 고정 코드로401장을 전부 추정하고 궤적을 저장했다. 실행 소스 `ae4764136127b71b3b4bf4b8576de0c76b1cd5bc`.
2. 자기RGB 첫 프레임만 보고 바닥 내부 사각형 `(64,256)–(447,335)`을 선택했다. 30,720픽셀 전부 양의 유한 평면 거리였다. 고정 높이 **0.230860865m**를 예측 바닥 signed distance 중앙값 **0.981169513**으로 나눠 허용척도 **0.2352915190301189**를 고정했다. 새 추적 수용 상수나 GT 맞춤은 없다. [바닥 참조](seal/floor-reference.json), [척도](seal/allowed-scale.json), [ROI 몽타주](seal/floor-roi-montage.png).
3. **2026-10-16 14:44:05.224173Z**에 추정·척도를 봉인하고14:44:08Z ops-alert에 알렸다. [봉인](seal/estimation-scale-seal.json) SHA `3f34f8784e444498b31139720e07b26ca947e10d25ce53cc4cb8ff788c00aa28`, 궤적 SHA `a89b637e3814b7921c961ae615ee0b1f090fb289ef0e292e99c157b2cca58269`.
4. 제공자가14:47:27Z에 공개한 [평가 manifest](evaluation-manifest.json) SHA **8ff6dbaf090a555b9ed52e1a6d251567b010df79913021fc60c0ade66a6fd458**를 확인하고14:48:26Z 평가4파일만 RAM 파이프로 받았다. [4/4 SHA검사](evaluation-transfer.json). Mac 정답 payload 저장0이다.
5. (a)는 GT로 척도·회전·평행이동을 모두 맞춘 참고치다. MASt3R의 GT척도는0.266420450으로 위 허용척도와 다르다. (b)는 봉인 척도를 유지한 채 GT로 회전·평행이동만 맞춘 SE(3) ATE다. LK/RBPF는 기존 metric scale1을 유지한다. [채점 후 무결성](post-evaluation-integrity.json): 봉인8파일 불일치0, LK/RBPF 궤적도 제공자의 예측 봉인과 일치.

고정 높이/법선은 명목 장착 FK이고 실시간 측정이 아니다. 중력 처짐·차체 기울기에 따른 바닥 가정 오차는 남아 있다. MASt3R는 원화와 같은 자기 녹화에서 시작하되 핀홀 보정과 공식512×384 crop을 적용한다. 최종 중심 단면 FOV는49.8008°×38.2161°이며 원화 대비10.4373°×6.2348°를 잃는다. 동일 원시 프레임이 동일 유효 FOV를 뜻하지 않는다. [설치·렌즈·입력 가정 원기록](../README.md), [최종 K/FOV](../network-camera.json).

## 자원·설치 고정

[실측 요약](comparison-run-summary.json): 프레임 시간 중앙 **0.153451초**, 평균 **0.345972초**, p95 **1.114653초**. 모델/버퍼 준비28.488초, 전체 프로세스182.434초다. 프레임 시간은 decode 이후 추적·동기식 backend까지이며 초기화 큐는 원래 비동기 경로다. 전체 실행 시간과 프레임 중앙값으로 계산한 속도를 혼동하지 않는다.

GPU 전체0.5초 표본 최대 **22,230MiB /23,034MiB**(모든 자식 context 포함). 순간 최대 보장은 아니다. 주 프로세스 torch allocated/reserved 최대는7,712,232,960 /7,969,177,600bytes로 별도다. 연습의 약9GB 수치를 긴 영상 요구량으로 재사용하지 않는다. gcp4 실제 머신은 **g2-standard-16, NVIDIA L4×1**이다. `configs/gcp_hosts.json`의 g2-standard-8은 수정하지 않았다.

공식 소스 **e6f4e3d474fad0e11f561482012be864ba8c3f17**, [체크포인트3개 SHA256](../checkpoints.json), [라이선스 원문 URL/hash](../license-sources.json), [환경 freeze](../installation/freeze.txt), [설치 산출물 해시](../installation/install-sha256.txt)를 그대로 유지했다. 코드와 MASt3R 가중치의 **CC BY-NC-SA4.0 및 checkpoint notice 추가 조건**을 확인한 학술 비교다. 공개 원문에서 최소 VRAM 수치는 확인하지 못했으며 논문의 RTX4090을 최소 요구로 해석하지 않는다. 알려진 핀홀 K 모드와 보정 없는 central-camera 모드 중 이번에는 고정K 모드를 사용했다. 기존 시뮬레이션 venv와 분리한 gcp4 venv이며 모델 키·에이전트 자격 증명 VM 전송0이다.

## 검증·보존·운영

[순차 누적 funnel](rejection_table.json):401→401 SHA/보정→401처리→401유한 궤적→401척도봉인→401평가대응. 실패 사유·막은 물체·최소 틈은 오프라인 RGB에서 미관측/미측정임을 명시한다. [큐](queue.json)의 `rejection_table`은 이 파일의 절대경로다. [재현 명령](reproduce.json), [원본 실행 파일 SHA 목록](raw-manifest.json), [회수 검증](retrieval-verification.json)을 보존한다. 원시RGB·pointmap·추정 궤적·정답은 gcp4 영속 디스크에 남으며 Mac에는 요약·몽타주·소형 검토 영상만 있다.

비물리7검사, Python compile·whitespace 통과. [검증](validation-resume.json). [영상 검토](playback-review.md)는0–40초2Hz와30–40초10Hz를 포함한다. 첫 영상은 ffmpeg timebase 반올림으로403장이 되어 거부·보존했고, 수정본은 ffprobe **401장·13.366667초·3배속**을 확인했다([시도](attempts.json), [최종 영수증](review-r2/receipt.json)). GUI0이다. 원인이나 일반화 성능을 이 한 영상으로 확정하지 않는다.

평가 대기 동안 gcp4를 직접 정지해 **14:46:55.813Z**를 확인했고, 평가 파일 도착 후14:47:49.448Z에 재시작했다. 최종 [자기 PID/GPU/lease JSON0·load0.11](gcp4-before-final-stop.txt) 확인 뒤 직접 정지했다. [최종 상태](gcp4-final-stop.json)는 **TERMINATED, 2026-10-16 14:50:21.938Z = 23:50:21.938 KST**다. 오래된 타 작업 `.lock` 파일은 보존했다. wall/8h/24h 상한 추가0, idle20·budget-stop ACTIVE 유지, CPU VM gcp2 시작0, 다른 VM lifecycle 변경0, Drive0이다.

완료 범위는 이 녹화의 오프라인 위치 추정 비교다. 다른 장면·장거리·실시간 제어·운반/도착·실물·학습 성능을 검증하지 않았다. 전체 CI·리뷰·병합은 별도이며 PR은 DRAFT다.
