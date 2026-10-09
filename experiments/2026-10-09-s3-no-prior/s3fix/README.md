# S3 v147 수정·재시험 사전 기록 (2026-10-09)

19:22 KST, **아래 후보 결과를 보기 전 결정**: `s3_dev_light=continue_estimate_v1`, `global_diversity=kld_augmented_v2`, `mode_head_look=mode_information_v1`을 새 v147/7.40.0 혼합 스모크에 켠다. 모두 독립 옵션·기본 off이며 v142/v146 원본과 기존 hash-pinned 소스는 보존한다. seed14201(로봇별 기존 +0/+1/+2), 수렴 σxy≤0.05m/yaw≤5° 및 posterior 인증 기준은 바꾸지 않는다. 정확성은 eval_only XY≤0.25m/yaw≤15°. 실패를 보고 seed나 수치를 골라 바꾸지 않는다. 구현 버그는 별도 기록 후 고칠 수 있다.

## 표준 방법과 고정 후보

- [Fox 2003 KLD-sampling](https://www.robots.ox.ac.uk/~cvrg/hilary2005/adaptive.pdf) §3.2: 점유 bin 수로 표본 근사 오차를 제한한다. 기존 .5m/.5m/10° bin, epsilon .05, confidence .99 유지. 초기/상한을100000→400000, 최소를2000→8000으로4배 확장한다. 두 모드에 더 많은 표본을 배분하려는 자원 설정이며 두 모드 보존을 수학적으로 보장하지 않는다. 처음100000개를 보존하고 같은 RNG의 독립 map-uniform300000개를 추가한다. seed 선택·GT 주변 샘플링·모드별 임의 quota 없음. 움직임 시작 후 기존2000 tracking handoff 유지.
- [Nav2 AMCL pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)의 Augmented MCL: alpha_slow=.001/alpha_fast=.1, 주입확률max(0,1-w_fast/w_slow), map-uniform pose. 기존 EMA 수치 유지, 새 옵션에서는 Nav2/Probabilistic Robotics Table8.3의 매 관측 재표본화와 KLD 종료 규칙을 사용해 ESS가 높아도 recovery를 우회하지 않는다. 우도 바닥값·고정 주입률 추가0. Probabilistic Robotics §8.3.5 본문 직접 열람은 미확인, 공개 Nav2의 p258 주석과 실제 식은 확인했다.
- [Burgard/Fox/Thrun IJCAI1997 active localization](https://www.ijcai.org/Proceedings/97-2/Papers/080.pdf) §3: 예상 posterior entropy가 작아지는 센서 방향을 선택한다. 기존 자기 posterior/정적 지도/카메라 보정만 사용한다. 최대512개 가중 대표 표본, 보이는5개 열의 예측 벽 경계 센서로 모드와 관측의 상호정보량 합을 순위 proxy로 쓴다. 원래5 pan 완료 후 연결 모드가 여럿이면 기존 허용 wrist pan700/2300 중 미관측 방향을 최대2개 추가한다. 전체 기존120초 관측 예산 유지. 예측 시야는 필터 관측으로 주입하지 않는다. 새 RGB를 실제로 받아야 위치 개선 근거가 된다.
- DEV 진단은 검사값을 그대로 저장하고 veto만 우회하는 log-only 정책이다. 기존 pair own estimate·상태·발행 명령으로 진행하며 GT나 성공 인증을 만들지 않는다. σ 예산/관측 시한/위치 불확실/재관측 횟수 소진과 가드는 기록 후 진행, GO 합의·실제 명령/프레임 오류·짐 낙하/기울기/집게 이탈의 기존 실제 실패 감시 경계는 유지한다. 정식 경로는 옵션off로 기존 보수적 정지를 유지한다. 새로운 물리 감지기를 GT로 제어에 넣지 않는다.

## 고정 검증 집합과 실행 예산

저장 입력 재생은 v146 r1 seed14201 및 S2 v141 graduation seed1065–1070 전부, 원본 자체 seed/명령/영상 그대로, 처음14.00 절대SIM초까지만 비교한다. 모드 head 관측은 원본에 없는 새 영상을 만들 수 없으므로 저장 관측에 대한 선택 순위만 검증하고, 위치 수렴의 전후 비교는 동일 RGB/명령에서 입자 옵션 효과로 구분한다. baseline/candidate 첫 σ 수렴 시각·오차·yaw·허위수렴 수, 마지막오차와σ, sample/injection counts를 보존한다. 재생은 simulation0·GT 평가만. 보정한v142 원본 r1도 필요시 같은14초 범위의 보조 진단으로만 사용한다.

새 물리 스모크는 **1회**, v3 host binding on·heading 기본on·main#420 relay-cache-v1·dev_light. no dock prior/weld/top/GT control. 본 연구와 agent_lock 순서 공유, SIM1800초/wall10800초·raw3GiB+10GiB reserve. ENOSPC는HOST_ERROR, 자동 재시도 없음. 관련 시험초록→커밋/push→실행, CI 완료 대기 없음. [전체 번호 예약](reservation.json), 최신main6813f8a1 포함. 결과는 실패도 로컬raw와TensorBoard에 기록한다.
