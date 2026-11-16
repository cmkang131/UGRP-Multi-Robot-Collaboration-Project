# v6 dev 코호트 6회 실행 결과 (2026-09-28, Claude)

tags_temporary 조작 진단이며 연구 결과가 아니다. weld OFF, 모델 호출 0, 재시도 0.
제어 입력은 자기 손목 RGB·자기 발행 명령·정적 지도/보정·STATUS뿐이다. GT는 `eval_only/`의 사후 평가에만 있다.

## 한 줄 결론

**v6는 과거보다 더 가지 못했다.** 6회 모두 파지 전에 끝났다.

- v5h 조건 2회는 dev09–14와 같은 정렬 단계 재관측 실패로 끝났다.
- b-only·a+b 4회는 **출발 직후** 첫 둘러보기에서 막혀 공동 운반 작업이 시작되지도 않았다.
  B 플래그(posterior 보존 PF)가 출발 위치 추정을 망가뜨렸다.
- 그래서 A 플래그(빔 기준 상대 정렬)는 물리에서 한 번도 실행되지 않았다. **A의 효과는 이 코호트로 알 수 없다.**

## 실행 조건과 승인

| 항목 | 값 |
|---|---|
| 실행 소스 | `3c26acddec066adcd9164e6d2a6f51c1261c5f66` (`claude/zone-pair-v6-dev`, main e8ff1882 + 등록 커밋) |
| 번들 | `zone-pair-v70-beam-relative-multiturn`, workflow `zone-pair-dev` 0.6.0 |
| 사전등록 | `prereg_v6.json` REGISTERED, `registration_sha256=379ffe42…68fa` ([등록 기록](registration.json)) |
| 승인 | [#221 코멘트 5866466067](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5866466067). 관리자 세션이 사용자 위임에 따라 승인. 드라이버가 실행마다 실시간 조회로 확인(`github_authorization.author=cmkang131`) |
| 잠금 | `agent_lock` owner claude, 드라이버 PID에 묶음, 종료 뒤 해제 확인 |
| raw | `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v6-3c26acddec066adcd9164e6d2a6f51c1261c5f66/` (327 MiB, 로컬 전용·원격 백업 아님) |
| 동시 실행 | 1개씩 순차. 승인 envelope가 worktree의 prereg 한 파일에 run_id 하나씩만 들어가기 때문이다 |

### DRAFT→REGISTERED 전환 (과학 내용 불변)

병합된 v6 로더는 DRAFT에서 `--execute`를 무조건 거부했고, 등록 경로가 없었다.
v5h와 같은 방식(등록 커밋 + 늦은 envelope + 실시간 GitHub 코멘트)으로 실행하도록 최소 변경했다.

- `scripts/zone_pair_v6_contract.py`: DRAFT는 계속 prepare-only다. REGISTERED는 envelope의 source SHA·run_id·registration 해시, `--lock-owner`, 주 checkout `outputs/` 절대 경로를 검사한다.
- `prereg_v6.json`: `status`, `runnable`, `readiness`, `draft_registration`만 바꿨다. 로더 해시와 `registration_sha256`만 다시 계산했다. [register_v6.py](register_v6.py)가 과학 필드(환경·기준·예산·run·플래그·예산 범위) 불변을 assert한다. DRAFT 원본은 e8ff1882의 바이트(sha256 `4ce32a6a…efe9bf`)로 묶었다.
- readiness의 미충족 항목(상대/전역 bound 보정, markerless provider·형상 coverage)은 해제하지 않고 공개 항목으로 남겼다.
- 회귀: `tests/test_zone_pair*.py`, `tests/test_zone_study*.py` 등 **7550 passed / 3 failed** ([로그](registration_pytest.log)). 실패 3건은 sparse worktree에 없는 `experiments/2026-09-26-zone-study-offline-smoke/*/example_trial_record.json.gz` 때문이다. 이번 변경과 무관하다.

### 운영 사고 1건 (물리 전 거부)

s912-v5h 실행 중(09:00:53Z) 제가 worktree에 미추적 분석 파일(`replay_bootstrap.py`)을 만들었다.
다음 실행 v6-s912-b가 **물리 시작 전** `execution source must be clean` 으로 거부됐다(09:15:02Z, 출력 폴더 없음, 기록 `v6-s912-b-managed/`).
s912-v5h는 추적 소스 fingerprint가 바뀌지 않았다(`source_changed=false`). 파일은 실행기가 import하지 않는다.
파일을 치운 뒤 v6-s912-b와 v6-s912-ab를 새 기록 경로(`*-managed-a2`, [run_cohort_a2.sh](run_cohort_a2.sh))로 실행했다.
물리 결과를 보고 다시 돌린 것이 아니므로 재시도로 보지 않는다. 거부 기록은 그대로 보존한다.

## 결과표

SIM 시간은 시뮬레이터 시각 1.3 s 시작 기준 종료 시각이다. "명령"은 발행한 arm/look/drive/mecanum 명령 수이며 실제 관절·이동 성공이 아니다.

| 실행 | 조건 | 종료 사유 (먼저 실패한 쪽) | 도달 단계 (제어기 자체 상태) | SIM s | wall s | look 명령 r1/r2 | 정렬 재관측 r1/r2 | 명령 | 파지·들기·운반 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| v6-s911-v5h | v5h | r2 `ALIGN_RELOOK_NO_FIX` @187.8 → r1 `PARTNER_ABORT` | 접근 성공 → 정렬 (둘 다 align) | 190.3 | 811 | 164 / 338 | 2 / 2 | 1886 | 없음 |
| v6-s911-b | b-only | r1·r2 둘러보기 `SWEEP_TRANSITION_BLOCKED` @11.4 → 60 s 공동 운반 요청 둘 다 `SELF_UNCERTAIN` 거부 | 출발 전 (공동 작업 없음) | 62.5 | 190 | 0 / 0 | – | 6 | 없음 |
| v6-s911-ab | a+b | s911-b와 동일 (영상·명령 바이트 동일) | 출발 전 | 62.5 | 185 | 0 / 0 | – | 6 | 없음 |
| v6-s912-v5h | v5h | r1 `ALIGN_RELOOK_FIX_EXPIRED` @210.5 → r2 `PARTNER_ABORT` | 접근 성공 → r1 align, **r2 pregrasp_standoff** | 213.0 | 886 | 292 / 496 | 6 / 5 | 3194 | 없음 |
| v6-s912-b | b-only | r1·r2 `SWEEP_TRANSITION_BLOCKED` @11.4 → `SELF_UNCERTAIN` 거부 | 출발 전 | 62.5 | 233 | 0 / 0 | – | 6 | 없음 |
| v6-s912-ab | a+b | s912-b와 동일 (영상·명령 바이트 동일) | 출발 전 | 62.5 | 201 | 0 / 0 | – | 6 | 없음 |

- 사후 평가(GT): v5h 2회는 `DEV_NOT_CONFIRMED`다. approach는 통과했고 joint_grasp·lift·door·배치는 실패다. 금지 접촉 0, weld 0, r3 간섭 0.
- b-only·a+b 4회는 `EVIDENCE_INCOMPLETE`다. 공동 작업이 없어 평가기가 경로를 대조하지 못했다.
- 요약 원자료는 [summary.json](summary.json)이다. 부하 평균(시작→끝)도 여기 있다. 시스템 부하는 12–70으로 높았으며, 이 결과는 동기 SIM 시간 기준이다.
- 영상은 핵심 시점 프레임만 확인했다. s911-b 60 s에서 세 로봇 모두 dock에 있고, s912-v5h 209 s에서 두 로봇이 바닥의 빔 양끝에 있다. 전체 영상 수동 검토는 하지 않았다.

### 첫 실패 원인과 증거

**v5h 조건 (s911, s912)**

- 정렬 중 예정 재관측의 전역 fix가 `std_xy` 검사에서 거부된다. 제한 시간·fix 만료로 실패한다.
- s911 r2: `align_relook_fix_rejected` @185.6/186.7/187.8 s (frame 1551/1562/1573). 마지막은 `gate_ok, std_xy, std_yaw, sigma_reserve` 실패 → `ALIGN_RELOOK_NO_FIX`.
- s912 r1: 재관측 6회. 마지막 fix(frame 1789, 209.5 s) 뒤 210.5 s 재검사에서 `std_xy` 실패 → `ALIGN_RELOOK_FIX_EXPIRED`.
  이때 r2는 pregrasp_look에서 `pregrasp_fix`(209.3 s)를 받고 pregrasp_standoff에 들어가 있었다.
- 주의: 이 v5h 조건은 동결 v5h와 같지 않다. 공용 경로 변경(차단 명령 처리, 성분 마스킹, 예산 초기화 범위)이 포함된다.

**b-only / a+b (4회)**

- 두 로봇 모두 60 s 전 첫 `look_around`에서 팔을 드는 전이가 10 s 대기 후 거부됐다 (`events.jsonl` job_failed @11.4 s).
- 막힌 이유는 자기 위치 추정이다. s911 r1 추정 (2.12, −0.83) m, σxy 2.70 m, σyaw 1.27 rad였다. 실제로는 x=−0.65 dock에 있다. 이 추정을 믿으면 카메라 구가 `wall_divider_1`과 겹친다(여유 −8 mm, 요구 398 mm).
- 60 s의 `pair_carry`는 둘 다 `SELF_UNCERTAIN`으로 거부됐다 (`eval_only/pair_admission.jsonl`, gate `uncertain`).
- 오프라인 재현([replay_bootstrap.py](replay_bootstrap.py), 저장된 자기 JPEG·명령만 사용, GT 없음):
  - 출발 뒤 태그가 보이는 자기 프레임은 **첫 프레임(1.30025 s) 하나뿐**이다. 첫 팔 명령(1.3 s) 0.25 ms 뒤에 찍혔다. 그 뒤 카메라가 기울어 11.4 s까지 태그 0개다.
  - v5h PF는 이 첫 프레임으로 σxy 1.07–1.30 m까지 줄인다. v6 recovery PF는 "팔 명령 뒤 0.3 s 미정착 프레임"이라 사후분포를 줄이지 않아 2.70–2.89 m에 머문다. 4개 로봇·seed 모두 같다 ([bootstrap_replay_*.json](.)). 기록된 실패 추정값(2.7031 m / 1.2685 rad)을 그대로 재현했다.
  - v5h의 1.1–1.3 m도 믿을 만한 위치는 아니다. 이 경우 guard를 통과했을 뿐이다. 그 뒤 팔이 올라가 태그를 보고 σ 0.025–0.037 m fix를 얻었다.
- v6 오프라인 재생은 정렬 checkpoint부터 시작해서 출발 부트스트랩을 다루지 않았다. 그래서 이 문제를 보지 못했다.

## dev05–14와 비교

| 코호트 | 가장 멀리 간 단계 | 주된 실패 |
|---|---|---|
| dev03–04 (v2) | 출발 전 | `SWEEP_TRANSITION_BLOCKED`(출발 둘러보기) → 랑데부 시간 초과 |
| dev05–06 (v3) | 제어기 grasp·wait_lift 상태 (GT 파지 없음) | 충돌 guard, `POSE_UNCERTAIN` |
| dev07–08 (v4) | pregrasp_descend·wait_close (닫힘 명령 0) | `PREGRASP_NOT_READY`, `POSE_UNCERTAIN` |
| dev09–14 (v5b–v5h) | align (재관측 반복) | `ALIGN_RELOOK_NO_FIX` / `ALIGN_RELOOK_TIMEOUT` |
| **v6 (이번)** | **pregrasp_standoff (s912-v5h r2 한쪽)** | v5h: `ALIGN_RELOOK_NO_FIX`·`ALIGN_RELOOK_FIX_EXPIRED` / b·a+b: `SWEEP_TRANSITION_BLOCKED` |

- 13회 연속(dev05–14 + v6)으로 GT 기준 파지(joint_grasp)가 한 번도 없다. v6는 더 가지 못했다.
- s912-v5h r2의 pregrasp_standoff는 dev07(pregrasp_descend)보다 앞 단계다. 진전이 아니다.

## 다음 병목

1. **출발 위치 부트스트랩 (b-only·a+b에서 먼저 막힘).** B 플래그를 켜면 공동 작업 자체가 시작되지 않는다. 이것을 풀기 전에는 A(상대 정렬)를 물리로 시험할 수 없다.
2. **정렬 단계의 전역 재관측 정밀도 (v5h).** dev09–14와 같은 실패가 두 번 더 나왔다.

## 같은 실패 반복 — 국소 패치 대신 선행 방법

전역 지침에 따라, 반복된 실패에 새 임계값·예외를 덧대지 않는다. 검증된 방법을 먼저 적용한다.

**출발 부트스트랩 실패 (dev03–04에 이어 두 번째)**

- MCL/AMCL의 표준 절차는 초기 자세 사전분포(평균+공분산, 또는 알려진 후보 위치들의 혼합)로 입자를 초기화하는 것이다. 전역 초기화는 사전 정보가 없을 때만 쓴다. [Thrun·Burgard·Fox, *Probabilistic Robotics* 8장 MCL], [ROS AMCL `initial_pose`/`initial_cov`](https://wiki.ros.org/amcl).
  - 우리 정적 지도에는 `zone_start_dock_v3`의 세 출발 행이 있다(로봇-행 배정은 없음). 세 행의 혼합 사전분포는 실시간 정답이 아니라 허용된 정적 지도 정보다.
- Active Markov Localization은 위치가 모호할 때 사후분포 전체에서 안전한 감지 행동을 고르고, 먼저 멈춰서 관측한다. [Fox·Burgard·Thrun 1998](https://doi.org/10.1016/S0921-8890(98)00049-9).
  - 우리 경우에는 팔 명령 전에 정지 상태의 정착 프레임을 먼저 찍는 것이다. 지금은 첫 명령과 같은 순간의 프레임 하나만 태그를 본다.
- 불확실한 자세에서의 충돌 검사는 belief 전체에 대해 기회 제약으로 한다. [Bry·Roy 2011 RRBT](https://doi.org/10.1109/ICRA.2011.5980508). 사전분포 없이 σ 2.7 m 구름으로는 어떤 팔 동작도 인증되지 않는 것이 정상이다.

**정렬 단계 전역 재관측 실패 (dev09–14에 이어 7·8번째)**

- [lit_review.md](../lit_review.md)의 결론(물체 기준 상대 측정 + 짧게 이동·정지·재관측, 전역 PF는 참고값)이 이미 이 실패에 대한 문헌의 답이다. v6의 A 플래그가 그 구현이다.
- 다음 코호트는 새 정렬 패치가 아니라, 위 부트스트랩을 문헌 방식으로 고친 뒤 A를 실제로 물리에서 도달시키는 것이 우선이다.

## 영상 (원본, 로컬)

| 실행 | `eval_only/overview.mp4` sha256 | 바이트 |
|---|---|---:|
| v6-s911-v5h | `c5d18502cfb29822748515d718212cbd71da4c3a6215b9996e6bbf820c3c2dc8` | 1,422,716 |
| v6-s911-b | `302a14170c0eaa4cd65278e20248d52f82ff8f44a207b0291165807b56fb0a8d` | 416,249 |
| v6-s911-ab | `302a14170c0eaa4cd65278e20248d52f82ff8f44a207b0291165807b56fb0a8d` (s911-b와 동일) | 416,249 |
| v6-s912-v5h | `1bc1f35b0aab1bca26d291adf595e776866bbc5650dae8c7d7b1263a2c6080e0` | 1,626,357 |
| v6-s912-b | `e67d6189b565fd93e8b501da6487519fae3d311fb9f954597501ff8cf8a6d620` | 418,242 |
| v6-s912-ab | `e67d6189b565fd93e8b501da6487519fae3d311fb9f954597501ff8cf8a6d620` (s912-b와 동일) | 418,242 |

경로는 raw 폴더 아래 `<실행>/eval_only/overview.mp4`다 (고정 관측 카메라 `cctv_warehouse`, 5 fps, 평가 전용).

## 원본 해시

| 파일 | SHA256 |
|---|---|
| v6-s911-v5h/manifest.json | `d792517c3907d7e9426be650379f1d75db5c070191743136c19f658ec88bc0ba` |
| v6-s911-v5h/artifacts.sha256.json (8251 파일) | `5fd649f7e6d9f440d2ee320761977033cbe3819ad6e59c0fbf9e2213b2e74589` |
| v6-s911-v5h/eval_only/trace.jsonl | `d0806573ad95ae9cbacf43335cb61d85044a7d11369a7d478c14f518c5dfa202` |
| v6-s911-b/manifest.json | `3a027bf521cbf1a3d20068fa3fbb8bd5d175a8e69ab44a3bb4f7ce8d4b2ac381` |
| v6-s911-b/artifacts.sha256.json (1857) | `1fc1b8c50209ad210122cef34c40d590da629fd66a7e5b1d5d2c8e17f151404c` |
| v6-s911-ab/manifest.json | `2952d7ea08504c53ad019120b5ff384a9cabd00fd34244c3dcf3903fa0036c60` |
| v6-s911-ab/artifacts.sha256.json (1857) | `6c60d0e52f64fc53efcb6f279e9af2065433a9de18448483d0d1359f6268b6ee` |
| v6-s912-v5h/manifest.json | `8c54c75fd4eee34a2e4e59998628dc326d6bd6420865a762bfed1c42d3c46491` |
| v6-s912-v5h/artifacts.sha256.json (9385) | `782eb14cb8f7fc467376d6f8cdc00ccf70eaf29bd9e2c4e30218b78714b6b5a6` |
| v6-s912-v5h/eval_only/trace.jsonl | `819ae5b840faeaa4c124541e54b9af140ffe4a0bad8116e8d79a86392ad84add` |
| v6-s912-b/manifest.json | `0916aa431e26fd25b68a2699e3479451715918e54aa92ec06932184ed8b897d5` |
| v6-s912-b/artifacts.sha256.json (1857) | `b62582dadc1c59ea6477f3de4f6558ab1930a001d4b44ba21a633fd2b1e16b24` |
| v6-s912-ab/manifest.json | `ed91261d4eb7fdb0ff0e9975f62c76b7a3ea8a6be4e84735cc6e431578343430` |
| v6-s912-ab/artifacts.sha256.json (1857) | `762de35a51461e28ed1d8b57cb3229b200b9a7b50db030521b9b7d9e9c452e6a` |
| v6-s912-b-managed/manifest.json (물리 전 거부) | `38aafd639c58777f982da9636986652660b07cc593814e0df81bbba17e3356a8` |
| v6-s912-b-managed-a2/manifest.json | `57255346178c070d2a2c76ada44432862874851341a30a025c2fae7fac1fc768` |
| v6-s912-ab-managed-a2/manifest.json | `3edb84acaf8c492fbb2456fad34f7782466c3f80a725d1222ad9eb1e6fb76960` |

모든 자기 입력 JPEG·메타데이터가 각 `artifacts.sha256.json`에 있다. 모델 요청은 없다.

## TensorBoard

- 새 snapshot: `/Users/changmin/projects/ugrp/outputs/tensorboard/0928-zone-pair-v6-dev/v5h-v6`. v6 6회 + 기준선 dev13·dev14(v5h 동결, 이전에 미변환)다. 파생 뷰는 `outputs/zone-pair-v6-dev-tb-view-20260928/`(result.json + 영상 hardlink)다.
- EventAccumulator로 8개 run의 scalar 5종(success·sim_s·wall_s·commands·model_calls)을 다시 읽었다. 원자료와 일치한다 ([검증](tensorboard_validation.json)).
- 공용 viewer(PID 9293/9291, 다른 작업 소유)는 재시작하지 않았다. logdir `/Users/changmin/projects/ugrp/outputs/tensorboard`에서 새 run 8개가 보이고, 고정 링크의 값을 확인했다.
- `outputs/tensorboard-view.json`에는 `zone_pair_v6_dev_20260928` 키만 추가했다.
- 남은 확인:
  - 미디어 서버(:6009)는 이번 영상 id에 404를 준다. 등록 목록이 서버 시작 때 만들어진 것으로 보인다. 소유자가 재시작해야 한다.
  - HParams 열은 UI에서 이 run들에 대해 다시 확인하지 않았다.

## 참고 자료

- Thrun, Burgard, Fox. *Probabilistic Robotics*, MIT Press 2005, 8장 (Monte Carlo Localization, 전역·초기 자세 초기화).
- ROS AMCL 문서, `initial_pose_*`·`initial_cov_*` 파라미터: https://wiki.ros.org/amcl
- Fox, Burgard, Thrun 1998, "Active Markov localization for mobile robots", Robotics and Autonomous Systems 25: https://doi.org/10.1016/S0921-8890(98)00049-9
- Bry, Roy 2011, "Rapidly-exploring Random Belief Trees for motion planning under uncertainty", ICRA: https://doi.org/10.1109/ICRA.2011.5980508
- v6 문헌 요약: [../lit_review.md](../lit_review.md)
