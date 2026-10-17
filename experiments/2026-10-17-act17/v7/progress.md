# v7 진행 기록

2026-10-17: v4 예외 없이 v7 별도 관문·240기록·변환을 완료했다. M/F/S 각10000 update·저장 재로딩을 완료했다. 동일 VAL8×3 실제 native 평가와 VAL14528행 개루프 측정 중이다.

| 단계 | 완료/요청 | 확인 범위 |
|---|---:|---|
| 학습카메라 OFF native 교사 관문 | 40/40 | 각 종류10/10, Score 재계산·실제XML·native noslip0·입력감사 위반0, manifest8226파일 |
| 기록 pilot | 4/4 | 실제10Hz JPEG·명령·라벨, 네 종류 각1, 원본Score·입력경계 재계산 일치 |
| 실제 pilot 학습 준비 | 3/3 경로 | M/F/S 실제 전처리 배열일치·각1회 준비 gradient·저장재로딩 동일 예측, 연구모델 아님 |
| 나머지 기록 | 236/236 성공 | 원본Score·실제XML·native0·held/invisible0 재검사, controller manifest48424파일 검증; pilot포함240/240 |
| 데이터 변환 | TRAIN200·VAL40 시작 | TRAIN72572행/VAL14528행, 정렬4412/889행, TRAIN만으로 정규화, 실패 시연 제외0 |
| 연구 학습 | M/F/S 3/3 완료 | source e1b7de0f7, 각10000 update·같은 seed·실제전처리일치·체크포인트 재로딩 검증 |
| 학생 VAL8 / FINAL40 | VAL24 실행 중 / FINAL 미제출 | source de6170d93, 네 XML 그룹 총24세계·각 후보 같은8시드; 최종 완료 전 성공률 미집계 |

첫 준비 시도는 Scene.build가 빌드 전의 메타데이터 주석을 덮어써서 중단했다. 실제 XML은 v7이었다.
원본을 고쳐 쓰지 않고 converter가 실제 최종 XML·정적 시나리오 해시를 확인하도록 수정했다.
이후 기록에는 주석도 최종 transform에서 남긴다. XML·교사 동작·접촉·카메라 변경은 없다.
두 번째 준비 시도(270164c89)는 세 경로 모두 통과했다. 이는 준비 재시도이며 연구 비교 라운드는 아직 시작하지 않았다.

닫힌 pilot은 JPEG를 재인코딩하지 않고 동일 바이트 파일을 hardlink로 공유하고,
64KiB 초과 JSON은 전체 해제 SHA를 확인한 zstd로 보관했다. 기존 producer manifest의 원 바이트 해시는 유지한다.
기록 무결성 검사는 압축된 파일의 해제 해시를 읽는다. 원본 이미지 경로·바이트와 과거 v4 자료는 보존했다.

증설 전 여유10.60GiB에서 남은236회·모델 예약량5.05GiB를 빼면5.55GiB여서 제출을 막았다.
조정자가 ops-alert.md에서180→200GiB 증설을 승인·실행했다. 잠시 L4를 직접 정지한 뒤 재시작했고,
200GiB 디스크/199GiB ext4 루트 자동확장, 여유29.96GiB·예약후24.91GiB를 확인했다.
수동 growpart/resize2fs는 실행하지 않았다. idle20 timer·budget-stop은 유지한다.
공식 서울 SKU 공개가에서20GiB 추가는 크레딧·세금 전 월 약3533원(730h 기준 하루116원)이며 실제 순청구액과 구분한다.

[관문별 표](funnel.json)는 현재 기록/프레임/표적/모델/평가 단위를 나눠 담는다.
[증설 전 표](funnel-pre-resize.json)·[증설 전 차단 대기열](next-queue.json)은 당시 상태를 보존한다.
실제 제출 대기열과 stack PASS는 [results/bulk-runtime-queue.json](results/bulk-runtime-queue.json),
[results/bulk-stack-check.json](results/bulk-stack-check.json)에 있다. [디스크 예약 재검사](results/record-budget-r2.json)는 PASS다.
원본은 `/home/ugrp/ugrp-sim/runs/act17-v7/`에 있고 Mac에는 요약·대표 재생만 가져왔다.
실행 SHA는 gate be39af6fc, pilot5160938e5, 준비270164c89, bulk376fa86c0이다.

변환 Source2ac6e7027, 학습 Sourcee1b7de0f7은 같은 고정 학습·전처리·정책·평가 코드를 사용한다.
RAW106060행→지원하는 근거리87100행, 미래표적696800개→padding 제외683360개다.
스킬 밖18960행과padding13440개를 별도 사유/단위로 남겼다. 원본은 버리지 않았다.
[시각/명령이력 감사](results/dataset-timing-audit-r1.json)는 선택87100행의 RGB·관측·현재라벨 시각차0을 확인했다.
초기240행을 뺀86860행에서 마지막 자기 명령은 과거 시각이고, 라벨이 바뀐32299행 모두 마지막 이력이
현재 라벨 대신 직전 라벨과 정확히 일치했다. 이 로그 대조에서 한 틱 밀림·현재 라벨 누수는 발견하지 못했다.
[회수 증명](results/retrieved-r1/retrieval-verified.json)은 선택 요약14파일 SHA와 압축4개 전체 해제 SHA 일치를 확인했다.
원본 이미지·state·tensor·모델 가중치는 Mac에 회수하지 않았다.
기록 본 실행12그룹의 첫30 SIM초 지표 중앙값은0.45064 wall/(SIM×owner world), 원 배치 지연 중앙값은10.7892 wall/SIM이다.
[실측](results/bulk-first30-timing-summary-r2.json)은 기록용이며 통제된 가속 비교·실제 성공의 근거로 쓰지 않는다.

main4bb02030b의 gcp2 정지예산2,000KRW 후속 사용자 결정을 확인했다. budget-stop과 idle20을 유지하며,
이 문서에 실청구액을 추정값으로 채우지 않는다. [닫힌167회 요약](results/record-progress-167.json)은 중간 증거다.
gate/pilot/bulk와 준비 시도에 RUN_META 보존 분류를 소급 추가했다(실제 추가시각 표시, 원 채점·시각·해시 변경 없음).
완료된 관문은 milestone, 재현할 v7 학습자료 기록은 study, 임시 준비 시도는 dev로 구분한다.

[실제 평가 초기 입력 대조](results/initial-runtime-parity-r1.json): 같은 VAL8×3의24세계 모두 첫 RGB SHA와252차원 자기 명령 문맥 배열이 교사 기록과 정확히 일치했다. 이는 시작 입력 대조이며 이후 관측·동작·성공을 보장하지 않는다. [학습 완료 원장](results/training-complete-r1.json)은 M/F/S 각각10000 update·실제 저장 재로딩을 확인한다.
