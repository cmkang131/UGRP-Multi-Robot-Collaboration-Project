# warp2 — ACT 외 흐름의 MJWarp 배치 이동

2026-10-16 사용자 요청, Refs #523. **A: 소스 열람·설계 완료 / B: 공통 백엔드 재사용 구현, 유한 gcp2 검증 중**. [실행 결과](runtime.md)는 CPU/GPU·시드 반복·초기화·cap_end를 구분한다. A 완료 당시의 무실행 기록은 설계 시점의 범위다. 장면/관문 대기열은 HOLD_SCENE, 미승인·미제출이다.

- [우선순위·공수·기대 이득](priority.md)
- [MjData·카메라·명령·입력 감사·성공 판정 경계](inventory.md), [행별 목록](access-inventory.csv)
- [LLM 대기 세계의 정지·리셋·비동기 묶음 설계](llm-batching.md)
- [전체 요약](summary.json), [누적 관문·거부표](rejection_table.json)
- [소스 SHA·파일 해시](source-manifest.json), [기존 CPU 근거](baseline-evidence.json)

## 구현 순서와 공통 백엔드 계약

1순위는 LLM 없는 **빔 짝 교사 beampair6**다. `claude/warp-act`가 제공하는 배치 엔진·상태 동기화·렌더/접촉 공급자를 그대로 쓴다. 별도 `put_model/make_data/step` 엔진이나 독립적인 접촉 변환기를 만들지 않는다. 작업 worktree는 `warp-flows`, 브랜치는 `claude/warp-flows`이며 설계 기록을 위해 공통 조상 `142dbf04c2128c3d7ca1c3ceb03ee3b651d9a7e5`에서 먼저 만들었다. 구현 전 warp1의 **커밋된** API를 반영한다. 작성 중 파일은 실행·복사하지 않는다.

의존 API 요구는 다음과 같다. 세계별 setup/advance 경계에서 고정 제어 tick을 양보하고, 공통 배치 엔진이 물리 substep마다 기존 port deadline·v7 입력 릴레이를 적용한다. host MjData는 같은 세계·같은 SIM 시각의 동기화된 뷰다. ray/FOV용 운동학 뷰와 **GPU에서 계산한** 접촉/force 평가를 구분한다. CPU에서 새로 접촉을 풀어 GPU 파지 성공을 판정하면 안 된다. 기본 `physics_backend`는 기존 C 경로이며 `mjwarp_batch_v1`은 명시적으로 켜야 한다.

각 lane은 별도의 교사·보이는 물체 기억·HeldCargoGuard·READY/GO/ACK·RNG·port·감사 원장·기록기를 가진다. 두 로봇의 관측을 먼저 취득한 뒤 명령을 발행하는 기존 순서를 유지한다. 한 lane의 양쪽 로봇은 같은 물리 세계에 있고, 다른 lane과 통신하지 않는다. 기존 adapter의 모듈 monkeypatch와 전역 closure는 lane별 `sys.modules` 문맥으로 격리한다. 각 generator를 진행/종료할 때 자기 `harness/sim/scripts` 문맥만 설치하고 원래 문맥을 복구한다. `teachers/models/guard` closure를 lane 사이에 공유하지 않는다.

보이는 대상의 위치를 만드는 교사 어댑터는 현재 시야/가림 조건을 유지한다. 학생·LLM 관측으로 이 정답 기반 교사 측정을 보내지 않는다. 닫기 명령부터 빔/끝 측정을 양쪽에서 지우는 `held_object_hidden_v1`과 `held_world_reads=0`, `invisible_measurements=0`을 유지한다. top은 평가 전용이다. weld OFF, 카메라 배치/FOV·해상도·제어/관측 주기·기존 성공식·계산량 탐색 예산은 유지한다. backend별 결과를 합산하지 않는다.

## B의 유한 검증 계획

최대 3라운드, L4 사용 누적 최대 3시간. gcp2 프로젝트 `ugrp-sim-b-1014` / 계정 `changmin5781@gmail.com`만 쓴다. `ugrp-act-l4-gcp2`의 다른 작업 임대·PID·GPU 메모리를 먼저 확인하고 자기 임대를 만든다. CPU VM 전체 실행 합계는 40 이하로 둔다. N64/256은 사용자가 지정한 **하나의 GPU 배치의 세계 수**이며 64/256개 CPU 프로세스를 띄우는 것이 아니다. CPU 비교는 최대 40개 작업의 실제 동시성·부하를 기록한다.

알려진 6개 시드: **8318726, 8318620, 8318600, 8318604, 8318611, 8318631**. beampair6 고정 plan의 spawn·beam·초기 pan·role·burst·토글을 그대로 쓴다. N1·N16에서 각 시드의 기존 성공식과 입력 감사를 다시 센다. N16의 반복 lane은 독립 시드 16개나 새 관문으로 세지 않는다. 공통 API는 upstream에서 세계별 배열이 가능한 필드만 허용하며, 여섯 장면의 `dof_length` 차이는 지원하지 않는다. `exact_model_groups_v1`은 정확한 XML별로 기존 `WarpTransport`를 한 번씩 호출하고 그 graph를 세계 묶음별 stream에 enqueue한다. 새 물리 엔진/필드 덮어쓰기는 없다. 성공·실패·cap_end·HOST_ERROR·미시작을 구분하고 6/6 C 결과를 승계하지 않는다.

N16/64/256 처리량은 완료된 유효 세계의 SIM초 합 / 배치 wall초로 기록한다. compile/setup·CPU↔GPU 동기화·교사·RGB·기록을 포함한 end-to-end와 순수 physics를 따로 낸다. GPU 비동기 작업은 동기화 후 wall 시각을 읽는다. `SIM초/$ = 3600 × throughput / VM_hourly_price`; 가격의 지역·시각·근거와 VM 전체 요금/증분 비용을 표시한다. 새로운 CPU 짝 비교가 없으면 과거 wall/SIM에 N을 곱해 N16 처리량으로 발표하지 않는다.

R2 N1 성공 뒤 마지막 R3는 N16/64/256의 각 1 SIM초 고정 작업량(prefix: 기존 0.25ms 물리 4000 step·10 control tick)을 먼저 재고, 여섯 시드를 섞은 N16의 전체 교사 실행을 따로 수행한다. prefix는 초기화 비용을 포함한 짧은 구간이며 장기 정상 상태 속도나 집기 성공으로 해석하지 않는다. 실패면 수정 전 거부 분포를 먼저 만든다. 원인을 주장할 경우 gcp2에서 실패 1–2개와 성공 1개의 개요+r1+r2 영상을 3배속으로 만들고 전체 2Hz·마지막 10 SIM초 10Hz 프레임띠를 파일로 본다. Mac GUI/물리/렌더는 금지다. 실패 직전 자기 카메라 10Hz ring은 기록 전용이며 control frame_id/RNG/관측 호출을 바꾸면 안 된다. 학습 카메라·학습·LLM E2E는 이번 B에서 실행하지 않는다.

## 참고 자료와 확인 범위

공식 코드의 고정 commit·파일 SHA256·회수 시각은 [official-sources.json](official-sources.json)에 있다. 원문은 Mac `outputs/e2e18-admin/warp2-plan/sources/`에 보존했다. 저장소 소스는 `git show <SHA>:<path>`로 읽고 AST parse만 했다. 아래 조사는 실행 검증이 아니며, 설치된 warp1 버전에서 같은 API가 있는지는 B 직전에 다시 확인한다.

- [MuJoCo MJWarp 공식 안내](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html): 큰 배치의 throughput 최적화, 단일 세계 latency와의 차이, capacity·graph capture·host/device 전송 비용.
- [MJWarp io.py @57b4692f](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L2656): `reset_data`의 세계별 reset mask.
- [MJWarp forward.py @57b4692f](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/forward.py#L2224): 확인한 `step(m,d)`는 active-world mask 인자를 받지 않는다.
- [Playground wrapper.py @d59156e0](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/_src/wrapper.py#L198): env.step 후 done에 따라 data/obs/info를 선택하는 autoreset.
- [Brax training.py @6d039374](https://github.com/google/brax/blob/6d039374b34a266107bd1e952180eea33ac4eab8/brax/envs/wrappers/training.py#L130): pipeline state와 obs의 세계별 done 선택. reset과 pause를 구분하는 참고 코드.
- [Isaac Lab DirectRLEnv @86042738](https://github.com/isaac-sim/IsaacLab/blob/86042738bbf79b894df1825bbfe342625cd74f1b/source/isaaclab/isaaclab/envs/direct_rl_env.py#L662): reset buffer→env_ids, `_reset_idx(env_ids)`; [PhysX articulation](https://github.com/isaac-sim/IsaacLab/blob/86042738bbf79b894df1825bbfe342625cd74f1b/source/isaaclab_physx/isaaclab_physx/assets/articulation/articulation.py#L453)의 선택된 상태 쓰기. 선택 reset이 전체 sim.step에서의 세계별 pause를 보증하지 않는다.

기존 물리의 5mm 동등성 관문을 새로 적용하지 않는다. 2026-10-16 단계적 이동 결정에 따라 MJWarp 자체의 성공식/입력 관문으로 평가하되, C와의 관측·궤적·성공 차이는 별도 기록한다. 장면 채택과 40회 관문 승인은 남는다.
