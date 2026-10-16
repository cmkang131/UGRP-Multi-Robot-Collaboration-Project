# rlprep — ACT 위 RL 준비 설계 (2026-10-16)

**설계·비물리 골격 완료 / 실제 학습·배치 통합 NOT_READY.** PR #530의
`3c02a1af1ca60a54bf9733c76948c62eafceb018` 위에 추가했다. 이번 작업의 GPU 기동·물리·렌더·
학습 갱신·모델 호출·GUI 실행은 모두 0이다. 기존 rl1b의 8틱 GPU 진단은 이번 결과가 아니다.
사용자는 학습 중 정답 보상/특권 critic을 허용했고, 정책 입력은 자기 RGB·발행 명령 이력·
스킬/물건/자리 번호표로 유지하도록 했다. **이번 요청은 준비만 하며 ACT 관문 전 학습 금지**다.

## 확인한 현재 근거

`inputs.json`의 조회 시각·원본 경로·전체 SHA256을 기준으로 한 로컬 저장 기록의 확인이다.
gcp2 원본 재계수나 새 폐루프 재검증을 하지 않았다. 아래 두 모델의 시도는 합산하지 않는다.

| 후보 | validation wheel MAE / persistence | 저장 폐루프 결과 | 이번 준비의 판단 |
|---|---:|---:|---|
| beamact2 | .054589 / .023129 | 0/20 | persistence 미달 |
| beamact3 A | .022876 / .023129 | 0/20, cap_end20 | wheel만 개선; 실행 성공 없음 |
| beamact3 B | 진행 중인 로컬 기록 | 최종 결과 미확정 | 미완료를 통과로 세지 않음 |

beamact3 A의 학생 실행/재계수 소스는 `5ad43e1e096822d7a4ed2e7ce720c2900e7f5ff6`,
모델 SHA는 `e5c48771f03660b20cff525515cddb6cf82566c2797b2d89a8b57a9c17e27650`이다.
이 비교 세트는 이미 본 20시드로 새 확증 자료가 아니다. wheel MAE 개선을 pulse/PWM·
전체 행동·물리 성공으로 확대하지 않는다. RL 대기를 유지한다.

warp3 `RECORD_API_READY.json`은 source `0362037280c6cbc4677f70366db43b9892b23690`,
controller `f0db6b1abb842ea65b71c433738210254f300a7c`의 marker다.
원본 바이트를 `warp3-record-api-ready.json`에 보존했다. 실제 형식은 `ready`와 `proofs`이며,
`backend`/중첩 `gate.n` 필드는 없다. 이 작업은 **marker 구조·해시만** 확인했다.
그 marker도 bitwise trajectory·전체 학생 평가·대량 기록 승인을 명시적으로 보장하지 않는다.
정적 모델/태스크 고정·새 free-body 시작 범위이며, 시드별 질량/형상을 덮어쓸 수 없다.

수정 전 근거/거부 분포는 [관문 표](rejection-table.json)에 있다. 단위는 **모델 후보 2개**다.
marker 메타데이터 2→2, persistence 관문 2→1(거부1), 폐루프 관문 1→0(거부1), 실행 승인 0→0.
학생 시도 40회를 하나의 성공률 분모로 합친 표가 아니다. 별도 물리 실패 원인을 주장하지
않으므로 이번에는 새 실패/성공 영상 분석을 만들지 않았다. 향후 원인 분석은 gcp2 영상 규칙을 따른다.

## 참고 자료 — 2026-10-16 원문·공식 코드 확인

논문 결과는 저자 보고이며 우리 장면에서 재현한 성능이 아니다. 읽은 코드의 고정 커밋·URL·
파일 SHA는 [reference-sources.json](reference-sources.json)에 있다. 다운로드한 원문은
`outputs/rlprep/references/`에 로컬 보존했다. 아래 수치는 각 저자 설정으로, 우리 기본값이 아니다.

| 방법/1차 출처 | 핵심 설정·우리 적용 판단 |
|---|---|
| [Residual Policy Learning](https://arxiv.org/abs/1812.06298), [저자 설명/코드](https://k-r-allen.github.io/residual-policy-learning/) | 기존 제어기에 model-free 잔차를 더하는 출발점. 손으로 짠 근거리 파지 경로를 새 base로 넣는 근거로 쓰지 않는다. |
| [ResFiT, 2025 §III-C](https://arxiv.org/html/2509.19301v1), [공식 구현](https://github.com/amazon-far/residual-offpolicy-rl/tree/66262b06a0caf159fb001504949b7b48ccda5f64) | action-chunk BC 동결+매 틱 잔차. n-step3, critic LayerNorm, actor 지연2–8, tau .005, offline/online 50:50. 원문은 UTD>1·20Hz·별도 시각 encoder를 사용한다. 코드 기본 critic warmup10k, actor lr1e-6/critic1e-4이며 PR530의3e-4와 다르다. ACT를 실제 base로 다뤄 1순위 근거다. |
| [DPPO, ICLR2025](https://arxiv.org/abs/2409.00588), [공식 can 설정](https://github.com/irom-lab/dppo/blob/cc7234ad7ff39a8f32de3af903606723a16f0648/cfg/robomimic/finetune/can/ft_ppo_diffusion_mlp.yaml) | denoising MDP에 PPO. 해당 설정은 total denoise20/FT10, chunk4, gamma .999, denoise gamma .99, PPO clip .01, GAE .95, 10epochs. CPU 병렬 환경+GPU 학습 예이며 MJWarp 예가 아니다. ACT에는 denoising likelihood가 없어 직접 이식하지 않는다. |
| [PA-RL, 2412.06685](https://arxiv.org/abs/2412.06685), [저자 방법 설명](https://policyagnosticrl.github.io/) | policy 후보 여러 개→Q 상위 후보→행동 gradient 개선→지도학습 distillation. 본문 계열은 Cal-QL, IQL/RLPD 조합도 보고. ACT 직접 미세조정의 2순위 연구안. 특권 Q의 행동 선택은 **학습 표적 생성에만** 허용한다. 저자 연결 GitHub는 timeout으로 코드 미확인; 후보 수/최적화 횟수는 추정해 채우지 않는다. 프로젝트 페이지 BibTeX의 다른 arXiv 번호도 복사하지 않았다. |
| [RLPD, ICML2023](https://arxiv.org/abs/2302.02948), [공식 설정](https://github.com/ikostrikov/rlpd/blob/c90fd4baf28c9c9ef40a81460a2e395092844f88/configs/rlpd_config.py) | prior/online replay 혼합·Q ensemble10/target min2·LayerNorm. train 스크립트 기본 offline ratio .5, batch256, UTD1(실험별 override와 구분). demo 재사용은 (o,a,r,o',종료)와 출처가 완비된 동일 contract 전이에만 허용한다. |
| [Policy Decorator, ICLR2025 §4/App.B](https://arxiv.org/html/2412.13630v1), [공식 코드](https://github.com/tongzhoumu/policy_decorator/tree/92ba9ba442587ae5989c286355ace2200a0537fb) | SAC 잔차+bounded action+progressive exploration. visual TurnFaucet 예 H30k/scale .05, PushChair H100k/scale .2로 태스크별 값이다. 원문 batch1024·UTD .25·tau .01. 보편적인 “예산20% warmup” 규칙은 아니다. 우리 calibration 없이 그 scale/스케줄을 넣지 않는다. |
| [DSRL, CoRL2025](https://arxiv.org/abs/2506.15799), [공식 코드](https://github.com/ajwagen/dsrl) | diffusion/flow의 base 가중치를 동결하고 초기 latent noise 분포를 RL로 학습. 출력 잔차와 별개다. ACT의 inference latent를 곧바로 같은 공간으로 취급하지 않는다. |
| [2026 diffusion navigation GRPO](https://arxiv.org/abs/2603.12868), [ARLI 저자 설명](https://async-rl-intermediate-information.github.io/) | 최신 인접 연구도 확인: 전자는 encoder 동결/상위 decoder·head 갱신과 group 상대 advantage, 후자는 발행 중 명령·중간 관측을 포함한 지연 모델을 다룬다. 초록/저자 설명 확인 범위이며 코드·상세 HP·ACT 적합성은 미검증이다. 이번 ACT 잔차 경로의 대체 근거로 쓰지 않는다. |
| [MuJoCo Playground 공식 vision PPO](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/config/manipulation_params.py), [trainer](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/learning/train_jax_ppo.py), [MJWarp 공식 설명](https://github.com/google-deepmind/mujoco_warp) | `PandaPickCubeCartesian` vision 설정: worlds1024, unroll10, minibatches8, updates/batch8, batch256, gamma .97, lr1e-3, clip .3. trainer의 policy/value observation key를 분리하고 `--impl=warp` 경로를 사용한다. state actor의 관절·정답 입력을 우리에게 복사하지 않는다. 1024세계 저해상도 예를 L4의 원래 fisheye 640×480 처리량으로 외삽하지 않는다. |

보상 형식은 [Ng et al. 1999 원문](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf)의
potential 차분을 참고한다. 잔차 decoder 미분 근사는 기존 PR530의
[TD3 저자 구현](https://github.com/sfujim/TD3/blob/master/TD3.py)·
[straight-through 개념](https://arxiv.org/abs/1308.3432)과 구분한다.

## 제안 설계와 입력 경계

**1순위: 고정 ACT+매 0.1 SIM초 잔차**, 기존 `rl_act_actor.compose`와 decoder를 재사용한다.
원래 RGB 이력/발행 명령 이력·번호표에서만 특징, base 출력·자기 chunk 위치를 만든다.
ACT와 actor encoder를 동결하고 zero-init 잔차 head를 학습한다. 역정규화14D(base+bounded residual)를
기존 바퀴·duration·PWM·done decoder로 보낸다. 최종 합성 **발행** 명령을 자기 이력에 쓴다.
잔차0일 때 원래 명령과 일치해야 한다. done 한도는 유효한 교정 label이 없는 기존0을 유지한다.
새 base/장면으로 옮길 때 train-only 교정 분포로 차원별 범위를 다시 봉인한다. ACT15의
작은 상자 envelope를 빔 wheel 분류 head에 그대로 붙이지 않는다.

첫 실험의 제안 learner는 PR530의 twin LayerNorm critic·MLP2×256·batch128·n-step3·
actor4회 지연·tau .005·Adam3e-4·UTD1이다. 이는 **기존 pilot 설정 유지**이며 ResFiT 전체 재현이
아니다. gamma .995/0.1SIM초는 기존 설정(반감 약13.8SIM초)으로, 논문20Hz 값을 그대로 옮긴 것이
아니다. Q ensemble10·고UTD·demo50:50·progressive exploration은 첫 후보에 자동 추가하지 않는다.
바퀴 deadband/PWM rounding의 straight-through는 실제 decoder forward를 유지하는 손실용 근사다.
새 모델에서 실제 gradient/메모리·base0 동등성 검증 전에는 learner ready로 보고하지 않는다.

**2순위 직접 미세조정**은 PA-RL식 train-only 행동 표적 distillation이다. ACT encoder 동결·head만
갱신하는 별도 후보로, 파국적 망각과 chunk credit을 검증한다. privileged critic은 배포 후보 선택·
chunk 선택·done 지연·재집기/성공 통보에 쓰지 않는다. PPO 잔차 비교를 한다면 raw residual의
log_prob를 저장하고 decoder 투영 뒤 행동의 확률로 가장하지 않는다. DPPO/DSRL은 별도 diffusion
base와 비용 관문을 요구하므로 이번 ACT 골격에는 구현하지 않는다.

학습 reward는 기존 `rl_act_reward`의 `10*success_once + gamma*Phi(next)-Phi(now)`를 사용한다.
Phi는 train p95 거리로 정규화한 접근 거리와 pi로 정규화한 방향 오차의 음수 평균이다.
새 wrapper는 **에피소드당 성공 보너스 한 번**으로 latch하여 낙하/재파지의 반복 상승 보너스를 막는다.
이는 코드/가상 전이 검사이며 실제 reward hacking을 관측했다는 주장이 아니다.
terminal의 Phi(next)는0, 단순 수집/예산 truncation은 마지막 관측으로 bootstrap한다.
90SIM초 유한 태스크 종료와 collector cap은 별도 필드로 기록하고 시간 종료는 `cap_end`로 남긴다.
실제 evaluator 성공 판정과 정책 종료를 바꾸지 않는다. 안정 들기·운반·놓기 성공을 따로 세며,
들기 성공을 전체 운반 성공으로 쓰지 않는다. h1/2/3은 이번 준비에서 모두 off;
특히 warp3는 centre mask 주석 미지원이라 h1을 켤 수 없다.

훈련 critic 전용 입력은 qpos/qvel·화물 pose/속도·상대 거리/각도·접촉·높이/기울기·
남은 **SIM** horizon, detach한 허용 actor 특징과 실제 발행 action이다. 처음 두 종류와 접촉은
warp3 API가 제공하고, 추가 항목은 추후 schema로 봉인해야 한다. critic encoder/normalizer/hidden을
actor에 공유하지 않는다. 정답 reward·critic은 학습 process/파일 lane에만 두고 평가 actor를
별도 process로 export한다. `held_world_reads=0`, `invisible_measurements=0`은 **정책 입력/행동 선택**
감사에 적용하며 허용된 training privileged read 수는 별도로 센다. 이 골격의 payload 검사만으로
실제 GPU process read=0을 증명했다고 쓰지 않는다. top 제어 입력·weld·수제 근거리 fallback은 금지다.

## 자원/계산량 상한 제안 — 실행 권한 아님

| 단계 | 세계 수 | 최대 전이 수 | 합산 SIM초 | critic update 상한 | L4 점유 상한 제안 |
|---|---:|---:|---:|---:|---:|
| 연결 후 pilot | 8 | 7,200=8×1×900 | 720 | 7,200 | 1h |
| pilot 이후 별도 stage1 | 16 | 72,000=16×5×900 | 7,200 | 72,000 | 추가3h |

episode90SIM초/900틱은 기존 ACT15/warp3 horizon이다. 세계 수는 기존 rl1b8슬롯부터 시작해
한 번만2배로 늘리는 **메모리/처리량 미측정 자원 제안**이며 적합한 배치가 실증됐다는 뜻이 아니다.
전이 수·update 수는 sealed count로 끝내고, 계획/탐색 wall 초를 행동 기준으로 쓰지 않는다.
원래 카메라·고리 버퍼·ACT 메모리 요구량이 안 맞으면 세계 수를 낮춘 별도 계획을 봉인한다.

L4 한 장의 준비/JIT·진단·학습·평가/저장까지 총4GPU h 제안이다(위1h+3h). 비용용 외부
wall 상한은 학습 알고리즘의 탐색/종료 기준과 별개다. 실제 과금·공유 부하는 미측정이며
4h를 완료 시간 약속으로 쓰지 않는다. rl1b 저장 median wall/SIM233.565가 그대로라면
90SIM초 한 배치만 약5.84h라 pilot1h에 못 들어온다. 속도가 개선됐다고 추정하여 제출하지 않는다.
관문 후 첫30SIM초에 end-to-end/physics/render/ACT/update/JIT를 분리 측정하고 기존 >6 차단을
적용한다. 비용/VM 상한·공유 작업·디스크 때문에 끝나면 cap_end/HOST_ERROR를 분리해 회수한다.

gcp2 프로젝트 `ugrp-sim-b-1014`/계정 `changmin5781@gmail.com`만 사용한다. 향후 모든 gcloud에
`--account changmin5781@gmail.com --project ugrp-sim-b-1014`를 붙인다. gcp1은 접근/생성/복사 금지다.
8h·idle20분·budget-stop을 유지하고, 시작 전 lease·전체 동시 실행≤40·저장 예산을 확인한다.
자기 lease만 정리하며 다른 lease/실행이 있으면 VM을 멈추지 않는다. VM에 모델/에이전트 키를
두지 않는다. 이번에는 원격 명령·lease 생성·VM 조작 자체가 없다.

## 실행 전/후 관문

1. 현재 wait 해제는 같은 모델/태스크/입력 계약의 validation persistence 엄격 개선과 비영(非零)
   폐루프 성공 근거를 재확인한 뒤다(ResFiT의 base 성공 전제). MAE만으로 성공 채택하지 않는다.
   ACT15 loader는 해시가 고정돼 있어 beamact3를 로드하지 못한다. **해시·새 출력 head용 별도
   adapter와 장면/공동 역할 계약 봉인**도 필요하다. 현재 후보 표는 교체 후보의 상태 비교다.
2. 같은 gcp2 머신·정적 모델/카메라·control tick으로 partial reset 후 다른 세계의 **다음** 동역학과
   RGB/issued 이력을 확인한다. paused world의 clock/state 고정, 잔차0 동등성, 정책 canary 정답
   변조 불변성, deployment의 reward/critic 모듈 미로드, h1 off, weld off를 실측한다.
3. 첫30SIM초 속도/메모리·실제 learner gradient/유한 손실·저장/재로딩·actor-only export를 확인한다.
   미구현/미검증 gate는 통과로 채우지 않는다. `start_training()`은 현재 인자와 무관하게 거부한다.
4. 미래 pilot의 새 평가 시드를 train/dev/기존20과 분리해 미리 봉인한다. **각 arm40회**를 제안한다
   (프로젝트 관문의 최소40과 같은 표본 예산; 학생95% 기준을 가져온 것이 아니다). persistence,
   ACT 단독, ACT+RL을 같은 시작/동일 SIM horizon으로 짝 비교한다. persistence는 이전 발행 명령
   유지+동일 actuator 한도인 ablation으로 명시하고 정답 종료를 넣지 않는다. 학습 마지막
   checkpoint를 고정하고 평가로 선택하지 않는다. 3×40×900=108,000전이/10,800합산SIM초 평가도
   총 점유 예산에 포함한다. 못 끝낸 arm은 n/N미완료로 남기고 짧은 prefix를 완주로 바꾸지 않는다.
5. n_RL>n_ACT와 n_RL>n_persistence의 관측 개선, paired 승/패, Wilson 구간, 모든 cap_end/실패/
   HOST_ERROR 분모와 접근→정렬→READY→파지→3초들기→놓기 funnel을 보고한다. 40회의 관측 개선은
   pilot 신호이며 정식 채택/통신 효과 주장은 별도 검정/표본수 사전등록 뒤다. GT reward 크기·MAE
   감소는 성공률 대신 쓰지 않는다. s1 작은 상자 결과와 공동 빔·다른 장면/호스트는 합산하지 않는다.

향후 대기열에는 실제 존재하는 절대 `rejection_table` 경로가 필요하다. 이번 `plan.json`은
`DESIGN_ONLY_NOT_A_QUEUE`/`execution_allowed=false`이며 실행 대기열을 발행하지 않는다.
실패 분석은 gcp2에서 분포와 영상(실패1–2/성공1)을 만들고 Mac에는 요약·몽타주·실패 프레임만
회수한다. warp3의 기존100틱/10SIM초·10Hz 자기카메라 ring을 재사용하며 학습 영상과 분리한다.
실제 영상 크기/ffprobe·전체2Hz/직전10초10Hz 직접 검토는 향후 실행에서 확인해야 한다.

## 코드·검증·재현

- `scripts/rlprep_contract.py`: 기본 off `rlprep_batch_v1`, warp3 metadata 검사,
  `dict→TrainingTruth` 학습 전용 adapter, actor/public terminal과 reward/critic 반환 분리,
  episodic 보너스 latch, active world 수로 계산한 전이 상한, cap_end 사유/로그.
- 기존 `rl_act_env/reward/actor/learning`은 수정하지 않는다. 실제 MJWarp owner/RPC 생성·GPU
  learner 연결·chunk cache reset callback·새 head export는 미연결이며 ready로 보고하지 않는다.
- 시작 전에 존재하던 미추적 `scripts/rl_act_prep.py`, `tests/test_rl_act_prep.py`는 수정/커밋하지
  않았다. 시작 해시는 `inputs.json`에 있다. 새 CI에는 `test_rlprep_contract.py`만 추가했다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.prepare_rlprep
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_rlprep_contract.py tests/test_rl_act_signal.py \
  --junitxml=outputs/rlprep/pytest.xml
```

비물리 범위: 정답 canary 변경 시 공개 입력/terminal 불변·eval privileged read0,
실제 warp3 형식 truth 변환, 기본 off/강제 학습 금지, 전이 cap 직전 engine 호출 차단,
reset 뒤 reward 폐기, potential telescoping·반복 보너스 차단, 실제 marker 형식 검증.
새3건+기존17건의 최종 결과·소스/산출물 해시는 `verification.json`에 남긴다.
실제 NN 학습/부분 reset 동역학/GT actor 입력0/학생 성공은 이 시험 범위가 아니다.
기록은 로컬·GitHub PR에 보존하며 프로젝트 규칙에 따라 Drive를 사용하지 않는다.
