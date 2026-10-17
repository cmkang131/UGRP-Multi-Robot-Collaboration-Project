# v7 R1 결과: NOT_READY

M/F/S는 같은 VAL8에서 모두0/8이며 안정 들기·놓기도0/8이다. FINAL 진입 후보가 없어 새 FINAL40은 실행하지 않았다. 본 연구 비교는1라운드이며, 추가 학습/물리 라운드를 근거 없이 제출하지 않았다.

|후보|요청/관측완료|grasp 완료 신호|안정 들기|안정 놓기|배정 물체 성공|같은 종류 아무 물체 성공|전체 완료 신호|cap_end|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|M|8/8|4|0|0|0/8|0/8|3|5|
|F|8/8|5|0|0|0/8|0/8|5|3|
|S|8/8|1|0|0|0/8|0/8|1|7|

각 후보의 cyan/red/green/yellow는 모두0/2다. 시작 시 같은 종류가 두 개 이상 보인 경우는 pixel/probe/qualified 세 기준 모두0/8 고유 시작(반복 세계0/24)이다. 이8시드의 첫 장면 중복색 모호성을 실패 원인으로 삼을 근거는 없다. 이후 장면 전체의 물체 식별 성공을 보장하는 결과는 아니다. 완료 신호9회와 cap_end15회를 따로 보존한다.

[독립 재계수](results/validation-independent-r1.json), [시간순 누적 funnel](results/validation-rejection-table-r1.json), [전체 단계 funnel](funnel.json), [실제 대기열/stack PASS](results/validation-stack-check-r1.json), [NO_VAL8_PASS 판정](results/selection-r1.json)에 원본 경로·SHA·재현 명령이 있다. 배치의 complete는 정해진90 SIM초 또는 종료까지 관측했다는 뜻이며 물리 성공이라는 뜻이 아니다.

## 원인 분리

[개루프 표](results/error-table-r1.md)는 세 후보 각각 VAL14528행을 평가했다. 정렬889프레임의 wheel median/p90은 M0.0275/0.35, F0.0272/0.35, S0.0197/0.35 full-scale이며 servo p90은54/54.6/51 PWM counts다. 마지막 자기 명령 수치 참조의 wheel p90은0.175, servo p90은0이다. 이 참조를 실행 정책이나 가드로 사용하지 않았다.

교사 이동 wheel component2856개 중 학생 정지는 M307/F525/S357개, 반대 부호는167/202/150개다. 정렬 완료 오탐은0이라 이 구간 wheel 오류를 완료 신호 탓으로 돌릴 수 없다. 실제 TRAIN 마지막100개 optimizer 로그 평균0.42457/0.48398/0.28335와 VAL prior-z0 손실0.23473/0.22269/0.28947은 서로 다른 목적이므로 단순 gap으로 해석하지 않는다. S는 TRAIN 표집도 달라 TRAIN 로그만으로 우월하다고 판단하지 않는다.

따라서 **폐루프 누적만의 문제는 아니다. 교사 상태에서도 학습 적합도·표현·데이터에 관한 문제가 남는다.** 초기24세계의 RGB 바이트/252차원 명령 문맥 일치, TRAIN/추론 전처리 일치, RGB/라벨 시각차0, 직전 명령 이력 대조는 통과했다. 이 검사가 모든 버그 부재를 증명하지는 않는다.

[실패24개 이탈 직전 표](pre-exit-comparison.md)는 학생·같은 상태 교사의 회전 부호와 크기, 실제 차체 heading 변화를 구분한다. 유효 교사 라벨은8/24 창에만 있고 나머지16/24는 미확인이다. 전체 저장 관측15124개 중 유효 라벨1268개, potential-hold 제외13856개이며 invisible_measurements=0·held_world_reads=0이다. 이는 기존 pre-hover counterfactual 범위의 감사이며 실제 DAgger 회복 시연을 새로 수집했다는 뜻이 아니다. 기존 DAgger의 유효290/5427(5.34%) 한계도 해소됐다고 주장하지 않는다.

발행 명령 부호 분류는 왕복8/정지4/한 방향12다. 작은 부호 반전까지 포함하므로 실제 차체 진동으로 바꾸지 않는다. F88646은 학생 `+++++++++-`, 교사 `-------000`, 실제 차체 Δyaw+5.672415도라는 반례다. 7-probe 기하 FOV 이탈은 픽셀 인식/접촉/유일한 실패 원인이 아니며 성공 교사도 파지 중 대상이 화면 아래로 사라진다.

## 직접 본 재생

[실패 M88623](playback-student-M-88623-review.json)은0–90 SIM초 전체2Hz와80.1–90초10Hz를 모두 봤다. 노랑 목표가7초 부근 화면 아래로 빠진 뒤 빨강 물체 쪽으로 가며, 후반은 바닥과 빨강 가장자리를 보고 정체한 채 cap_end다. [실패 F88620](playback-student-F-88620-review.json)은0–14초 전체2Hz와4.4–14.3초10Hz를 봤다. 목표가 왼쪽으로 빠진 뒤 회복하지 못하고,11.2초 부근 시야가 위쪽 벽으로 바뀐 뒤14.3초 완료 신호로 끝난다. 둘 다 native 안정 들기0이다.

[동일 시작의 성공 교사88620](playback-teacher-88620-review.json)은0–40.5초 전체2Hz·30.8–40.7초10Hz를 봤다. 접근 후8.5–30초 무렵 화면 아래 비가시 구간과 내려놓은 뒤 실제 좌우 둘러보기 순서가 있다. 이 구간을 짧다고 표현하지 않으며 학생의 초기 정렬 실패 원인이라고 단정하지도 않는다. 성공은 별도 native Score로 확인한 교사 결과이며 자기 RGB만으로 높이/접촉을 채점하지 않았다. 수정된 overview는 정확한 compiled geometry를 적용했고 원 자기 RGB는 재인코딩하지 않았다.

재생은 GCP ffmpeg 3배속·각8MB 이하, ffprobe 확인 후 프레임 띠를 파일로 읽었다. Mac GUI/플레이어/시뮬레이션/렌더0이다. [회수64파일 전체 SHA/크기 검증](results/delivery-verified-r1.json)과 개별 재생 기록에 위치·해시가 있다.

## 처방 비교와 남은 범위

ACT 공개 코드의 episode 균등/시연 내 시각 균등 표집과 현재 원해상도 RGB를 적용해 M→F를 비교했고, 종류별 TRAIN50시연을 확보했다. S의 네 단계 균등25%는 별도 가설이다. [문헌/설정 대조](../README.md)의 ACT/ALOHA·Diffusion Policy·DAgger/HG-DAgger·Mobile ALOHA 수치를 우리 성공 보장으로 옮기지 않는다. 우리의1 decoder·10k update·단일 자기 카메라/명령 이력은 원 논문 전체 재현과 다르다.

이번 변경으로 학생 성공은 얻지 못했고 M/F/S 모두 채택하지 않는다. 원래 제안한 replan1/temporal ensemble0.01은 같은 모델의 관측 반영 지연을 검증하는 다음 후보지만, 남아 있는 큰 개루프 오차를 해결한다고 가정하지 않아 추가 물리를 제출하지 않았다. 더 긴 표준 ACT 학습이나 구조 비교는 새로운 사전 고정 라운드로 구분해야 한다. 손으로 짠 근거리 경로/가드, 정답 학생 입력, RL은 추가하지 않았다.

## 보존과 검증

실행 source는 교사 gate be39af6fc, 기록 pilot5160938e5/bulk376fa86c0, 변환2ac6e7027, 연구 학습e1b7de0f7, 실제 VAL de6170d93, 최종 저장 상태 감사b798247ba다. 모두 gcp2 L4 g2-standard-8, warp_native_contact_v1/hash a5c8d3707·CPU/GPU noslip0·weld OFF다. 다른 호스트/과거 v4와 합산하지 않았다. 분석의 C kinematics/rays는 저장 상태를 읽었으며 물리 step·학습 추가0이다.

세 모델은 [공개 Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261017-act17-v7-r1)에 실패 비교 자료로 보존했고, 새 checkout 익명 다운로드·3 ZIP/69파일 전체 SHA·bundled CPU 로딩3/3을 검증했다. [배포 증거](results/release-r1/public-verification.json)는 실제 과제 성공과 별개다. raw 학습자료 전체는 VM 영속 디스크에 남고 Mac에는 가중치/원 상태/tensor를 가져오지 않았다.

분석 첫 시도는 v4 전용 scene 문자열 registry 때문에 시작 전에 멈췄고, 같은 v7 adapter를 재사용한 재시도로24개를 완료했다. 압축 기록 reader 실패·원본 실패 driver도 보존했고 연구 비교 라운드로 세지 않는다. [재시도 기록](results/closed-loop-attempts-r1.json)·[복구 완료](results/postprocess-r1-recovery.json)를 참조한다.

짧은 비물리 검사17개와 분석 수정 뒤 admission 검사1개가 통과했다. CI·독립 검토·PR 병합은 별도로 확인한다. 다른 lease/연산/GPU process0과64파일 회수 검증 뒤 L4를 정지했고 [TERMINATED](results/vm-stopped-r1.json)를 확인했다. budget-stop/idle20은 변경하지 않았다.
