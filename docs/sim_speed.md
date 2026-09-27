# 시뮬레이션 속도: 동작 불변 설정과 대기열

2026-09-26 사용자 요청("좀 빨리 할 수 있는 방법이 없을까")에 따라 로봇 행동·결과를 바꾸지 않고 CPU를 줄이는 방법을 정리한다. 측정·동등성 근거는 [실험 기록](../experiments/2026-09-26-sim-speed/README.md)에 있다. 물리·timestep·solver·접촉·카메라 해상도/FOV/외관·렌더러 설정·제어 주기는 바꾸지 않는다.

## 1. 비트 동일 가속 `exact-v1` (M1 러너)

```sh
.venv-sim-worker-mac/bin/python scripts/run_m1_owncam.py --prereg experiments/2026-09-26-zone-m1-owncam/prereg.json \
  --only m1dev-s93 --output /Users/changmin/projects/ugrp/outputs/<새 폴더> --speedups exact-v1
```

- `sim/exact_speedups.py`의 두 항목만 켠다. 구동 산술(`ExactDriveKernel`, 기존 `PhysicsDriveKernel` 훅 재사용)은 `np.dot`의 합산 순서를 그대로 따르고, 시작 시 `np.dot`과 비교하는 자체 검사가 실패하면 원래 경로로 돌아간다(`manifest.json`의 `speedups.drive_kernel`에 기록). 접촉 사전 필터(`ContactPrefilter`)는 러너가 어차피 건너뛰는 접촉만 벡터 연산으로 뺀다.
- 기본값은 `none`(기존 경로)이다. 적용 여부는 `manifest.json`의 `speedups`에 남고 `result.json`은 바뀌지 않는다.
- 다른 러너에서 구동 산술만 쓰려면 월드 생성 뒤 `from sim.exact_speedups import install_drive_kernel; install_drive_kernel(world)`를 호출한다. 러너마다 동등성 검증을 따로 한다. 훅에 이미 다른 커널(비트 동일이 아닌 `PhysicsDriveKernel`, 다른 버전, 다른 월드)이 있으면 유지·교체하지 않고 `RuntimeError`로 거부한다. 같은 버전의 정확 커널이면 `exact_drive_kernel_already_installed`를 돌려준다.
- **연구 코호트 기본값은 아직 `none`이다.** 2026-09-26 Codex 검토 판정에 따라, 최종 소스를 고정한 전체 M1 A/B에서 파지·상승 이후까지 qpos 해시를 비교하기 전에는 `exact-v1`을 연구 공통 기본값으로 채택하지 않는다(지금까지 qpos 동일성은 seed별 첫 120 SIM s만 확인).
- 다른 플랫폼(Ubuntu/OpenBLAS 등)이나 패키지 버전에서는 자체 검사 결과와 동등성을 다시 확인한다. Mac 결과와 Linux 결과는 같은 코호트로 합치지 않는다(렌더러·부동소수점이 다름).

## 2. 동등성 확인

```sh
python3 scripts/sim_equivalence.py <기준 run 폴더> <새 run 폴더>                 # 전체 실행
python3 scripts/sim_equivalence.py <절단 run> <전체 run> --until-sim-s 120       # 절단 실행과 앞부분 비교
```

명령·제어 입력 프레임 행과 JPEG 바이트·제어기/스킬/매크로 로그·평가 로그·`result.json`을 비교한다. 종료 코드는 동일 0, 다름 1, 증거 부족 2(`insufficient_evidence`)다. 필수 파일·JSON 객체·비교 건수와 양쪽의 구간 도달을 검증한다.

전체 비교는 M1 v3의 명령·프레임·controller/skill events·macros·평가 frames/gt_trajectory/contacts/retention **9개 로그 전부**와 manifest의 파일 SHA-256을 요구한다. `result`의 commands/frames/contact/retention 개수, 프레임 인덱스와 평가 행 정렬, 프레임·GT의 시작/간격/종료 도달을 검사한다. `phase_times`의 `skill:grasp → to_carry_posture → nav_preplace → release → look_back` 순서와 해당 입력 프레임, 파지·상승 macro/skill event, 운반 retention이 필요하다. 따라서 동일하게 누락된 로그·후반 구간이나 미완주 자료는 전체 동등성 증거가 아니다. 명령·로그·result는 **원본 바이트 SHA-256**으로 비교하므로 키 순서·공백·숫자 표기 차이도 다름이다. JSON 파싱은 검증/차이 설명용이며 정규화 비교를 하지 않는다. prefix 비교도 선택한 행의 원본 바이트를 유지한다.

프로파일끼리는 `qpos_checkpoints.jsonl`의 `step`(양의 정수), `t`(유한한 음이 아닌 수), `sha256`(64자리 소문자 hex)을 검증하고, `profile.json`의 `qpos_every`, `mj_steps`, `checkpoints`, `initial_sim_s`, `timestep`, `last_step_checkpoint`, `final_checkpoint`와 대조한다. 간격·순서·시간·총 스텝·마지막 상태가 맞아야 한다. 전체 비교는 최종 시간을 러너의 `result.sim_s`(소수 둘째 자리 반올림)와 대조한다. 구간 비교는 **qpos와 제어 프레임 모두** 양쪽에서 끝까지 도달해야 하며, 양쪽이 똑같이 잘려도 증거 부족이다. 프로파일이 한쪽에만 있으면 증거 부족이다. 일반 run 두 개의 로그 비교는 qpos 미비교를 명시한다.

`sim_profile.py` v3는 qpos 기록이 켜져 있으면 매 `mj_step` 직후 스냅샷을 갱신해 `last_step_checkpoint`를 보존한다. 종료 시 읽은 `final_checkpoint`는 별도로 저장하고, 둘이 다르면 오류를 남긴다. 종료가 정규 간격 사이에 있어도 마지막 물리 스텝의 스냅샷을 추가하므로 종료 직전 상태 덮어쓰기를 숨기지 않는다. 이전 자료에 메타데이터가 빠졌다면 새 검사로 전체 상태 동등성을 인증할 수 없다. 원본을 수정하거나 과거 판정을 소급 확대하지 않는다. **저장 자료는 간격별 상태 샘플이며 매 스텝 누적 해시가 아니다.** 추가 해싱 비용이 있으므로 이후 A/B는 같은 계측 버전을 사용해야 한다. 연구 기본값 채택에는 [전체 A/B 사전등록 초안](../experiments/2026-09-26-sim-speed/prereg_default_check_DRAFT.json)의 별도 연속 상태 기록·2 seed × 4회 검증이 필요하다. 초안은 미등록·미실행 상태다.

## 3. CPU 측정

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
python3 scripts/ugrp_session.py run kiro-prof -- .venv-sim-worker-mac/bin/python scripts/sim_profile.py m1 \
  --episode m1dev-s93 --sim-limit 120 --speedups exact-v1 --output /Users/changmin/projects/ugrp/outputs/<새 폴더> [--sections|--cprofile]
```

비교는 wall이 아닌 CPU 초와 **retired instruction 수**로 한다. Apple M3(성능 코어 4 + 효율 코어 4)에서는 같은 구간의 CPU 초도 부하에 따라 2배 이상 달라진다(효율 코어 배치·경합). `profile.json`의 `counters`(instructions, P 코어 비율)와 `cpu_at_sim_mark`(고정 SIM 시각까지의 CPU)를 함께 본다. wall 비교가 필요하면 `scripts/agent_lock.py` 잠금을 잡는다.

## 4. 머신 전체 sim 대기열 `scripts/sim_slots.py`

```sh
python3 scripts/sim_slots.py status
python3 scripts/ugrp_session.py run kiro-m1 -- python3 scripts/sim_slots.py run --owner kiro --label m1-s93 -- \
  .venv-sim-worker-mac/bin/python scripts/run_m1_owncam.py ...
```

- 이 대기열은 **MuJoCo 라이브러리를 로딩한 프로세스 수의 보수적인 상한**을 관리한다. import 후 대기하는 pytest·노트북도 센다. 실제 `mj_step` 실행 수를 관측하지 않으며 `active_sim_count`는 `null`이다. 열린 `queue.lock`만으로 일을 안 한다고 가정하지 않는다.
- 기본 cap은 6이다. Mac 공용 root는 기존 `/Users/changmin/projects/ugrp/outputs/sim-slots`, Linux는 `/var/tmp/ugrp-sim-slots`다. Linux에서 여러 사용자가 참여하면 관리자가 해당 디렉터리의 공용 그룹/권한을 준비한다. 모든 참여자는 동일 root·cap을 사용한다. `--root`는 격리 테스트/관리자 설정용이며 에이전트별 root를 만들면 전역 제한이 분리된다.
- `admission.lock` 안에서 집계와 예약을 수행한다. 슬롯 파일이 열려 있다는 사실은 예약 증거가 아니다. 커널 잠금, 예약 기록, PID와 커널 시작 식별자가 맞는 보유자/자식만 연결한다. 예약 **하나당 로딩 프로세스 하나**만 상쇄하고, 나머지 자식은 추가로 센다. 옛 기록에 시작 식별자가 없거나 PID가 재사용됐으면 중복 제외하지 않는다.
- 여러 worker를 시작하는 명령은 시작 전에 **최대 동시 로딩 프로세스 수**를 `run --workers N` 또는 `sim_slot(..., workers=N)`으로 예약한다. N개 예약은 모두 한 번에 승인하거나 거부한다. 이미 로딩된 자식도 집계에서 숨기지 않는다. 이는 협력적 입장 제어이며, 예약을 과소 신고하거나 우회한 명령의 임의 fork를 OS 차원에서 차단하는 샌드박스는 아니다.
- `sim_slot()`의 workers에는 현재 프로세스도 포함한다. 이미 MuJoCo를 로드한 호출자가 아직 미예약이면 그 한 자리만 기존 집계에서 새 예약으로 전환한다(cap=1에서도 가능). CLI/new-worker 입장에는 이 공제를 적용하지 않는다. 호출자+자식 하나면 workers=2다.
- `release()`는 자기 FD를 닫으며 `LOCK_UN`·기록 삭제를 하지 않는다. 상속 FD가 살아 있으면 예약도 유지된다. CLI는 자기 명령을 별도 프로세스 그룹에서 시작하고 **직접 명령이 끝나도 살아 있는 작업 자손이 모두 종료될 때까지** 예약을 유지한다. SIGINT/SIGTERM은 리더가 아직 회수되지 않았고 시작 식별자·PGID가 모두 맞을 때만 전달한다. `poll()` 중에는 전달을 보류하며, 리더 회수 후에는 숫자 PGID로 신호를 보내지 않고 자손 종료를 기다린다. 다른 reaper와의 경쟁을 막기 위해 SIGCHLD는 기본 처리여야 한다. Python 호출에서 자식을 시작할 때는 `run_reserved(slot, cmd)`를 사용한다. 그룹을 벗어나 detach하는 작업은 FD를 유지하거나 자체 예약해야 한다. 단순 `with sim_slot(...)` 본문에서 미예약 자식을 남기면 안 된다.
- Linux `/proc`의 살아 있는 PID에 대한 권한/파싱 오류, macOS `lsof`의 실패 코드/부분 결과, 커널 시작 식별자 변경은 입장을 거부한다. macOS 식별자·그룹은 `libproc`으로 확인한다. 가시성이 제한된 호스트/샌드박스는 전체 census를 확인할 수 없어 종료 코드 70으로 거부할 수 있다. 추정치로 진행하지 않는다.
- Linux에서는 hidepid 제한, 부분/overlay proc mount, 호스트 PID namespace를 확인할 수 없는 경우도 거부한다. 관리자는 **실제 호스트 namespace에서 확인한** 부팅별 기준을 `/etc/ugrp/sim-slots-host.json`에 준비해야 한다: `{"schema":"ugrp.host_proc_visibility.v1","boot_id":"<현재 boot_id>","pid_namespace":{"device":<host /proc/1/ns/pid st_dev>,"inode":<st_ino>}}`. 파일과 상위 디렉터리는 root 소유이고 group/other 쓰기 금지여야 한다. 현재 container namespace를 자동 등록하지 않는다. 기준이 없거나 재부팅으로 만료되면 sim 0개로 간주하지 않고 거부한다. 실행 중 그룹 종료 판정에서도 가시성을 잃으면 예약을 유지한다. 이 변경에서 실제 호스트 기준 파일을 생성하지 않았다.
- census는 저비용이라고 보장하지 않는다. macOS의 전체 `lsof` 조회는 비용이 들며 결과를 오래 캐시하지 않는다. 단조 시계 `--timeout`은 전역 잠금 대기와 census 시간을 포함하며, 각 census도 최대 5초 예산을 받는다. 만료 시 시작하지 않고 75를 반환한다. 커널/파일시스템 호출의 스케줄링 지연까지 실시간 반환을 보장하는 것은 아니다.

## 5. 개발용 앞부분 절단(dev slice)

```sh
... scripts/sim_profile.py m1 --episode m1dev-s93 --speedups exact-v1 --stop-at-phase skill:to_carry_posture --output ...
```

제어기가 지정 단계(`phase_times` 키 형식)에 들어가면 다음 결정 전에 끝낸다. 그 전까지는 전체 임무와 같은 궤적·명령·프레임이다. 출력에 `DEV_SLICE_NOT_A_RESULT.txt`가 생기며 M1 결과로 보고하지 않는다. 동결·시험 판단은 전체 임무로 한다. 문 통과·배치 같은 뒤쪽 단계부터 시작하는 slice는 제어기 진입점이 필요해 아직 없다(실험 기록 참조).

## 6. 원격 병렬 코호트(실행하지 않음)

| 경로 | 병렬성·비용 | 절차·주의 |
|---|---|---|
| Ubuntu 팀원 PC ([설치](ubuntu_quickstart.md)) | 코어 수만큼 동시 실행, 추가 비용 없음 | `MUJOCO_GL=osmesa` 기본(소프트웨어 렌더링). EGL GPU 렌더링은 별도 검증. Mac과 렌더러·부동소수점이 달라 **별도 실행 환경 코호트**로 기록 |
| Kaggle CLI ([안내](kaggle_simulation.md)) | 비공개 CPU kernel, 무료. 이 CLI 경로의 작업당 최대 요청 1,800초, 실제 할당은 `kaggle quota` | `prepare → submit → status → collect`. 인터넷 OFF, OSMesa. M1 한 에피소드(Mac 저부하 CPU 약 490초, 렌더 약 150초)가 OSMesa에서 1,800초 안에 끝나는지 먼저 짧은 slice로 측정해야 함 |
| Colab CLI ([안내](colab_simulation.md), [L4 검토](colab_standard_simulation_review_20260923.md)) | 무료 CPU 런타임 또는 계정의 CCU. 유료 자원 자동 구매 금지 | 전송기가 OSMesa를 강제. L4 EGL 연결·검증 미완. 세션당 유한 배치 후 회수·해시 검증, 자기 세션만 정리 |

세 경로 모두 결과 회수·해시 검증까지 해야 완료이며 Mac 결과와 섞지 않는다. 이번 작업은 원격 자원을 만들거나 실행하지 않았다.
