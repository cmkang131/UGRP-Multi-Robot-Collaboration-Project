# mapbuild2 사전 기록

PR #556 DRAFT와 mapbuild1 worktree를 잇는다. 1→2→3 순차 관문, 4는 warp10 결과 전 WITHHELD.

- 실제 명령 주행: gcp2 L4 `ugrp-act-l4-gcp2`, shared 4세계(FOLDED/HIGH × 초음파 OFF/ON), 기존 v122의 forward .35/100ms, left .35/60ms, turn .35/100ms와 정지 꼬리. 4 SIM초는 자료 수집 범위이지 실행 wall 상한이 아니다. 사용자 결정에 따라 실행 wall 상한을 새로 두지 않는다. idle20/budget-stop 유지.
- 장면 `walls_floor_contrast_v5_indigo110_s80`, `no_mip_v1`, warp7 렌더 소스 `5974a181a2cec9731339a6ce3aadc0464b8dddcf` 고정. CPU 물리0, MJWarp 물리만. 공용 top은 평가 영상 파일에만 저장, 자기 manifest에는 넣지 않는다.
- 자기 RGB와 명령 v122 예측을 기록한다. HIGH closed는 보정 미자격을 유지하고 실제 운반 성공으로 주장하지 않는다. 초음파는 기존 센서 모델로 실제 Warp 상태에서 판독하되 상태/대상 이름은 입력에 전달하지 않는다. OFF/ON은 다른 실행 조건이다. 먼저 기록/추정 척도를 비교하며 보조 거리 융합을 했다고 보고하지 않는다.
- 전체10Hz 기록(4초 전체가 실패 직전10초 범위) + 기록 전용 고리 버퍼. 개요/r1/r2 병렬 3배속 ≤8MB 영상, 전체2Hz·마지막10Hz 띠를 gcp2에서 생성하고 파일로 직접 확인. Mac GUI0.
- 원인 주장 전 분포표와 시간순 검토를 작성한다. 표준 ORB BF Hamming/ratio .75/essential RANSAC은 OpenCV 공식 문서와 비교한다. 마스크·상호 대응·피라미드·해상도·블러·압축을 분리한 뒤 조명/밉맵/질감 후보를 다룬다. 기존 수용 상수는 바꾸지 않는다.
- 지도 생성은 1–2 관문 확인 뒤 자기 추정 pose와 RGB 벽 바닥 접점만 쓴다. 정답 지도 raster는 별도 평가기만 연다. 지도가 완성되지 않으면 unknown/누락 그대로 기록한다.
- 같은 결함3라운드면 중단·보고한다. 원본은 gcp2, Mac에는 요약·몽타주·실패 프레임/검토 영상만. 공용 bare 직접 참조 clone, 타 lease/PID 보존, VM정지0.

참고: [OpenCV matcher](https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html), [ORB](https://docs.opencv.org/4.x/db/d95/classcv_1_1ORB.html), [calib3d](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html), 2026-10-16 열람. ORB Hamming과 ratio .75, API 기본 피라미드·essential RANSAC 기본값을 비교 근거로 사용한다. essential의 단안 척도·평면 퇴화는 미터 척도 검증과 별개다.
