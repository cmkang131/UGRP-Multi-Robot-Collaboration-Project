# DEV 체크포인트·이어가기 (v98 단계 검사 속도 올리기, 2026-10-05)

Refs #363. 브랜치 `claude/v98-checkpoint`(기준 `codex/pair-carry-highpose`).

## 왜

`align_to_carry` 단계 검사(`scripts/run_pair_highpose.py --stage-probe align_to_carry`)는 매번 출발점부터 전체 경로를
다시 돈다(약 500 SIM초, 벽시계 40–90분, 부하에 따라 더). 고친 내용은 보통 실패 지점 근처의 행동만 바꾼다. 그래서 경로 중간
상태를 저장해 두고 거기서 다시 시작하는 **DEV 전용** 도구를 만들었다.

## 규칙 (지켜야 할 것)

- 이어간 실행(resumed)은 **DEV 진단 전용**이다. `resumed_from=<체크포인트 sha256>`, 코호트 `v98-dev-resumed-diagnostic`,
  `evidence: false`, `pooled: false`로 표시한다. 증거로 세지 않고 합산하지 않는다. **최종 검증은 계속 연속 실행이다.**
- 바뀐 제어기 코드로 이어가기는 진단에서만 허용한다. `--allow-code-change`가 있어야 하고, 기록에 체크포인트의 코드 SHA와
  지금 코드 SHA가 둘 다 남는다(`code_changed: true`). 작업 트리가 더러우면 거절한다(코드 SHA를 남길 수 없으므로).
- 기본은 꺼짐이다. `student_run_case(..., dev_checkpoint=None)`이면 실행기 동작·출력 바이트가 그대로다(아래 게이트로 확인).
- 물리·카메라·제어기 동작은 바꾸지 않는다. 정답(GT)을 제어에 넣지 않는다. 이 도구는 이미 있는 상태를 저장·복원만 한다.
- DEV_PILOT 단계 검사(`--admission dev-pilot --stage-probe ...`)에서만 쓴다.

## 사용법 (정확한 명령)

모든 명령은 자기 worktree에서, 소유한 SIM 슬롯으로 실행한다(AGENTS.md 잠금 규칙). `<SHA>`는 커밋된 HEAD.

1. **체크포인트를 저장하며 연속 실행** — 실행기 `main()`을 그대로 쓰고, 루프 경계(틱 i의 맨 앞, eval_sample·촬영 전)에서
   저장만 끼운다. 나머지 인자는 `run_pair_highpose.py`와 똑같다.

   ```
   python -m scripts.dev_pair_checkpoint run --after-carry-go-s 5 --every-s 25 [--at-sim-s 400] [--stop-at-sim-s 165] \
     --check carry --map-id zone_wide_door_geometry_v3 --case-id zone_wide_door_geometry_v3 \
     --admission dev-pilot --stage-probe align_to_carry \
     --calibration experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json \
     --calibration-sha256 aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4 \
     --expected-source-sha <SHA> --lock-owner claude --sim-slot <slot> \
     --output /Users/changmin/projects/ugrp/outputs/<run> --execute
   ```

   - `--after-carry-go-s 5`: 운반 barrier GO마다 5 SIM초 뒤 저장(운반 다리 안). `--every-s N`: N SIM초마다.
     `--at-sim-s T`: 월드 SIM 시각 T(이벤트 `sim_s`와 같은 시계) 이후 첫 틱. `--stop-at-sim-s`: DEV 지평 멈춤.
   - 저장 위치: `outputs/<run>/checkpoints/ckpt_<tick>_t<sim_s>.pkl.zlib` + `.sha256` + `manifest.jsonl`
     (틱, SIM 시각, 스트림 오프셋·접두 sha256, 다른 파일 sha256, 코드 SHA·dirty, 버전, 부하 평균).
   - 저장 실패는 `result.dev_checkpoint_errors`에 기록만 하고 실행은 계속한다(저장은 상태를 읽기만 한다).

2. **실패 직전 체크포인트 고르기** — `manifest.jsonl`에서 실패 시각 바로 앞 행을 고른다.

   ```
   python -c "import json;[print(r['file'],round(r['sim_s'],2),r['triggers']) for r in map(json.loads,open('outputs/<run>/checkpoints/manifest.jsonl'))]"
   ```

3. **이어가기** — 새 출력 폴더로. 스트림 접두(jsonl)와 재설정 기록 파일은 원본 실행에서 sha256을 확인하며 복사한다.
   프레임 이미지 접두는 복사하지 않는다(디스크; sha256 행은 `frames.jsonl`에 있다).

   ```
   python -m scripts.dev_pair_checkpoint resume \
     --checkpoint /Users/changmin/projects/ugrp/outputs/<run>/checkpoints/<file>.pkl.zlib \
     --calibration experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json \
     --output /Users/changmin/projects/ugrp/outputs/<run>-resumed-<label> --lock-owner claude --sim-slot <slot> \
     [--stop-at-sim-s <T+60>] [--allow-code-change]
   ```

   고친 코드로 이어가려면: 고친 코드를 커밋하고(트리 깨끗), `--allow-code-change`를 붙인다.

4. **비트 동일 비교** — `python -m scripts.dev_pair_checkpoint compare --continuous <연속 case 폴더> --resumed <이어간 case 폴더>
   --from-sim-s <T> --min-horizon-s 60 --report <json>`. 모든 jsonl 스트림(명령 행, 프레임 행, `eval_only/trajectory.jsonl`의
   qpos/qvel, 접촉, 카메라 표지)의 바이트 접두, 모든 자기 카메라 프레임 파일의 sha256, `student_record.json`의 모든 이벤트 목록
   (벽시계 키 제외)을 비교한다.

## 무엇을 저장하나

한 체크포인트 = Python 객체 그래프 전체를 cloudpickle로 한 번에 피클(같은 memo라 공유 참조·순환이 그대로 유지된다).

- 물리: `backend` 전체. MuJoCo `MjModel`·`MjData`는 통째로 피클한다(`qpos/qvel/act`, `qacc_warmstart`, 접촉·제약 버퍼, `time`,
  호스트 시계 v2의 정수 하위 단계 수). 월드의 Python 상태, 명령 포트, 프레임 번호, 발행 명령 표.
- 제어: `runtime` 전체 — 두 로봇의 PF 입자·가중치·numpy `Generator` 상태, 명령 이력, 상태 채널, 타이머, 실행기, guard, 로그.
- 호스트 루프: 틱 번호, `start`, 로봇별 명령 수, 사례 `result` 사전.
- 프로세스 RNG: `random.getstate()`, 옛 `np.random` 상태. 모듈 표(경로로 불러온 VIS3·markerless 모듈과 `sys.path`).

피클하지 않고 복원 때 새로 만드는 것: 스레드 잠금(경계에서 잡혀 있으면 저장 거절), 렌더 `ThreadPoolExecutor`와 두
`mujoco.Renderer`(새 렌더 스레드에서 같은 모델·크기로; 렌더 프로필 `floor_light_v1`은 XML/모델 수준이라 렌더러 쪽에 잃는 상태가
없다), 열린 jsonl 스트림(접두 복사 뒤 append로 다시 열기), 원래 case 폴더 아래 경로(새 폴더로 옮김), `MjvOption` 등 Mjv 구조체
(필드 복사). 저장 때 거절하는 것: MuJoCo 버퍼를 가리키는 ndarray 뷰(조용히 복사되면 갈라진다), 진행 중인 Future, 모르는 열린 파일.
`__getattr__`로 위임하는 클래스(`FailClosedLoc`)는 기본 역피클이 빈 객체에서 `__setstate__`를 찾다 무한 재귀하므로 명시적
상태 설정자로 다시 만든다(같은 `__dict__`).

## 비트 동일 게이트 (필수)

`experiments/2026-10-05-dev-checkpoint-resume/run_gate.sh`(물리 프로세스 동시 1개, 조정자 지시 2026-10-05).

- 0단계: 최신 #363 head를 가져와 이 브랜치가 그것을 포함하는지, HEAD 기준 worktree(`ugrp-wt/v98-ckpt-headbase`)가 정확히
  그 SHA인지 확인한다(아니면 거절).
- 기본 꺼짐: #363 HEAD 실행기와 이 브랜치 실행기(체크포인트 없음)로 같은 짧은 `raise_high_align`을 돌려 바이트 비교.
- 저장 켠 연속 `align_to_carry`(165 SIM초 DEV 멈춤)를 HEAD 짧은 실행과 비교(HIGH까지 같은 궤적; 단계 이름이 들어 있는
  `stage_probe_entry` 이벤트의 `stage` 키 하나만 `--ignore-event-key stage`로 제외, 스트림·프레임은 전부 비교).
- T1 = 운반 다리 안(첫 운반 GO + 5 SIM초), T2 = 운반 전(그 앞의 25초 주기 체크포인트, 파지·들기 구간). 각 T에서 이어간
  실행을 T+62 SIM초까지 돌리고 연속 실행과 비교(60 SIM초 이상).
- #363 담당의 s911 `align_to_carry` 실행(`outputs/v98-dev-align_to_carry-7194637e-s911`)은 사용자 중단으로 81.55초에 멈춰
  기준으로 쓰지 않는다. 다른 단계 검사끼리 비교하면 `stage_probe_entry` 행이 다르므로 기본 꺼짐 확인은 같은 단계 검사로 한다.

결과: **아직 실행 안 함.** 2026-10-05 15시 무렵 기계 과부하(부하 평균 135–234, CPU 8개, 스왑 5.2/6 GiB)로 조정자가
먼저 물리 동시 1개·#363 실행 우선, 이어서 사용자 지시로 시뮬레이션 전부 중단을 전달했다. 재개 지시 뒤
`run_gate.sh /Users/changmin/projects/ugrp/outputs/v98-ckpt-gate-<SHA8>`
로 실행한다. **게이트 통과 전에는 이 도구로 진단하지 않는다.**

지금까지의 증거(게이트 아님):
- 단위 시험 `tests/test_dev_pair_checkpoint.py` 11개 통과. 관련 시험 119개 통과(dev_pilot·final_veto·timing·highpose·워크플로).
- 개발 루프(재기반 전 코드, 직접 `student_run_case` 호출, align_to_carry seed 911): 1.5 SIM초에 저장, 3.0초까지 연속 vs
  새 프로세스에서 이어감 → 모든 jsonl 스트림 바이트 접두·프레임 30장×2 sha256·이벤트 목록 동일(지평 1.45초뿐).
  `outputs/v98-ckpt-dev-20261005/loop1_compare.json` sha256 `337c5888…`, 체크포인트 `73fe4e3a…`(3.5 MB 압축).
- 중단한 실행(증거 아님): `outputs/v98-ckpt-dev-20261005/aborted-gate-7dbcd627-stopped-at-5s`(연속 저장 실행, 5 SIM초에 멈춤),
  `aborted-head-7194637e-overload`(HEAD 짧은 실행, 4 SIM초에 멈춤).

벽시계 속도: 아직 측정 못 함. 예상은 이어가기 준비(역피클 + 모듈 163개 + GL 렌더러) 수십 초 + (실패 시각 − T)의 물리 시간,
연속 실행은 0초부터 실패 시각까지. 게이트의 `gate_log.jsonl`(단계별 unix 시각·부하 평균)로 측정해 채운다.

## 한계

- 바뀐 코드로 이어가기: 모듈 수준 함수·클래스는 새 코드를 불러오지만, 값으로 피클된 클로저(예: `cap_world_steps`의
  `limited_step`, 단계 검사 `tick` 감싸개, `init_prior` 감싸개, `rt.bind` 결과)는 체크포인트의 옛 코드를 유지한다. 새 코드가
  인스턴스 필드를 추가하면(`__init__`에서만 만드는 속성) 복원된 객체에는 없다. 그런 변경은 이어가기로 진단할 수 없다.
- 프레임 이미지 접두는 복사하지 않는다. 접두가 필요한 평가 도구는 원본 실행 폴더를 읽는다.
- 서로 다른 프로세스의 문자열 해시 시드(`PYTHONHASHSEED`)로 집합 순회 순서가 바뀔 수 있다. 게이트는 기본(무작위) 시드로 돌렸다.
- 체크포인트는 같은 기계·같은 버전(mujoco/numpy/Python)에서만 쓴다(manifest에 기록).
- 렌더 스냅숏 브로커(`render_snapshot_async`)를 쓰는 경로는 지원하지 않는다(저장 거절).

## 참고 자료

- MuJoCo 문서 "Simulation → State": `mjtState`, `mj_getState/mj_setState`, `mjSTATE_INTEGRATION`(전진 동역학의 입력 전체),
  `qacc_warmstart`, 잠자기 요소가 있으면 `mjData` 전체 복사만이 완전한 저장·복원이라는 설명.
  https://mujoco.readthedocs.io/en/stable/programming/simulation.html (확인함). 이 도구는 `MjData` 전체를 피클한다(가장 보수적).
- MuJoCo Python 바인딩: `MjData` 피클은 자기 `MjModel` 사본을 함께 만든다(로컬 확인: `d2.model is not m`, 200 단계 뒤 qpos/qvel
  비트 동일 — `tests/test_dev_pair_checkpoint.py`).
- Gymnasium `MujocoEnv.set_state`: qpos/qvel만 넣고 `mj_forward`. warmstart·접촉 버퍼는 복원하지 않으므로 비트 동일 이어가기가
  아니다. https://github.com/Farama-Foundation/Gymnasium/blob/main/gymnasium/envs/mujoco/mujoco_env.py (확인함)
- Brax: 환경 상태가 불변 pytree(`State(pipeline_state, obs, reward, done, metrics, info)`)이고 `step`이 상태를 받아 새 상태를
  돌려준다 → 저장 = pytree 보관. https://github.com/google/brax/blob/main/brax/envs/base.py (확인함; 순수성은 구조상 추정)
- Isaac Lab "Reproducibility and Determinism": 같은 하드웨어·버전·시드에서 강체는 결정적, GPU 스케줄링으로 최하위 비트가 바뀔 수
  있음; 시뮬레이터 상태 저장·복원 API는 그 문서에 없음.
  https://isaac-sim.github.io/IsaacLab/main/source/features/reproducibility.html (확인함)
- cloudpickle README: 가져올 수 있는 모듈의 함수·클래스는 참조로, 동적·지역 정의는 값으로 피클.
  https://github.com/cloudpipe/cloudpickle (확인함) → 바뀐 코드 이어가기 한계의 근거.
- Python `pickle`: `Pickler.reducer_override`, 6-튜플 reduce의 `state_setter`(3.8+). https://docs.python.org/3/library/pickle.html (U)
- numpy `Generator.bit_generator.state`(피클 포함), `random.getstate/setstate`.
  https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.BitGenerator.state.html (U),
  https://docs.python.org/3/library/random.html#random.getstate (U)
- 고전 체크포인트/재시작: DMTCP(Ansel, Arya, Cooperman, IPDPS 2009) — 프로세스 전체를 투명하게 저장(U). Chandy·Lamport(1985)
  일관된 전역 스냅숏 — 여기서는 단일 스레드 루프 경계가 일관 지점(U). 기록·재생 디버거 rr(O'Callahan 외, USENIX ATC 2017)(U).
  프로세스 이미지 방식은 GL 컨텍스트·열린 파일 때문에 쓰지 않고, 응용 수준 객체 그래프 저장을 택했다.
