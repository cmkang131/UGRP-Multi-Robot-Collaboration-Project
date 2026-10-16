# 2026-10-05 v98 시뮬레이션 wall 시간 감시와 비트 동일 가속 (DEV 진단, 증거 아님)

Refs #363. 사용자 요청(2026-10-05): "시뮬 렌더링 시간도 왜 오래 걸리는지 좀 제대로 감시해봐", 이어서 "시뮬 빨라지게 정상화".
이 기록의 모든 실행은 **개발 진단(DEV)**이다. 연구 결과나 #363의 성공 근거로 합산하지 않는다.

## 1. 한 줄 요약

- **연구 실행용 가속 세트는 `v98-exact-v6`로 확정**했다(조정자 결정 2026-10-05). 구성은 `v98-exact-v1` + `pf_geometry_shared`(A1) + `opencv_exact`(A3)이고, `render_pipeline`(A2)은 끈다.
- **v1 전 구간 바이트 동일:** align_to_carry s911 전체 길이에서 가속 없음(wtA-solo)과 v1(wtX-n0b)을 비교했다. 15324/15328 파일이 같고, 나머지 4개는 허용 목록의 wall/id/경로 필드다. 판정 `IDENTICAL_UP_TO_ALLOWLIST`, 행동 차이 0(7절).
- **v1의 정상 구간 속도 이득은 거의 0이다.** 같은 SIM 구간(121–321 s, 프레임 파일 mtime 기준)에서 가속 없음 2.91 wall/SIM, v1 2.88 wall/SIM이다.
  - **처음 보고한 "4.53 → 2.27"은 철회한다.** 두 실행 모두 단계 타이머(프로파일러)가 켜져 있었고, 기계 부하가 달랐으며(19.7→9.2 vs 7.7→5.7), 스캔이 몰린 앞 30 SIM s만 쟀다. 그래서 가속 효과로 볼 수 없다(3절 표는 기록으로만 남긴다).
- v3/v5/v6의 새 항목(A1, A3)은 오프라인 재생에서 비트 동일을 확인했다(4절). 재생 400프레임에서 29.1 → 18.8 s다. 실제 전 구간 효과는 다음 연구 실행의 `walltime_profile.jsonl`로 다시 정리한다(추정 약 2.9 → 2.4~2.5 wall/SIM, 미측정).
- 가장 큰 시간은 **제어기 콜백 `on_frames`(위치 추정 PF + OpenCV 벽 관측)**다. 물리(`mj_step`)와 렌더(GPU 읽기 대기 포함)가 그 다음이다.
- 느려지는 가장 큰 외부 원인은 **기계 부하**다.
  - 부하 100~170(무거운 프로세스 9개, swap 4.9/6 GiB)에서는 같은 일이 10~50 wall/SIM까지 늘었다.
  - 동시 실행 3개(부하 10~20)에서도 SIM 초당 CPU 시간이 단독보다 약 1.3~2.5배 많았다.
- **우선순위:** zsh 기본 옵션 `BG_NICE` 때문에 `( … ) &`로 띄운 실행은 nice 5로 돈다. 공용 v98 실행기 `outputs/v98-probe-tools/launch_v98_{runs,probes}.sh`도 해당된다. 사용자 규칙(2026-10-05 "우선순위 낮추지 마")에 따라 실행기에 `setopt NO_BG_NICE`가 필요하다. renice, taskpolicy, QoS 낮추기는 금지다.
- **감시 장치 수면 보정:** macOS `time.perf_counter`(mach_absolute_time)는 기계가 잠든 시간을 빼고 센다. 실제로 감시 장치 wall 1327 s, 벽시계 1941 s(약 10분 수면)였다. 그래서 창마다 `clock_wall_s`(`time.time`)를 함께 기록한다.

## 2. 환경

- Mac: Apple M3, 성능 코어 4개 + 효율 코어 4개, 16 GiB, swap 5 GiB. Python 3.12, MuJoCo 3.12.0.
- 물리: timestep 0.00025(SIM 초당 `mj_step` 4000번), noslip 10. `cargo_noslip_v1`은 2026-09-18 `local_contact_fine`(ce3bc957)의 0.00025를 물려받았다.
  - v98 경로는 이 기록 전까지 `exact-v1`(PR #209 구동 커널)을 쓰지 않았다.
- 렌더: CGL(GPU) `Apple M3`, `2.1 Metal - 91.7`. `MUJOCO_GL`은 설정되지 않았고 Darwin은 항상 `mujoco.cgl`이다.
  - 로봇 카메라는 640×480, 2대 × 20 Hz로 SIM 초당 40장이다. 렌더 전용 스레드 1개에서 처리한다(CGL 문맥이 스레드에 묶임).
  - 설정의 offwidth 1280×720은 이 경로에서 쓰지 않는다.
- 한 틱(0.05 SIM s)의 순서:
  1. `eval_sample`
  2. `capture`(렌더 → JPEG q82 → base64 → sha256 → 디코드 → .jpg 쓰기 + frames.jsonl)
  3. `on_frames`(로봇별 OpenCV 벽 관측 + PF 갱신)
  4. `step`/`arm_step`
  5. `issue`
  6. `advance_to`(200 substep)
- 스레드 구성(프로세스당): 주 스레드 1개, 렌더 executor 1개(Metal 대기열), GCD/OpenCV 작업자 8개.
  - GCD/OpenCV 작업자는 표본상 약 99% 쉬고 있다.
  - BLAS/OMP 스레드는 실제로 일하지 않는다.

## 3. 단독 저부하 단계표 (30 SIM s, align_to_carry 앞부분, 원본: `outputs/v98-walltime-profile-20261005/lo-r*`)

> **주의:** 이 표의 두 열은 부하가 다르고 둘 다 단계 타이머가 켜진 앞 30 SIM s다. 가속 효과의 근거로 쓰지 않는다(1절 철회). 단계별 비율을 보는 용도로만 남긴다.

| 단계 | 가속 없음 (lo-r1) wall/SIM | v98-exact-v1 (lo-r2) wall/SIM |
|---|---:|---:|
| 전체 루프 | **4.53** (CPU 4.25, 부하 19.7→9.2) | **2.27** (CPU 2.20, 부하 7.7→5.7) |
| 제어기 `on_frames` | 2.98 | 1.11 |
| 물리 `advance_to` (그중 `mj_step`) | 0.72 (0.55) | 0.47 (0.41) |
| 렌더 대기 (GPU 렌더 / 픽셀 읽기) | 0.50 (0.29 / 0.16) | 0.42 (0.23 / 0.16) |
| `step` + `arm_step` | 약 0.2 | 0.19 |
| JPEG·base64·sha256·파일·JSONL | < 0.1 | < 0.06 |

- 픽셀 읽기는 wall 0.16, CPU 0.015다. GPU 완료를 기다리는 시간이다.
- PF 내부(cProfile 25 SIM s, 고부하라 비율만 참고):
  - `vision_loc.expected_rows`가 스캔마다 같은 입자 배열에 **두 번** 불린다(`zone_final_pair_scan.quality`와 `scan_loglik`).
  - 그 안의 `first_blocked`가 전체의 33%, `_fan_corners`가 7%다. OpenCV 관측은 약 9%다.
- 스레드 제한(`OMP/OPENBLAS/VECLIB_MAXIMUM_THREADS=1` + `cv2.setNumThreads(1)`, lo-r3)은 바이트가 같았다(1220/1224). 하지만 2.93 wall/SIM으로 오히려 느렸다(표본 1개).
  - 단독 실행에는 **권장하지 않는다.**

## 4. 비트 동일 가속 `v98-exact-v1` (`harness/zone_pair_highpose_exact_speedups.py`, 기본 `none`)

| 항목 | 내용 | 동일성 근거 |
|---|---|---|
| `expected_memo` | `pf.expected(px, pose)`의 마지막 1개 결과를 캐시한다. 입력이 필터 자신의 `pf.px`일 때만 쓴다. | 키에 입자 배열 바이트, 자세, 적재 상태, 열 위치 바이트가 모두 들어간다. 하나라도 바뀌면 다시 계산하고, 결과는 복사본으로 돌려준다(시험: `tests/test_v98_exact_speedups.py`). |
| `drive_kernel` | `sim.exact_speedups.install_drive_kernel`(PR #209 비트 동일 구동 커널)을 v98 장면에 설치한다. | PR #209의 동일성 검사 |
| `schedule_memo` | 시작 시 3번 반복되던 `schedule_bytes` json 직렬화를 1번만 한다. | 순수 함수 |

- 캐시 적중/실패: r1 339/169, r2 439/267. 스캔당 1:1로 예상했는데 약 2:1이었다. 정지 중 연속 프레임 사이의 재사용으로 보이며, 확인하지 않았다.
- **바이트 비교 도구** `scripts/compare_v98_runs.py`: 두 사례 폴더의 모든 파일을 sha256으로 비교한다. JSON/JSONL은 키 경로 단위로 비교한다. 다음 **정확한 경로**만 허용한다.
  - `result.json`의 `/loadavg_start[]`, `/loadavg_end[]`
  - `student_record.json`의 `/pair[]/status_messages[]/task_id`(uuid4), `/robots/<r>/provider/provider/lifecycle[]/{before,after}/pf_id`(id(pf)), `inference_wall_ms/{p50,p90,max}`
  - `eval_only/dr_receipt_nees.json`의 `/source/student_record{,_sha256}`
  - 위 파일에 해당하는 `artifacts.sha256.json` 항목
  - 그 밖의 차이(명령, 프레임 바이트, 사건, 개수, 빠진 파일)는 모두 행동 차이로 판정한다.
- **전체 길이 판정:** `IDENTICAL_UP_TO_ALLOWLIST`(7절). 비교 중 `eval_only/dr_receipt_nees.json`의 `/truth_files/{r1,r2}/path`(실행 폴더 절대 경로)도 허용 목록에 넣었다. 해당 파일의 sha256과 행 수는 계속 같아야 한다.

### 4.1 추가 세트 (`SETS` in `harness/zone_pair_highpose_exact_speedups.py`)

| 세트 | 구성 | 상태 |
|---|---|---|
| `v98-exact-v2` | v1 + `render_pipeline`(A2) | 채택 안 함(9절) |
| `v98-exact-v3` | v1 + `pf_geometry_shared`(A1) | 오프라인 비트 동일 |
| `v98-exact-v4` | v1 + A1 + A2 | 채택 안 함 |
| `v98-exact-v5` | v4 + `opencv_exact`(A3) | 채택 안 함(A2 포함) |
| **`v98-exact-v6`** | v1 + A1 + A3 | **연구 실행용 확정** |

- **A1 `pf_geometry_shared`** (`harness/zone_pair_highpose_pf_geometry_shared.py`): 동결 파일 `vision_loc.expected_rows`를 비트 동일하게 다시 썼다. 동결 파일은 고치지 않고 모듈 속성만 바꾸며, 다섯 함수 소스 sha256이 기록값과 다르면 설치를 거부한다.
  - 바닥·윗선 두 추적이 같이 쓰는 계산(형 변환, ddx/ddy, 모서리 행렬식과 `ok`)을 한 번만 한다.
  - `mu` 분자를 추적마다 한 번만 계산한다.
  - 모서리 오프셋과 틈 검사를 입자 단위 (P,1)에서 한다.
  - 시간 `t`는 `ok & mu >= 1` 후보에서만 계산한다.
  - 같은 float32 연산을 같은 순서로 하므로 원소별 값이 같다. min은 순서와 무관하다.
  - 증명: 기록·교란 입력 110개와 측정 자세의 무작위 입자 구름(P 2000/7/4/1, 무하중·적재)이 비트 동일이다. 400프레임 오프라인 재생에서 보고·로그 가중치·입자 바이트가 같다. 시험 `tests/test_highpose_pf_geometry_shared.py`. P2000 호출당 49 → 28.6 ms.
- **A3 `opencv_exact`** (`harness/zone_pair_highpose_opencv_exact.py`): 동결 VIS3 `markerless_probe.detect_boundaries` 복사본이다. 카메라 모델별로 이미지와 무관한 기하(행, 추적, 범위, 창 인덱스)를 캐시하고(LRU 16), 수집은 평면 인덱스 `take`로 한다. 바이트가 같은 연속 프레임(약 12%)은 이전 관측을 깊은 복사로 재사용한다. 고정 소스 sha256이 다르면 설치를 거부한다.
  - 증명: 프레임×모델 215쌍이 비트 동일하다. A1+A3 재생(400프레임)도 바이트가 같다. OpenCV 관측 호출당 16.1 → 13.0 ms.
- A4(프레임 게이트 JPEG 재디코드 재사용)와 A5(기타 파이썬 부담)는 0.5% 미만으로 추정되어 구현하지 않았다.
- **B7 숨은 물체 8개 물리 분리: 버림.** 블록 3개, team_beam, 창고 물건 3개, dispatch_box(자유 관절, 접촉 없음, 비활성 weld 20개)를 MjSpec으로 빼고 물리만 돌렸다. 명령이 0이어도 1스텝부터 r1·r2·cargo_beam 상태의 마지막 자리가 달라졌다. 4000스텝 뒤 최대 차이는 8e-6이고, 모델 통계(`stat.meaninertia` 등)를 맞춰도 같았다. 1스텝 비용도 0.0940 vs 0.0981 ms로 이득이 없었다(접촉·제약이 없는 자유도는 거의 비용이 없다).
  - 참고: r3까지 빼면 0.094 → 0.057 ms(−39%)다. 하지만 접촉 수가 바뀌어 행동 변경 후보이고 보류했다(8절).
- 원본: `outputs/v98-walltime-profile-20261005/microbench/`, 우선순위표 `speedup_priority.md`(sha256 `41d3e446…`).

## 5. 감시 장치 (`sim/walltime_monitor.py`, 래퍼 `scripts/run_pair_highpose_walltime.py`, 선택·기본 꺼짐)

```bash
python scripts/run_pair_highpose_walltime.py [--walltime-window-sim-s 10] [--no-monitor] [--speedups none|v98-exact-v1..v6] -- <run_pair_highpose.py 인자>
```

- 사례 폴더 밖, 실행 루트에 `walltime_profile.jsonl`(schema `ugrp.sim_walltime_monitor.v1`)을 쓴다. 그래서 `artifacts.sha256.json`에 영향이 없다.
  - SIM 10초 창마다 기록한다: wall/SIM(`perf_counter`, 수면 제외)과 `clock_wall_s`(`time.time`, 수면 포함), 프로세스 CPU/SIM, CPU 사용률, 단계별 시간(물리, 렌더 대기, 렌더 GL@렌더 스레드, 캡처, 제어기, JSONL, 진행), 부하 평균, RSS, 스레드 수, 문맥 전환, swap, 메모리 압력.
- 가속을 켜면 실행 루트에 `speedups.json`(schema `ugrp.v98_run_speedups.v1`, 적중 수 포함)을 쓴다.
- 감시 장치와 가속은 실행 코드 밖의 실행 기반 시설이다. 출력 바이트를 바꾸지 않는다는 것은 비교 도구로 확인한다. 바뀌면 새 실행 번들과 동등성 증명이 필요하다.

## 6. 동시 실행·우선순위·부하 (같은 코드 a3415342, seed 911)

| 묶음 | 동시 수 | nice | SIM 21 s 이후 평균 wall/SIM, CPU/SIM | 부하(1분) | 상태 |
|---|---:|---:|---|---|---|
| 15:23 4개(wtA, wtB, align wtX, case wtX) | 4 | 5 → 15(15:24 조정자 renice +10) | align wtB 4.78/4.46, align wtX 4.61/4.26, case wtX 6.10/5.74 | 10~126 | 조정자가 중지(우선순위 실수), 결과 아님 |
| 15:36 3개 n0 | 3 | 5(zsh BG_NICE) | 첫 창만: align wtX 2.71, case wtX 3.18 | 4~5 | 내가 중지(nice 5), 결과 아님 |
| 15:37 3개 n0b | 3 → 1(15:47) | **0** | align wtX 4.20/3.81, case wtX 6.25/5.58 | 7~20 | 15:47 조정자가 wtA·case 중지("한 번에 하나씩"), align wtX만 계속 |

- 같은 SIM 창끼리 align wtX를 비교했다(wall/SIM). 21–31: nice 15 5.77 vs nice 0 5.67. 31–41: 4.21 vs 4.55. 41–51: 5.52 vs 3.55. 51–61: 4.19 vs 3.67.
  - nice 0이 약간 낫다. 하지만 동시 수가 4 대 3으로 달라서 우선순위만의 효과를 분리할 수 없다.
- 4개 묶음의 11–21 창(15.5~19 wall/SIM, CPU 사용률 53~59%)은 **부하 급등(111~126)**과 겹친다. 급등 원인 프로세스는 기록이 없다(미확인).
  - "낮은 우선순위가 효율 코어 배치를 일으켰다"는 미확인 가설로만 남긴다.
- 동시 3개(부하 10~20)일 때 창별 CPU/SIM은 3.4~8.5였다. 같은 구간 단독 저부하(lo-r2)는 1.6~3.2였다.
  - 처리량 합계는 약 0.6~0.8 SIM s/wall s로, 단독 0.44의 **약 1.5배**에 그친다(실행 수만큼 늘지 않는다).
- align wtX-n0b 단독 구간(15:47 이후) 결과: 아래 7절.

## 7. 전 구간 판정: 가속 없음(wtA-solo) vs v1(wtX-n0b)

- 두 실행: align_to_carry, a3415342, seed 911, nice 0.
  - wtA-solo: 가속 없음, 감시 장치 끔, 단독. 16:28:18 종료(exit 0).
  - wtX-n0b: `v98-exact-v1`, 감시 장치 켬. 15:47까지 3개 동시, 이후 단독.
- 바이트 비교(`scripts/compare_v98_runs.py`): 15328 대 15328 파일, 동일 15324, 한쪽만 0, 행동 차이 0. 다른 4개는 `result.json`, `student_record.json`, `eval_only/dr_receipt_nees.json`의 허용 필드와 `artifacts.sha256.json`이다. 판정 **`IDENTICAL_UP_TO_ALLOWLIST`**. 원본: `outputs/v98-walltime-profile-20261005/equiv-wtA-solo-vs-wtX-n0b-full.json`.
- 속도는 두 실행이 모두 단독이던 같은 SIM 구간(121–321 s)에서 프레임 파일 mtime으로 쟀다. 가속 없음 2.91, v1 2.88 wall/SIM으로 차이가 거의 없다.
  - wtX-n0b는 감시 장치가 켜져 있었고 wtA-solo는 꺼져 있었다. 감시 장치 부담은 따로 재지 않았다.
  - wtX-n0b 감시 장치 기록에서 `perf_counter` 합계 1327 s, 벽시계 1941 s였다. 기계 수면 약 10분이 빠진 것이다(1절 수면 보정).

## 8. 바이트가 바뀌는 후보 (목록만, 적용하지 않음; 적용하려면 새 번들 + 동등성/성능 재검증)

기대 효과는 3절 단계표 비율에서 계산한 추정이며 측정하지 않았다. 조정자 결정(2026-10-05): 아래와 r3 분리, timestep, 해상도는 행동을 바꾸므로 **E2E 뒤 후보로 기록만** 한다(카메라 주기 5 Hz는 기각, 10 Hz와 정지 중 PF 갱신 생략은 보류).

| 후보 | 줄어드는 몫 (wall/SIM) | 기대 효과 | 위험 |
|---|---|---|---|
| 렌더를 실제 소비 빈도로 줄이기. 측정에 쓰인 프레임은 r1 269/9832, r2 330/9832(2.7~3.3%)다. | 렌더+캡처 0.48. 소비되지 않은 프레임의 OpenCV/PF 갱신까지 빼면 최대 약 1.5 | 렌더만: 약 21%(1.27배). 프레임 처리까지: 최대 약 65%(약 2.9배) | 제어기 입력 시점이 바뀐다. 어떤 프레임을 쓸지 고르는 일이 제어기 쪽 판단이라 별도 설계가 필요하다. |
| timestep 0.00025 → 0.0005 | 물리 0.47의 약 절반, 0.23 | 약 10%(1.11배) | 접촉·파지 물리가 바뀐다. 2026-09-15 정지 파지 진단에서 0.002→0.00025로 바꾼 이유(미끄러짐)를 다시 확인해야 한다. |
| PF 입자 수 절반 | PF 갱신(on_frames 1.11의 약 74%)의 절반, 약 0.41 | 약 18%(1.22배) | 위치 추정 정확도와 재위치 성공률이 바뀐다. |
| 장면에서 r3 분리 | 물리 1스텝 −39%(마이크로벤치), 약 −0.19 | 약 6~7% | 접촉 수가 바뀐다. 비트 동일 아님(B7 사전 검사와 같은 이유로 추정). |
| 렌더 해상도 낮추기 | 0.1~0.2 | 약 5% | 인식 충실도 |

## 9. 남은 비트 동일 후보

- **렌더–물리 겹치기(조정자 제안 1): 불가.** 다음 틱 명령이 `on_frames`의 결과에 의존하고, `on_frames`는 이번 프레임이 필요하다. 다음 `advance_to`를 렌더와 동시에 할 수 없다.
- **비동기 픽셀 읽기(PBO 이중 버퍼):** 읽기 대기 0.16 wall/SIM 동안 겹칠 일이 다른 로봇 렌더뿐이라 A2와 같은 구조다. 이득이 거의 0으로 보여 시제품을 만들지 않았다(U).
- **MuJoCo 스레드 풀:** 접촉 28개 규모에서 이득이 의심스럽고 비트 동일성도 미확인이다(U).
- **`render_pipeline`(구현만, `v98-exact-v2`, 채택 안 함):** r1 제어기 갱신 동안 렌더 스레드에서 r2를 미리 렌더한다.
  - 최대 기대치는 r2 렌더 시간, 약 0.2 wall/SIM(약 9%)이다.
  - 소규모 시험에서 `Renderer.render`(mjr_render) 동안 주 스레드의 순수 파이썬 루프는 느려지지 않았다(GIL을 놓는 것으로 보임). 반대로 렌더는 주 스레드 파이썬과 GIL을 다투어 0.43→0.78 s로 늘었다. 그래서 실제 이득은 0.2보다 작다.
  - 조정자 결정으로 끈다. `V3.capture` 소스 sha256이 바뀌면 설치를 거부한다.
- `quality()`의 곡률 계산용 `loglik`은 작은 입자 집합에 2280번 불리지만 전체의 약 1%다. 고칠 가치가 낮다.

## 10. 권장 설정

- 실행은 **한 번에 1개**(사용자 2026-10-05). 동시 실행은 처리량을 약 1.5배까지만 늘리고, 실행마다 느려진다. 사용자 작업과도 경쟁한다.
- **nice 0.** zsh 실행기에는 `setopt NO_BG_NICE`를 넣는다. renice, taskpolicy, QoS 낮추기는 금지다.
- 스레드 환경 변수(`OMP_NUM_THREADS` 등)는 **설정하지 않는다**(3절).
- 시작 전 부하 평균 8 미만, swap 여유를 확인한다. TensorBoard, Spotlight 색인 같은 큰 상주 프로세스를 정리한다.
- 가속: 연구 실행은 `--speedups v98-exact-v6`(조정자 결정). 실행 루트의 `speedups.json`에 설치 여부와 소스 sha256이 남는다.

## 11. 원본 위치

- `outputs/v98-walltime-profile-20261005/`: 드라이버, 단계표 실행 lo-r0~r3, cProfile, 표본, 실행기, 로그, `launch_load.txt`(모든 실행의 시작/끝 부하·swap·nice 기록), `SHA256SUMS.txt`
- `outputs/v98-dev-*-a3415342-s911-*`: 동시 실행 폴더(중지된 것은 `STOPPED_BY_USER.json` 또는 `launch_load.txt`의 STOPPED 줄)

## 참고 자료 (V = 원문 확인, U = 미확인)

- V: zsh 매뉴얼 `zshoptions(1)` BG_NICE: "Run all background jobs at a lower priority. This option is set by default." 로컬 `man zshoptions`로 확인했다.
- V: MuJoCo Python 문서. 바인딩은 C 함수가 실행되는 동안 GIL을 놓는다. https://mujoco.readthedocs.io/en/stable/python.html (mjr_render 포함 여부는 9절 소규모 시험만 근거)
- V: MuJoCo 계산 문서. noslip은 주 풀이기 뒤의 PGS 후처리이고, 스레드 풀은 충돌·섬 단위 풀이를 병렬화한다. https://mujoco.readthedocs.io/en/stable/computation/index.html
- V: Nav2 AMCL 설정 `update_min_d`/`update_min_a`(정지 중 갱신 생략의 표준 예). https://docs.nav2.org/configuration/packages/configuring-amcl.html
- V: Walsh & Karaman, CDDT: Fast Approximate 2D Ray Casting for Accelerated Localization, arXiv:1705.01167. https://arxiv.org/abs/1705.01167
- U: Thrun, Burgard & Fox, Probabilistic Robotics 6.4 likelihood field. Fox, KLD-sampling(2003).
- U: Apple `mach_absolute_time`이 수면 시간을 빼는 동작의 공식 문구. 이 기록에서는 감시 장치 합계와 벽시계 차이(1327 vs 1941 s)로 확인했다.
- U: Apple Silicon에서 낮은 우선순위·QoS 스레드가 효율 코어에 배치되는 동작(Apple 공식 문서 문구 미확인). 이 기록에서는 분리해 측정하지 못했다.
- V(저장소): 이전 속도 기록 `docs/sim_speed.md`(exact-v1, PR #209), `experiments/2026-09-26-sim-speed/README.md`(mj_step 37%, 렌더 28%, 과부하 2.3배), `experiments/2026-10-03-calib-fast-guard/`(파이썬 guard, 0.03~0.05배 → 약 1.0배).
- V: cProfile, 계층별 타이머, 창 단위 감시는 Python 표준 `cProfile`/`time.perf_counter`/`time.thread_time`과 macOS `libproc` `PROC_PIDTASKINFO`, `sysctl vm.swapusage`를 썼다.
