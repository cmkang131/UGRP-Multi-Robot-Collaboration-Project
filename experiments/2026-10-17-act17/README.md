# act17: ACT 학생 실패 원인 분리

PR #539 / `claude/act16w`를 이어받았다. **진단 중이며 학생 성공을 새로 확인한 결과는 없다.**
새 학습·물리 전에 native 원본, 저장 체크포인트 A/B/C/D1과 VAL 시연을 검사한다.
교사 40/40과 학생 FINAL 0/40을 구분하며, 이미 공개된 FINAL40은 이후 개발 진단 자료이지 새 확증 표본이 아니다.

## 재현과 입력 경계

- 개루프: `scripts/act17_open_loop.py`. 모든 TRAIN11860/VAL3026 시연 행에서 h0, 기존 actuator projection 뒤 h0, 유효 chunk, 이전 명령 유지 기준을 비교한다. 단계는 평가 메타데이터에만 쓴다.
- 폐루프: `scripts/act17_closed_loop.py`. A/B/C/D1 VAL8과 A FINAL40, 총72개 저장 상태. 각 원본 launch의 compiled geometry와 런타임 카메라를 복원하고 kinematics/ray만 계산한다. 새 물리 step·학습·렌더0.
- 교사 반사실 명령은 기존 `VisibleOracle`의 visible-only·pre-hover·잠재 집게 닫기 경계를 유지한다. 라벨이 없으면 사유를 기록하고 다른 궤적의 명령을 가져오지 않는다. CPU seven-probe 화면 이탈은 픽셀 인식이나 실패 인과의 증명이 아니다.
- wheel 오차는 발행 명령 full-scale 비율(무차원), duration은 ms, servo는 PWM count다. 실제 관절·바퀴·차체 변위 오차가 아니다. 원 명령 단위 변환은 contract의 `.15 s`, `1000 PWM`을 그대로 쓴다.
- 원본 `act17_open_loop.py` 첫 실행은 eval mode 손실을 `posterior_loss_sample_weighted`로 잘못 이름 붙였다. LeRobot ACT는 eval에서 z=0이므로 실제 값은 **prior-z0 eval 손실(KL 없음)**이다. 정리 결과에서는 이름을 바로잡고 실제 optimizer TRAIN 로그와 구분한다. 수치 재학습·수정은 없다.
- 91637의 안정 들기73.1초가 기하 정렬 proxy 탈락과 함께 존재한다. proxy40/40 탈락을 필요조건·실패 원인으로 쓰지 않는다.

실행 호스트는 `changmin5781@gmail.com / ugrp-sim-b-1014 / ugrp-act-l4-gcp2 (g2-standard-8)`다.
CPU VM·gcp1 시작0, Mac 학습·sim·render·GUI0. 공용 backend·접촉 프로필 수정0. 원본은 VM 영속 디스크에 보존하고 Mac에는 요약·검토 프레임만 회수한다.

## ACT 설정 대조

아래 공개 코드 값은 2026-10-17 직접 열람했다. chunk의 논문100과 프로젝트 영상90을 구분한다.
원 논문 알고리즘 상자와 구현 손실 설명에도 차이가 있으므로 실제 구현의 L1을 기준으로 적었다.

| 항목 | ACT 논문/ALOHA 공개 구현 | act16w 실제 설정 | 해석 |
|---|---|---|---|
| chunk | 논문 부록100, 사이트 영상90; CLI 지정 | 8 | 50Hz의2초 대10Hz의0.8초, 개수만 직접 비교 불가 |
| temporal ensemble | 선택 가능, 공개 eval `k=0.01`, 같은 시각 예측을 오래된 것부터 가중 | off | 실제 제어에서 새 영상 반영은8틱마다 |
| 관측·행동 주기 | 50Hz / 20ms | 자기 RGB10Hz·교사 명령10Hz; ACT 발행10Hz·재추론1.25Hz | 저장 주기와 추론 주기를 구분 |
| 영상 | 현재4카메라, 각640×480 | 자기 카메라1대의4시점; 각각320×240으로 축소한 뒤2×2 640×480 | 현재 프레임은 전체의1/4, viewpoint4개가 아님 |
| 영상 정규화 | RGB/255, ImageNet mean(.485,.456,.406), std(.229,.224,.225) | 같은 수치, montage 뒤1회 | LeRobot `predict_action_chunk`에 별도 중복 정규화 없음 확인 |
| state | 측정 joint14, 평균/표준편차 | 자기 발행16명령+task+clock252; TRAIN 통계, token 유지 | 측정 joint는 학생에 추가하지 않음 |
| 행동 | 절대 joint target14, 평균/표준편차, std최소.01 | wheel4+duration4+servo5+done; TRAIN 통계, 별도 done BCE | 표현·물리 단위가 다름 |
| backbone·transformer | ResNet18·encoder4/decoder7·512·head8 | ResNet18·encoder4/decoder1·512·head8 | LeRobot 변형이며 원 구조와 완전 동일하지 않음 |
| 학습 | batch8·lr1e-5·β10, 논문 약5h/RTX2080Ti | batch8·lr1e-5·β10·10000updates | GPU wall 시간만으로 학습량 동등성 추정 금지 |

출처: [ACT 논문 §IV·부록D](https://arxiv.org/html/2304.13705),
[저자 프로젝트](https://tonyzhaozh.github.io/aloha/),
[eval/ensemble 코드](https://github.com/tonyzhaozh/act/blob/main/imitate_episodes.py),
[영상 정규화](https://github.com/tonyzhaozh/act/blob/main/policy.py),
[행동·state 통계](https://github.com/tonyzhaozh/act/blob/main/utils.py).
우리 근거는 frozen ACT `3f99d58c5ada0862e669ef4065c0ba957f1b4547`의
`harness/grasp_act_{policy,data,contract}.py`, `scripts/train_act16w.py`, 저장 adapter/config다.

## 참고 자료와 검증된 방법

| 원 출처 | 시연·평가 보고값 | 우리 문제에 적용할 범위·한계 |
|---|---|---|
| [ACT/ALOHA, Zhao 2023](https://arxiv.org/html/2304.13705) | 대부분50시연/과제, Velcro100. 실제25평가/과제; Slot Battery96%, Open Cup84%, Velcro20% | 모든 과제가80–90%라는 식의 요약 금지. 현재 상태별 예측과 temporal ensemble이 핵심; 카메라·관측 차이는 유지 |
| [Diffusion Policy, Chi 2023](https://arxiv.org/html/2303.04137v4) | 실물 Push-T136시연·20평가, 소스 pouring/spreading50시연의90% TRAIN. 12과제 평균 상대개선46.9% | receding horizon·다봉 행동 분포의 근거.46.9pp 또는 우리 예상 성공률이 아님. 바로 알고리즘을 교체할 근거로 쓰지 않음 |
| [DAgger, Ross 2011](https://proceedings.mlr.press/v15/ross11a.html) | 학습 정책이 방문한 상태에서 전문가 라벨을 모아 누적 | offline 저오차와 rollout 성공이 다른 이유. 우리 h5는5427관측 중290(5.34%) h0만 있고 회복 전문가 전체를 검증하지 않음 |
| [HG-DAgger, Kelly 2019](https://arxiv.org/html/1810.02890) | 실차 첫5000샘플에서 BC 충돌1/이탈6, DAgger1/1, HG0/0 | 운전 실험이지 파지 성공률 아님. 전문가가 제어를 회복한 구간의 양질 라벨 수집 근거; 학생 fallback 허용으로 해석하지 않음 |
| [Mobile ALOHA, Fu 2024 §6](https://arxiv.org/html/2401.02117) | 통상50개 in-domain+static825 co-training;20평가. Wipe/Call95%, Cabinet85%, Rinse/Chairs80%. Cook20시연·5평가40% | 이동 후 정밀 정렬의 관련 사례. ACT co-training의 결과이며 우리32 TRAIN 시작·자기카메라-only로 수치를 이전할 수 없음 |

우선 비교할 처방은 **같은 ACT의 매틱 receding-horizon 재추론**과 **원 공개 구현 계수0.01의 temporal ensemble**이다.
8틱을 그대로 실행하는 기준선과 같은 체크포인트·VAL8로 비교하면 학습을 다시 바꾸지 않고 관측 반영 지연의 기여를 검증할 수 있다.
정렬의 개루프 tail 오차가 이미 크므로 이 처방만으로 학습 문제가 해결된다고 가정하지 않는다.
교사 라벨 경계 때문에 관측되지 않는58개 실패의 명령을 만들어 DAgger로 학습하지 않는다.
DAgger/HG-DAgger를 다시 사용하려면 TRAIN에서 실제 회복 시연의 가시성·held 감사와 성공을 별도로 확인해야 한다.

후보는 기본 off이며 최대3라운드다. VAL8을 먼저 수행하고 통과 전 FINAL40을 내지 않는다.
FINAL을 재평가하면 기존91620–91659와 별도 새 seed를 등록해야 한다. 학습/물리 성공·stack 선언 검사·CI는 별도 결과다.
