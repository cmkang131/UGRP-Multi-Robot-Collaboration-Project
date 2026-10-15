# rl1 — 고정 ACT 위 잔차 강화학습

Refs #523. 상태: rl1b WAITING_BACKEND, 개선 여부는 아직 미측정이다.
이 문서는 2026-10-16 사용자 승인에 따른 유한 DEV 시험의 사전 계획이다.

## 현행 범위: rl1b (아래 원래 rl1 계획보다 우선)

2026-10-16 사용자의 "너가 좀 휴리스틱을 주면 안돼?", "자고 올테니까 너가 알아서 계속 진행해줘!"에
따른 범위 축소다. act16w의 MJWarp ACT 추가 학습을 우선하고, 본 RL은 ACT16 위의 rl2로 미룬다.
이번에는 **고정 ACT15 + 제한 잔차의 신호 확인만**, GPU 준비/JIT/측정/학습/평가 합계 **최대1시간**이다.
기존 아래 2h/6h·N64→256 probe·전체40 평가 계획은 이번 예산에 적용하지 않는다.

- 새 시작918000–918039 중 첫8개(결과를 보기 전 고정)를 기준 ACT15와 짝 비교한다.
  모델은 예산 안 마지막 체크포인트로 고정한다. 단계 진척만 증가하면 완료 신호와 구분한다.
- h1–h3와 h4를 명시적으로 ON. 학습 신호만 사용하며 정책 관측과 GT 종료 가드는 추가하지 않는다.
  h5 DAgger는 act16w/후속 ACT 작업이며 이번에는 OFF다.
- h1: 실제 자기 왜곡 RGB에서 가림까지 확인한 대상 중심의 정규화 좌표를 사용한다.
  `1 - norm(x,y)/sqrt(2)`(화면 밖/가림은−1)을 900틱으로 나눈다. ACT15의90초에서 최대 절댓값1인
  학습 계수다. 중앙 영역을 나누는 임의 문턱은 없다. 성공 교사의 마지막 화면 밖 구간도 벌할 수 있다.
- h2: 안정 들기 전 **처음 발행한** done에−10(기존 성공 보상10과 동일한 학습 척도).
  GT로 done을 거부/지연하지 않는다. done 잔차 한도0의 제약을 그대로 보고한다.
- h3: `Phi_angle=-clip(abs(error)/pi,0,1)`의 signed discounted potential 차분.
  양수만 남겨 진동에 보상하지 않는다. 기존 기본 potential의 각도 항과 추가 가중됨을 명시한다.
- h4: 훈련 manifest의 거리·정면 각도 순위를 합쳐 난도를 고정하고, 전이 예산의 첫1/3은 쉬운25%,
  다음1/3은50%, 마지막1/3은 전체를 사용한다. 분포 사분위/예산 분할이며 성공 판정 문턱이 아니다.
  평가 manifest는 별도 고정하고 이 스케줄을 적용하지 않는다.
- 휴리스틱별 ON/OFF 보상 항을 같은 전이에 남긴다. 독립 재학습 ablation이 없으면
  정책에 대한 개별 효과는 `unmeasured`다. h4 효과도 성공률 변화로 추정해 채우지 않는다.

재사용 모듈: `scripts/rl_act_reward.py`, `scripts/rl_act_curriculum.py`, `scripts/rl_act_env.py`.
현재 env는 backend 주입용 계약 래퍼이며 **실제 MJWarp binding/부분 reset은 미검증**이다.
기존 미커밋 env/reward 원형은 `outputs/rl1b/imported-originals/`에 보존했다(실행하지 않음).
짧은 비물리 시험: `tests/test_rl_act_signal.py` 16개 통과; 평가에서 privileged read0,
GT 변경 시 actor 입력 불변, h2 중복 벌점 방지, 부분 reset의 래퍼 이력 격리를 검사했다.
이는 실제 GPU reset·actor 출력 바이트·물리 성공 검증이 아니다.

의존성은5분 간격·재시작부터최대8시간 확인한다. 예전 watcher는 warp Python 파일 추가만으로
신호를 냈으므로 수정했다. 이제 커밋의 reset+step API 또는 warp1 보고 줄이 있어야 trigger이며,
trigger 자체는 runtime admission이 아니다. 다른 작업의 worktree나 VM은 갱신·정지하지 않는다.

추가 확인한1차 자료(2026-10-16): [ResFiT 본문§III](https://arxiv.org/html/2509.19301v1),
[Ng1999 원문](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf),
[DAgger PMLR](https://proceedings.mlr.press/v15/ross11a.html),
[Reverse Curriculum 초록](https://arxiv.org/abs/1707.05300).
h1/h2 계수와 h4의 간단한 순위 스케줄은 이 논문이 입증한 값이 아니라 이번 pilot 설계다.

## 원래 rl1 계획 (이력; 위 rl1b 예산/평가 축소가 우선)

## 사용자 결정과 입력 경계

사용자: "그리고 강화학습도 시도해보면 좋을듯 지금부터. ACT가 있긴 하니까 그걸 강화학습하면 과연 좋아질지".
조정자 질문: "강화학습의 보상과 학습용 평가자(critic)에 시뮬레이터 정답(물체 위치·접촉·들린 높이)을 써도 될까요? 로봇 정책의 입력(자기 카메라·자기 명령)은 그대로 두고, 정답은 학습 중에만 씁니다".
사용자 선택: "학습 중에만 허용 (Recommended)".

- actor: 자기 RGB 이력·자기 **최종 합성 발행 명령** 이력·스킬/물건 종류/자리 번호표만.
- 학습 전용 reward/critic: 물체 위치·측정 관절·접촉·들린 높이 허용. 평가 actor에는 제공하지 않는다.
- critic은 학습 손실에만 사용한다. 실행 행동/청크/종료/카메라/스킬을 GT critic으로 고르지 않는다.
- weld OFF, 정상 물리, held_object_hidden_v1 유지. 학습용 정답 읽기를 이 감사의 위반 수와 섞지 않는다.
- ACT+잔차는 별도 DEV 후보다. 기존 ACT 하나의 기본 학생을 교체하거나 성공을 선언하지 않는다.

## 읽은 자료와 기준선

1. 로컬 조사: `outputs/e2e18-admin/research/rl.md`, `research/act.md`.
2. ACT16a: `../act16-analysis/experiments/2026-10-16-act16a/`(worktree 기준).
   GCP2 독립 재현 완료 0/40. 첫 거부: 접근15, 정렬22, 집기1, 들기확인2.
   조기 done 요청26, cap_end15(거부 범주와 별도 축). 인과 원인을 확정하지 않는다.
3. ACT15: `claude/act-train`의 `experiments/2026-10-15-act-train/`와 모델 registry.
   모델 ID `grasp-act15-dagger1-step10000-1535c8a3`.
   [Release ZIP](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/models-20261015-act15-1535c8a3/grasp-act15-dagger1-step10000-1535c8a3.zip),
   ZIP SHA256 `e39bf6b27f263bc699a6b3165461421c5f5062ab6fc0be5bc38f90f369fb77cf`,
   actor SHA256 `d90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1`.
   새 VM에서 재다운로드·ZIP/내부 파일 해시·로딩을 다시 검증한다. GCP1에는 접근하지 않는다.
4. warp1: `claude/warp-act`(초기 HEAD `142dbf04c2128c3d7ca1c3ceb03ee3b651d9a7e5`).
   새 배치 backend 커밋을 기다리고 **커밋된 API만** 사용한다. 실행 소스는 먼저 커밋한다.
   교사 전용 실행기와 actor step/reset/RGB API의 준비 상태를 구분한다.

MJWarp에서 ACT15의 같은 시작 상태 기준선을 새로 측정한다. C의 0/40을 MJWarp 분모로 옮기지 않는다.
warp1/warp2가 ACT16을 별도로 완성하면 SHA·Release·장면을 봉인한 별도 코호트로 비교하며,
ACT15 결과를 보고 유리한 모델로 몰래 바꾸지 않는다. ACT16 대기 때문에 ACT15 첫 시험을 미루지 않는다.

## 방법·행동 공간

1순위는 **ResFiT식 고정 ACT + 매 제어 틱 작은 off-policy 잔차**다. 원 논문의 완전 재현이라는 뜻은 아니다.
ACT와 시각 encoder를 동결하고 허용 RGB 이력의 공간 특징·정규화 명령 이력·base action·청크 위치를
작은 MLP에 넣는다. 0으로 초기화한 마지막 층, tanh 출력, twin LayerNorm critic, TD3식 지연 갱신을 쓴다.
처음에는 UTD1, batch128, MLP 2×256, n-step3, actor는 critic4회당1회, target tau=.005.
이는 ResFiT §III-C(n=3, LayerNorm, actor 지연2–8, tau=.005)와 자원상 작은 pilot 구성이다.
gamma는 0.1 SIM초 단위 .995(할인 반감 약13.8 SIM초)로 고정하고 남은 horizon을 critic에 준다.
GT actor/state encoder 공유·critic hidden 재사용은 금지한다. critic 입력은 detach한 허용 이력 특징 +
훈련 GT(대상 상대 위치/방향, 손가락 접촉, clearance/tilt, 관절/속도, 남은 시간) + 실제 실행 행동이다.

잔차는 ACT의 **역정규화된 14차원 출력**에 더하고 기존 contract decoder로 투영한다.
바퀴4, 펄스4, PWM5, done1을 구분한다. 펄스만 보정하면 22/40 정렬 실패의 반전 부족과
26회 조기 done을 고칠 수 없으므로 펄스 전용을 첫 후보로 고정하지 않는다.
각 차원의 한도는 gcp2 ACT16a 유효 교정 행에서 `abs(expert - base)`의 **0이 아닌 값 중앙값**으로
한 번 산출하고 JSON·원본 해시로 봉인한다. 이는 학습 크기 제안이며 성공 판정 문턱이 아니다.
차원별 표본이 없으면 그 차원 잔차0, contract의 기존 유효 범위를 넘지 않는다.
done 교사 label의 인과성이 없는 경우 done 잔차0으로 명시하고 조기 종료 한계를 보고한다.
기존 정렬 MAE 중앙 .195, pulse21.77ms, PWM51.6은 행 내 평균의 분포이므로
차원별 한도인 것처럼 재사용하지 않는다. 디코딩 전후 0잔차 일치·포화·부호 전환·실제 펄스 변화량을 잰다.
잔차 활성·한도·프레임 선택은 평가 단계나 GT 거리로 바꾸지 않는다.

대안은 동일 RGB actor와 잔차 범위를 쓰는 **ResiP식 PPO 잔차**다. off-policy 불안정이 실제로
확인된 후 별도 코호트로만 실행한다. ResiP의 원 state actor를 수입하지 않는다. DPPO는 diffusion
denoising 정책용이라 ACT CVAE에 직접 적용하지 않는다. 첫 2시간에 방법을 여러 개 갈아 끼우지 않는다.

## 보상과 에피소드

사용자가 요청한 밀집 보상을 첫 후보부터 쓴다(기존 조사문서의 sparse-first 제안을 이번 결정으로 대체).
훈련 GT로 거리 d와 정렬 각도 e를 계산한다. d의 정규화는 훈련 시작 거리 p95(봉인된 시작 manifest),
각도는 pi를 쓴다. `Phi=-(clip(d/d95,0,1)+clip(abs(e)/pi,0,1))/2`.
`r = 10 * first_stable_lift_success + gamma*Phi(next)-Phi(now)`.
성공 보상10은 무차원 shaping potential 범위1의 10배로 둔 pilot 계수다. 새 물리 성공 문턱이 아니다.
이 potential 차분은 같은 상태에서 접근/후퇴를 반복하며 무한 가점을 얻는 문제를 막는 표준 방식이다.
종료 absorbing potential=0, terminal/truncation 처리를 동일하게 해서 목적함수 변경을 막는다.
거리·각도별 return과 실제 성공을 함께 기록하며 reward 상승만으로 개선을 판정하지 않는다.
성공은 기존 LiftScore의 clearance≥.012m, tilt≤10도, 양쪽≥.5N, 3 SIM초 유지로 고정한다.
접촉 힘 자체에는 양의 보상을 주지 않는다. 순간 튀어오름·낙하·벽에 기대기·관통은 영상으로 점검한다.

제어0.1 SIM초, 기존 학생 done+3.1초 settle, grasp 상한90 SIM초를 유지한다(ACT15 실행 계약).
GT 성공으로 episode를 조기 종료하거나 다음 스킬로 넘어가지 않는다. GT는 채점/학습 손실 전용이다.
cap90은 유한 과제 horizon으로 terminal 처리하고 `cap_end`를 별도 기록한다.
세계별 RGB·명령/청크/잔차 memory·RNG·reward history·ring buffer를 reset한다.
배치 일부 reset이 다른 세계의 상태를 바꾸지 않는지 비교한다. 훈련과 평가는 서로 다른 환경 인스턴스다.

## 예산·공유 자원

- 처리량 probe: N64→128→256, 각 첫30 SIM초. 총량 `N×SIM초/wall초`, RGB포함/물리만·메모리·오류를 분리한다.
  측정 중 ≤40이라는 CPU 독립 실행 상한은 유지하고, GPU vector world는 N으로 별도 표기한다.
  메모리에 맞는 가장 큰 N을 **실제 측정**해 선택한다. OOM 시 자기 프로세스만 멈춘다.
- 첫 학습: 새 전이100k 또는400episode 또는 **누적2 GPU시간** 중 먼저 도달.
  최종 전체 L4 사용(설정·JIT·probe·학습·평가 포함) **6시간** 상한. 체크포인트/비용은 중간 저장한다.
- 10k/25k/50k/100k 새 전이에서 dev20을 기록하고, 시간이 먼저 차면 즉시 종료한다.
  vector tick 수와 신규 전이 수를 구분한다. UTD는 신규 전이당 갱신 수다.
- 기존 GCP1 시연은 사용 불가. gcp2에서 **실제 발행된** 유효 교사 전이를 회수할 수 있을 때만
  50:50 demo/online replay를 쓴다. shadow teacher label을 실행 행동으로 위조하지 않는다.
  재기록이 불가하면 online-only인 ResFiT 계열 변형으로 표기한다.
- raw replay20GiB·특징 replay2GiB·체크포인트2GiB·영상/고리버퍼4GiB의 계획 배분.
  이는 쓰기 상한이며 실행 전 `df` 및 다른 임대의 쓰기 계획을 포함해 여유를 확인한다.
- gcp2 프로젝트 `ugrp-sim-b-1014`, 계정 `changmin5781@gmail.com`만.
  L4 `ugrp-act-l4-gcp2` 임대를 공유하고 실제 메모리 부족이면 승인된 `ugrp-act-l4-gcp2b`를 검토한다.
  g2-standard-8, 8h STOP, 유휴20분, service-account/scopes 없음. 할당 없음은 대기로 기록한다.
- budget-stop 발동은 즉시 신규 제출 중지. 다른 호스트로 우회하지 않는다. 비용 집계 지연을 감안한다.
  현재 비용 정가추정은 기존 gcp2 L4 $1.096/h 가정(미검증 가격): 최대6h $6.576 + 디스크/전송 별도.
  실제 청구와 구분하며 신규 VM 전 가격/할당을 확인한다. 모델/에이전트 키는 VM에 두지 않는다.
- VM마다 `/home/ugrp/ugrp-sim/leases/rl1.json`에 작업·소유 PID·시작·예상 종료를 기록.
  종료 때 자기 임대만 지운다. 타 임대/타 python·mujoco·ffmpeg가 있으면 VM 정지하지 않는다.
- Mac 학습·물리·렌더·GUI0. 분석/ffmpeg는 gcp2에서 하고 요약·몽타주·검토 띠만 회수한다.

## 감사·짧은 시험·한 번의 조정

보상: 성공 교사1개와 실패2개의 전체 시간순 reward 성분·GT 평가를 비교하고,
동일 prefix에서 가까워짐/정렬 개선이 positive potential progress인지 확인한다.
성공 rollout return이 실패보다 높은지 원본으로 재집계한다. 부족한 사례는 만들지 않고 미확인으로 남긴다.
배포 actor는 simulator handle/critic/reward/eval 파일 없이 별도 프로세스에서 추론한다.
같은 RGB/명령/번호표/가중치/RNG에서 GT 파일을 바꾸거나 삭제해도 출력 바이트가 같아야 한다.
`forbidden_input_fields=teacher_input_fields=invisible_measurements=held_world_reads=top=0`가 필수다.
학습에서 허용된 읽기는 `training_privileged_reward_reads`, `training_privileged_critic_reads`로 별도 센다.
평가에는 critic/reward 입력 경로를 만들지 않고 success evaluator만 별도 저장한다.

기준 ACT가 0% 근처이면 거부 분포·영상부터 남긴다. 첫25k 전이에서 성공 전이가0이면
**초기 상태 커리큘럼만 1회** 변경한다(보상·성공 기준 유지).
쉬운 시작은 독립 교사가 실제로 성공한 상태의 사전 고정 분포에서 뽑고 GT로 행동하지 않는다.
원 시작 평가 분포는 그대로 두며 쉬운 시작 성공을 원 시작 성공으로 합치지 않는다.
조정 후에도 성공 신호가 없으면 NO_GAIN 또는 학습 미성립 사유로 멈춘다.

## 평가·판정·납품

훈련 seed=20261016. dev seed=917000–917019, 최종 새 시작=918000–918039로 구분하고
시작 manifest를 **학습 전에** 고정한다. 기존 ACT15의91420–91459는 알려진 실패 진단용으로만 쓴다.
모델 선택은 dev20의 완료 수 최댓값, 동률은 더 이른 checkpoint다. 최종40은 한 번만 비교한다.
같은 시작 상태·physics/scene/camera/command contract·horizon·seed로 ACT 대 ACT+RL을 각각40회 실행한다.
훈련 환경과 평가 seed/reset RNG는 분리한다. 이전에 본 시드는 새 시작 성공이라고 부르지 않는다.

총 n/N, paired 개선/악화 수, exact McNemar p, Wilson 구간, 성공률 차이와 불확실성을 보고한다.
IMPROVED는 새40에서 순성공 증가가 있고 입력/물리 감사 통과일 때만(탐색적 DEV, 통계 확증과 구분).
같거나 하락하면 NO_GAIN. backend/할당/자료/실행이 없어 짝 비교 미완료면 BLOCKED이고 n/N은 null이다.
정렬/접근 진척만 늘었으면 완료 개선으로 부르지 않는다. HOST_ERROR는 전 시도/비용에 남기고
동일 seed 재실행은 별도 ID; 미완료를 실패0이나 완료로 바꾸지 않는다.
후보→접근→정렬→집기→안정들기→완료 누적 관문표, 각 단계 거부 수·사유·물체·최소 틈,
cap_end·조기done·HOST_ERROR를 남긴다. 비기하 사유의 틈은 null과 `not_geometric`을 명시한다.
가능하면 C CPU에서 최종40 중 첫4개 seed를 별도 코호트로 비교한다. MJWarp와 합산하지 않는다.

실패2개·성공1개 개요+r1(+r2 해당 시) 3배속 몽타주를 gcp2 ffmpeg로 만들고 각≤8MB,
전체2Hz·종료 전10 SIM초10Hz 띠를 직접 읽는다. 성공이 없으면 없다고 기록한다.
실행기는 기록 전용 last10s/10Hz 자기 RGB ring buffer를 제공한다(제어/학습 카메라 불변).
`ffprobe`로 시간·스트림을 검증하고 `outputs/e2e18-admin/playback/rl1-*/`에 회수한다.
모델을 결과에 쓰면 가중치·adapter·기준 ACT 해시·설정·출처를 새 Release asset으로 보존하고
registry 갱신→재다운로드→전체해시→모델 로딩까지 확인한다. 완료 전에는 배포 완료로 표시하지 않는다.

## 출처와 열람 범위 (2026-10-16)

- [ResFiT 논문 v1 §III–V](https://arxiv.org/html/2509.19301v1),
  [저자 코드](https://github.com/amazon-far/residual-offpolicy-rl): 고정 BC의 per-step off-policy 잔차,
  n-step3·LayerNorm·지연 actor·tau·demo mixing 확인. 측정 관절 입력을 그대로 가져오지 않는다.
- [ResiP v2](https://arxiv.org/html/2407.16677v2),
  [저자 코드](https://github.com/ankile/robust-rearrangement): PPO 잔차 비교; 원 state actor와 우리의 RGB actor 구분.
- [Pinto et al. 2017](https://arxiv.org/abs/1710.06542): abstract의 full-state critic/image actor 경계 확인.
  이 논문이 우리 RGB+자기 명령 이력·TD3의 성능을 보장하는 것은 아니다.
- [Ng et al. 1999](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf): potential-based shaping.
- [DPPO v3](https://arxiv.org/html/2409.00588v3): diffusion denoising RL; ACT 직접 적용으로 인용하지 않음.
- 이 계획은 공개 논문의 완전 재현·학생 채택·교사95%·E2E·실물 성공을 뜻하지 않는다.

### 저장 보상 감사 (GCP2, 소스18c369ff)

기존 C MuJoCo 원장을 gcp2 CPU에서만 재채점했다(새 물리/학습/GPU0).
실패91427·91439의 첫 done53.2/22.1 SIM초에 h2−10이 각각1회 귀속됐고,
성공 교사91434에서 기존 안정 들기3초를18.7 SIM초에 충족해 성공 항+10을 확인했다.
이18.7초는 평가 성공 시각이며 교사의 RGB 들기 확인24.7초와 다르다.
교사는 release를 포함하고 ACT done 토큰이 없어 완전한 return 짝 비교를 만들지 않았다.
h1 mask·교사 정렬 원장이 없어 해당 항은 미측정, 성공 보상·실패 done 귀속만 확인했다.
기록 [saved-reward-audit.json](saved-reward-audit.json); 로컬/원격 SHA256
`f858e0c19f23e89214bf31c6a0ce7830afb589a3ab7289b420e9896b7114a3c0` 일치.
잔차 calibration도 원격 원본과 전체 SHA256
`03f38a61fa808e59c68775ba0417d7aa73426834e0cad9d671914ca5d57e72f1` 일치.

첫 저장 분석 d1c6b040은 교사 원장의 lookaround_view6건을 채점 행으로 오인해
KeyError(min_z)로 중단됐다(부분 산출물 원격 보존, 학습/물리0). 18c369ff에서
알려진 주석 이벤트만 분리하여 완료했으며 모르는 schema는 계속 거부한다.
이 저장 감사는 새로운 RL 신호나 h1–h4 정책 효과를 뜻하지 않는다.

### 학습 클라이언트 준비

`scripts/rl_act_actor.py`는 ACT15 해시를 고정하고 upstream ACT의 ResNet18·원래 역정규화·
원래 디코더를 그대로 쓴다. 자기 RGB montage에서4x4 공간 bin, 정규화 발행 명령, raw ACT 행동,
청크 번호와 자기 done latch만 잔차 입력에 넣는다. 보상·critic·시뮬 모듈을 import하지 않는다.
0잔차는 float64 raw base를 그대로 디코딩하고, 자기 done 이후에는 원래 정지/유지 계약을 따른다.

`scripts/rl_act_learning.py`는 세계별 n-step3 replay, twin LayerNorm critic, actor4회 지연,
UTD1용 update, zero-init actor, tau.005를 구현했다. GPU 학습 생성자는 gcp2 L4 metadata와
명시적 enabled를 요구하며 CPU/Mac 학습 fallback은 없다. 아직 실제 optimizer 실행은0이다.
기존 decoder의 바퀴 deadband·PWM 반올림 때문에 actor loss에서만 straight-through gradient를
쓰는 **pilot 근사**를 명시했다. forward/replay는 실제 디코딩 명령이다. 이 미분은 실제 물리 미분이나
ResFiT 원문 그대로의 재현이 아니며, 실제 GPU 손실·grad 검증 전 학습 준비 완료로 보고하지 않는다.

TD3의 Adam3e-4·target noise.2/clip.5는 [저자 코드](https://github.com/sfujim/TD3/blob/master/TD3.py),
straight-through 개념은 [Bengio2013 초록](https://arxiv.org/abs/1308.3432)에서 확인했다.
공간 bin4x4는2x2 시점 montage 각각에2x2 위치 bin을 보존하는 pilot 표현 선택이다.
LeRobot pinned source의 feature_map interface는 gcp2 설치본 commit89236ea0에서 직접 확인했다.
원문 GitHub raw URL 열람은 실패했으며 설치본 확인을 원격 원문 열람으로 바꾸어 쓰지 않는다.
비물리 시험15개에는 n-step terminal/collector truncation 분리·episode 간 credit 차단·0잔차 정밀도 보존이 포함된다.

### 저장 ACT15 명령의 0잔차 인수 (GCP2 CPU, 실행 소스46a5012d)

실패91439의 자기 입력240행을 두 번 실제 ACT15로 추론했다. 각 회차에서 새 클라이언트의
발행 명령240/240이 저장된 ACT15 명령과 canonical JSON 바이트까지 같았다. 서로 다른
private canary 복사본을 두고도 명령/허용 특징 해시가 동일했다. 이 canary는 정책에 전달하지
않았고 원본 정답 파일은 변경하지 않았다. 로드된 MuJoCo·보상·critic·환경 모듈0이다.
ACT 원본 `b4db8ba2`의 policy/contract/data는 `3f99d58c`와 diff0이며 model SHA는
`d90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1`이다.

[zero-residual-audit.json](zero-residual-audit.json)의 로컬/원격 SHA256
`76cb3e56aeafe727eb08d83235114ad8b0b0d2ec1ddddc15fab66e9e05310a3e`를 확인했다.
이는 CPU 저장 입력·0잔차 경로의 인수다. 실제 GPU·새 RGB·부분 reset·학습 후 정책의
정답 불변성은 아직 검증하지 않았다. 새 rollout/학습/GPU0이며 소유 임대는 제거했다.
배포 로더/actor-only export는 이후 정리로 분리했고 아직 산출된 잔차 가중치는 없다.

## 실제 연결과 한 시간짜리 진단 구간 (실행 전 봉인 규칙)

warp1의 GPU_SHARED_TIMING 보고 줄이2026-10-16 03:56 점검에서 감지됐다.
이는 actor/reset 준비 완료가 아니므로, 커밋2fd1490a의 공통 WarpTransport를 그대로 재사용하는
`scripts/rl_act_warp.py`와 엄격한 RGB JSON 클라이언트 `scripts/rl_act_rpc.py`를 추가했다.
GT는 별도 owner process의 채점·훈련 lane에만 있다. 평가 process는 reward/critic/env 모듈을
로드하지 않는다. 실제 GPU 검증 전이며, 새 물리/학습 결과로 보고하지 않는다.

한 시간 안의 신호 확인에 맞춰 **새 시작40개(918000–918039)의 첫8개**, S1 cyan_1의 동일 정적
모델로 추가 축소한다. 훈련40개는919000–919039다. 장면은 기존 ACT15의 frozen6f/floor_light_v1으로
봉인하며, 선택된 v5 장면의 ACT16w와 합산하거나 그 장면의 RL 결과로 보고하지 않는다.
이 선택은 새 결과를 보기 전, 동일 모델 묶음·짧은 예산을 위한 것이다. 다중 장면/물건 일반화가 아니다.

- 실제 물리 owner는 기존90 SIM초/학생 done+3.1초를 유지하고 GT 성공으로 중단하지 않는다.
- 첫 측정은 훈련 시작8개의 **한 ACT 청크8틱**이다. 그8틱의 최대 전체 틱 시간과 남은 GPU 예산으로
  `prefix_ticks=min(900, floor(remaining/(4*max_tick_wall)))`를 정한다. 세 비교/학습 단계와
  갱신·저장 여유에 각1/4를 배정하는 자원 계획이며, 물리 성공 문턱을 바꾸는 값이 아니다.
  owner 종료 wait30초+terminate10초는 자원 예약으로 빼고, 제어·계획은 고정된 SIM틱만 쓴다.
- 이 구간을 **학습 전에** prefix-seal.json으로 봉인하고 기준 ACT와 잔차에 동일하게 적용한다.
  구간 결정에 성패·GT 보상·새 평가 결과를 쓰지 않는다. 평가 시작은 아직 보지 않는다.
- 훈련은 그 총 틱을3등분한 수집 구간이다. 분포는h4의25%→50%→전체로 넓히며,
  수집 구간 끝은 collector truncation(bootstrap 유지), 실제90초/학생 종료는 terminal로 구분한다.
- prefix가3개 curriculum tier×2개 ACT 청크(48틱)도 못 담으면 예산 부족으로 BLOCKED다.
  이는 초기 청크/첫 동작을 각 tier에 담는 계산량 하한이고 새로운 파지 수용 상수가 아니다.
- prefix에서 끝나지 않은 과제는 cap_end이며 실패0으로 확정하지 않는다. SIGNAL/NO_SIGNAL은
  **같은 prefix에서 관측한** 안정 들기·관문 변화에 한정한다. 전체 과제 성공 여부는 별도 미측정이다.
- GPU vector 진단은 CPU 독립 실행의30 SIM초/6.0 지연 관문을 명시적 override 사유와 함께 기록한다.
  per-world wall/SIM과 aggregate SIM/s를 둘 다 남기며 GPU1h 한도·예산 정지는 우회하지 않는다.
- 새 경로는 공통 manager의 `rl-act-signal`로 등록한다. 모든 실행은 커밋·push한 source,
  exact-XML C312 geometry/damping, 실제 library 버전, 모델·설정·시작 manifest 해시를 기록한다.

h1의 실제 연결은 frozen BandVisibility의 기존7개 probe/raycast로 가림을 확인하고 실제 자기
fisheye의 대상 중심 투영을 쓴다. 화면 경계/근평면/카메라 보정은 원래 값이며, 새 CV threshold를
만들지 않는다. mask centroid 도우미와는 별도의 geometric-probe annotation이며 인식 신뢰도가 아니다.
실행 뒤 영상을 보지 않고 이 label의 정확성이나 원인을 확정하지 않는다.

GPU reset은 설치된 공개 `mujoco_warp.reset_data(..., reset=world_mask)`를 사용한다.
다른 세계의 integration state와 RGB 바이트가 즉시 같은지 검사한다. 다음 틱 동역학의 완전한
비트 동등성은 이 짧은 인수에 포함하지 않으며, 채택/장기 rl2 관문으로 남긴다.
