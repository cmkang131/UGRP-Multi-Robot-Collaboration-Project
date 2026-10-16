# mast3rcmp — MASt3R-SLAM 녹화 비교 전용

**ownership-ack**: 필수 `agent-ownership.md` 확인. `codex/mast3rcmp`, gcp4 단독, 비교용 새 스크립트와 이 실험 기록만 소유한다. 제어기·지도·공용 백엔드·장면·다른 작업자 파일 수정0. 사용자 2026-10-16 결정에 따라 최종 위치 추정은 OpenCV 계열이며 MASt3R-SLAM을 제어 경로에 넣지 않는다. `COORDINATOR_NOTE.md` 인계에 따라 RBPF/왕복 녹화 제공자는 **mapbuild5**(같은 gcp5)다.

**설치·연습 완료 / 본 비교는 녹화 대기**다. [전송 영수증](practice-transfer.json): 연습 manifest `6b01b075aa8786f821a6d63e17268b486ec5c422bc13a4745fd07a98c7d12e0c`, 자기 RGB82/82 SHA256 일치. gcp5→Mac 파이프→gcp4로 옮겨 Mac 프레임 저장0. 명령·정답·top·r2·`own.json`·summary는 전달하지 않았다. `drive-off`41장과 `high-off`41장은 별도 영상이다. 4 SIM초·미소 이동 자료는 설치 확인에만 쓰고 성능 순위를 내지 않는다. HIGH 자격도 승계하지 않는다.

## 원문·설치 고정

- [공식 MASt3R-SLAM](https://github.com/rmurai0610/MASt3R-SLAM/tree/e6f4e3d474fad0e11f561482012be864ba8c3f17), commit `e6f4e3d474fad0e11f561482012be864ba8c3f17`. `main.py` SHA256 `354cc6930f23daa2c7761bc1fc75f29b8c63d13acb78e2b8b7432b674012ba79`. 내장 MASt3R/DUSt3R도 이 부모 커밋에 고정된다. 추가 [submodule](installation/submodules.txt), [의존성 freeze](installation/freeze.txt), [체크포인트3개 hash·공식 URL](checkpoints.json), [컴파일 산출물](installation/compiled-environment.txt)을 보존했다.
- [논문 arXiv:2412.12392v2](https://arxiv.org/abs/2412.12392v2), Murai/Dexheimer/Davison, CVPR2025. 원문은 RTX4090 1개·긴 변512·약15FPS 조건이며 단안 ATE의 척도를 정답으로 정렬한다. L4에서 같은 속도를 보장하지 않는다. 공개 README/논문에서 **최소 추론 VRAM 수치는 확인하지 못했다**. 4090 사용을 최소 용량 요구로 바꾸어 보고하지 않으며 L4의 실측 peak를 별도 기록한다.
- [코드 LICENSE](https://github.com/rmurai0610/MASt3R-SLAM/blob/e6f4e3d474fad0e11f561482012be864ba8c3f17/LICENSE.md)는 **CC BY-NC-SA4.0**. [MASt3R LICENSE](https://github.com/naver/mast3r/blob/main/LICENSE)도 같다. [공식 checkpoint notice](https://github.com/naver/mast3r/blob/mast3r_sfm/CHECKPOINTS_NOTICE)는 학습 데이터별 추가 조건을 명시한다. 공식 MASt3R README는 MapFree 조건이 특히 제한적이라고 설명하지만, 이번에 직접 받은 notice에서는 MapFree/Oxford 항목을 찾지 못했다(내장본과 원격본 모두). 따라서 존재하지 않는 Oxford 조항을 인용하지 않는다. CC 비상업 조건과 실제 notice의 추가 조건을 함께 보존하며 무조건 재배포 가능하다고 해석하지 않는다. 원문 URL·hash·이 불일치는 [license-sources.json](license-sources.json)에 기록했다. 이번 작업은 학술 비교다.
- lietorch `e7df86554156b36846008d8ddbcc4d8521a16554`, Python3.12 별도 venv, PyTorch2.5.1+cu124, CUDA toolkit12.9. 공식 Python3.11 예제와의 차이를 기록한다. [install.sh](install.sh)는 추론 의존성만 설치하며 기존 시뮬레이션 venv를 바꾸지 않는다.
- [실제 머신](gcp4-machine.json)은 **g2-standard-16 / NVIDIA L4×1 (23,034MiB)**. `configs/gcp_hosts.json`의 g2-standard-8은 이전 값이며 다른 작업자 설정을 수정하지 않는다. `maxRunDuration`/`terminationTime` 없음, idle20·기존 [budget-stop](budget-stop.json) 유지. CPU VM `ugrp-sim-gcp2` 시작·실행0. 비밀키·모델키·에이전트 자격 증명 VM 전송0.

## 입력과 계측

[`mast3rcmp_prepare.py`](../../scripts/mast3rcmp_prepare.py)는 manifest SHA256과 전체 프레임 SHA256을 검증하고 자기 RGB만 처리한다. K/D는 `harness/e2e_rgb_vo.py`와 같은 `sim/masterpi_camera_profile.py` 고정값이며 송신 측 파일 hash와도 일치한다. `cv2.fisheye`, R=I, Kout=K, 640×480으로 보정한다. 광학 중심을 지나는 원화 경계 광선은 수평60.2381°/수직44.4509°, 출력은54.4652°/42.0706°다. 수평 약5.773°·수직 약2.380°를 잃으며 출력 무효 픽셀0/307200이다. 이는 원화 전체의 단일 FOV가 아니라 중심 단면의 경계 광선 각도다. 공식 loader의 재중심화·긴 변512 resize/crop까지 적용한 **최종512×384의 중심 단면은 수평49.8008°/수직38.2161°**다. 원시 중심 단면에서 수평10.4373°/수직6.2348°를 잃는다. 최종K와 해상도는 [network-camera.json](network-camera.json)에 저장했다.

공식 알고리즘에는 알려진 핀홀 보정 모드와 보정 없는 central camera 모드가 있다. 이번 비교는 보정 영상+고정K, subsample1, 공식 single_thread=True를 사용한다. 논문은 MASt3R가 핀홀 영상으로 학습되어 강한 왜곡에서 예측이 나빠진다고 설명한다. [원본 파생 생성기](../../scripts/mast3rcmp_instrument.py)는 원본 hash를 강제 확인하고 원본 파일을 수정하지 않은 새 entry를 만든다. GUI import를 수동 기록기로 바꾸고 초기화·추적·재위치 추정을 전체 프레임에 기록하며 큰 검토용 재구성 출력만 생략한다. RELOC 가지에서는 미초기화/앞 프레임의 `add_new_kf`를 False로 초기화한다. 추적·대응·최적화·검색·수용 상수는 원본을 유지한다.

분모는 전체 입력 프레임이다. 초기화는 성공 수에 포함한 값과 별도 개수도 표시하고 실패/미처리를 영변위로 채우지 않는다. 온라인 자세와 최종 키프레임 그래프의 변환을 같은 참조 키프레임에서 각 자세로 전파한 궤적을 저장한다. 별도 최적화는 하지 않는다. 프레임 시간은 CUDA 동기화를 포함하고 시작/모델 로딩은 별도 기록한다. torch 할당자 peak와 모든 SLAM 자식을 포함한 GPU 전체의0.5초 표본 peak를 나눈다. 표본 peak는 순간 최대를 보장하지 않는다.

## 본 비교 평가 경계

추정 저장 후에만 평가용 정답을 받는다. ATE(a)는 정답 Sim(3) 척도 정렬의 참고값, ATE(b)는 자기 RGB로 고정한 바닥 mask+고정 카메라 높이·바닥 법선으로 정한 척도에서 SE(3) 정렬한다. 척도 산출 명령과 정답 채점 명령을 분리했다. 바닥 픽셀·고정 외부 보정이 불명확하면(b)는 unknown이며 학습 사전의 척도를 대신 쓰지 않는다. 평가 위치는 같은 시각의 **카메라 중심**이다. LK/RBPF의 차체 위치도 고정 외부 보정으로 평가 위치를 맞춘 뒤 나란히 비교한다. 방법·백엔드·호스트의 결과를 합산하지 않는다.

## 검증과 남은 작업

비물리 검사4개(분석적 척도 정렬, 실패 분모, manifest/이미지 변조 거부, 정답 없는 바닥 척도)와 Python compile/whitespace 통과. 주 가중치·검색 가중치 로딩과 실제 자기RGB 추적을 확인했다. 전체CI·본 비교·ATE는 아직 미확인이다. 첫 설치는 C++ 컴파일러 부재로 HOST_ERROR였으며 [거부 분포·수정](install-attempts.json)에 기록한 뒤 build-essential을 추가했다.

[재현 명령](reproduce.json), [순차 누적 funnel](rejection_table.json), [대기열](next-queue.json), [회수 SHA 대조](retrieval-verification.json)를 보존했다. 본 비교표는 본 녹화 추정·채점 후 추가한다. 원본은 gcp4 영속 디스크에 보존하고 프로젝트 예외에 따라 로컬/GitHub에 기록한다.


## mapbuild3 연습 결과 — 성능 비교 아님

실행 소스 `eb92fbd92812cbcb1cb0394ad48c6a63f85c504a`, 공식 core는 위 고정본 그대로다. [전체 요약](practice/practice-summary.json), [원본 파일 SHA 목록](practice/practice-raw-manifest.json). 두 영상은 각각 초기화1+추적40이며 전체41장 분모를 유지했다. 정답·명령·공용top 입력0, 평가용 정답 회수0, ATE 산출0이다.

|별도 영상|초기화/추적/실패/미처리|프레임 중앙값/평균/p95|GPU 표본 peak|모델·버퍼 준비/전체 실행|
|---|---|---|---|---|
|FOLDED drive-off|1/40/0/0 (N41)|0.1483/0.1812/0.3786초|9,274MiB|15.658/32.438초|
|HIGH high-off|1/40/0/0 (N41)|0.1609/0.1832/0.2884초|9,068MiB|15.618/32.417초|

프레임 시간은 이미지 decode 이후 추적·동기식 백엔드 완료까지다. 초기 프레임의 백엔드 큐는 공식 경로처럼 비동기다. GPU 표본은0.5초 간격으로 모든 자식 context를 포함하며 순간 최대 보장은 아니다. torch 주 프로세스 allocated peak는 두 영상 모두 약7.712GB, reserved7.969GB로 별도다. L4 용량23,034MiB 내에서 이 두 짧은 영상은 실행됐으나 긴 영상의 메모리 요구를 보장하지 않는다. 설치·연습 성공을 물리·HIGH 자격·지도/위치 추정 정확도 성공으로 확장하지 않는다.


gcp4는 자기 Python/MuJoCo/ffmpeg·GPU 프로세스0, 남은 lease JSON0을 확인하고 직접 정지했다. 다른 작업자의 오래된 `.warp9-claim.lock`·`.warp10-claim.lock`은 그대로 보존했다([종료 전 확인](gcp4-practice-close.txt)). [TERMINATED 확인](gcp4-after-practice-stop.json)의 `lastStopTimestamp`는 **2026-10-16T14:19:14.155Z (23:19:14.155 KST)**다. 실행 시간 상한 없이 idle20·budget-stop을 유지했다. 본 녹화가 도착하기 전까지 gcp4를 다시 시작하지 않는다.
