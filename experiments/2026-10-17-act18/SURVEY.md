# act18 조사: 구현 전 고정

기준 소스 `9924b9d28`, 최신 main `6bf55f43b`. act17의 v7 데이터만 재사용한다. 공개 저장소의 2026-10-17 조회 SHA와 파일 SHA-256은 `survey-sources.json`에 있다. 조사 자료는 성공 보장이 아니라 처방의 출처다.

| 항목 | 우리 act17 F/S | LeRobot ACT | ALOHA ACT / Mobile ALOHA | Diffusion Policy |
|---|---|---|---|---|
| 학습 길이 | 10,000 optimizer update, batch8 | 공통 train 기본100,000 update, batch8 | ACT 예제2,000 epochs; 어려운 실기5,000 이상, plateau 후3–4배 권고. epoch와 update는 다름 | 원본 hybrid 예제3,050 epochs, batch64; LeRobot preset은 별도 |
| 예측/실행 chunk | 8/8 @10Hz =0.8초 | 100/100, temporal ensemble 기본없음 | 예제100, ensemble 선택 시 매틱 재예측·계수0.01 | 원본16/8, 관측2; 최신 LeRobot64/32, 관측2. 둘을 섞어 기본이라고 부르지 않음 |
| 구조 | ResNet18 pretrained, d512/FF3200, encoder4/decoder1, CVAE32/KL10 | 동일; decoder1은 원본 decoder 재사용 문제를 따른 의도된 설정 | 소스 설정 decoder7이나 원본 구현의 실효 깊이와 구분 | ResNet18·조건부 U-Net·DDPM100, EMA; ACT와 다른 구조 |
| 행동 | wheel4+펄스4+PWM5+완료1, mean/std; 완료만 balanced BCE | mean/std·L1+KL | 관절 절대 목표, Mobile은 base 속도2를 추가; base는5샘플 이동평균 전처리 | [-1,1] min/max·noise MSE, multimodal 분포 표현 |
| 관측 | 자기640×480 RGB 한 장(F/S), 자기 발행명령252문맥. 측정 관절 없음 | state+카메라, ImageNet 정규화 | 실기 다중 카메라·측정 관절; 우리 입력 제한상 그대로 복제 불가 | 관측2·원본 crop76×76은 해당 벤치마크 설정; 카메라/FOV 변경 근거 아님 |
| 학습/추론 일치 | act17 원본 검사 통과, act18에서 같은 기록으로 재검사 | 동일 processor와 통계 재사용 | image/255 + ImageNet, ACT mean/std floor0.01 | min/max 범위와 inference clipping 일치 필요 |

원본 [ACT README](https://github.com/tonyzhaozh/act/blob/742c753c0d4a5d87076c8f69e5628c79a8cc5488/README.md)는 중간 정지·떨림 때 학습 연장을 먼저 권한다. [LeRobot 설정](https://github.com/huggingface/lerobot/blob/146d8474932c8b566717eb2738ba459337ab71c4/src/lerobot/policies/act/configuration_act.py)과 [학습 설정](https://github.com/huggingface/lerobot/blob/146d8474932c8b566717eb2738ba459337ab71c4/src/lerobot/configs/train.py)을 실제 읽었다. [Mobile ALOHA 학습 코드](https://github.com/MarkFzp/act-plus-plus/tree/26bab0789d05b7496bacef04f5c6b2541a4403b5)는 하드웨어 저장소와 구분했다. [원본 Diffusion hybrid 설정](https://github.com/real-stanford/diffusion_policy/blob/5ba07ac6661db573af695b419a7947ecb704690f/diffusion_policy/config/train_diffusion_unet_hybrid_workspace.yaml)과 [논문](https://diffusion-policy.cs.columbia.edu/)도 대조했다.

L1의 최적 점 추정은 조건부 중앙값이다. 서로 다른 모드를 **평균** 낸다고 쓰지 않는다. 주변분포에 양·음·정지가 많다는 사실만으로 같은 관측의 조건부 모호성을 입증하지 못한다. 기존 actuator projection의 `abs(w)<0.155`·pulse<1ms가 회귀 오차를 정지로 바꿀 가능성은 원본 예측의 raw/projected 수를 나눠 검증한다. 이 값은 새 상수가 아니라 고정 학생 계약의 기존 값이다.

순서는 (1) 원본 전체 TRAIN/VAL 명령 히스토그램·거부표, (2) 기존 F/S의 TRAIN 동일 목적 prior-z0 개루프와 TRAIN4 폐루프, (3) 그 결과로 후보2–3개를 고정하고 학습이다. 예정 후보는 공개 ACT 학습량/100 chunk와 Mobile base5 전처리이며, 데이터가 지지하지 않으면 이산 분류나 Diffusion으로 임의 교체하지 않는다. 모든 변경은 기본 off, 같은 TRAIN·VAL 시드, 허용 입력만 쓴다. TRAIN 적합 확인 전 VAL8 확대 금지, VAL8 8/8 전 FINAL40 금지.

실행은 gcp2 L4 `ugrp-act-l4-gcp2` / `ugrp-sim-b-1014` / `changmin5781@gmail.com`. wall 상한 없음, 유휴20분·현재 예산2,000KRW 정지 유지. 원본·모델은 VM 영속 디스크, Mac에는 요약·실패 재생만 회수한다. 새 시연 녹화는 현재 계획에 없다.
