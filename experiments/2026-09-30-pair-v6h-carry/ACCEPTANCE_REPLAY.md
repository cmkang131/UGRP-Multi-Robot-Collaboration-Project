# b-v6h1 인수 재생 (실제 물리 재생)

이 문서는 재생 기록 두 개를 담는다. 최신은 PR #292 head `3c4fe30e`(판정 PASS), 이전은 `3afc61b0`(판정 FAIL)이며 이전 기록은 그대로 두었다.

## 재생 2: `3c4fe30e` — 판정 PASS (lag-on 10건 모두 비트 단위로 같음, lag-off 확인도 tX0와 같음)

**판정: PASS. 등록 코드(b-v6h1)를 probe 원본 코호트와 같은 조건으로 다시 돌린 결과, 시험한 lag-on(축방향 지연 보정 켬) 10건 모두 명령 기록(commands.json)의 SHA-256, leg 결과, leg 검사 값이 probe와 비트 단위로 같았다. lag-off sanity(tX0 X01)도 probe tX0와 같다.** 앞선 FAIL의 원인이던 충돌 여유(margin)의 시그마 배수 적용 범위를 이 head가 등록 소스로 probe와 같게 맞췄고, 이번에는 시험용 덮어쓰기·probe 패치 없이 등록 필드(`--policies b-v6h1`)만으로 통과했다.

이 기록은 SIM 시간, 모델 호출 0, weld OFF의 정책 동등성 시험이다. leg 0~1(`--chain-stop-leg 1`)까지만 비교했고 leg 2 이후(측방 이동, 문 통과, 내려놓기)는 비교하지 않았다. 확증·E2E·실물 성공 근거가 아니다.

### 실행 조건

| 항목 | 값 |
|---|---|
| 등록 소스 | PR #292 head `3c4fe30e2197518443b195392212b0341507ac59` (branch `codex/pair-v6h-register`, “Match b-v6h1 sigma scope to the exploratory probe”). 작업 트리 깨끗, 실행 내내 SHA 변경 없음 |
| 번들 / workflow / 봉인 | `zone-pair-v83-carry-door-gain` / 2.16.0 / 봉인 전(pre-seal), 봉인 변경 없음 |
| 명령 | `--stage chain --sources teacher --policies b-v6h1 --prior-std e2e --chain-stop-leg 1 --render-profile floor_light_v1 --pf-track --contact-track --workers 4 --omp-threads 1` (등록 필드만) |
| 사례 | 이전 재생과 같은 11건(`plan.json`은 소스 SHA와 raw 경로만 바뀜): tS S01·S02·S03·S07, tR hR2_01·hR2_04(913), tX1b X06, tX1 X01·X03(913)·X00_F_hR2_04, lag-off sanity(tX0 X01) |
| 환경 | 렌더링 정상, HOST_ERROR 0. Python `.venv-sim-worker-mac`, worker 4, OMP=1. 전원 AC 유지(점검 64회 중 배터리 0), 여유 디스크 충분 |
| 물리 잠금 | owner claude, branch `claude/v6h1-acceptance-run`, driver PID로 획득(다른 에이전트 잠금이 풀린 뒤 시작, 예상 20분) → 정상 해제. 시작 부하 평균 [17.6, 23.7, 26.7], 종료 [30.5, 25.8, 26.0](다른 작업 CPU 사용 중; SIM 시간 재생이라 결과에 영향 없고 wall 시간 측정으로 쓰지 않는다). driver 총 996.6 s |

### 사례별 비교 (probe 원본 vs 등록 b-v6h1 @ 3c4fe30e)

`commands.json` SHA-256은 앞 12자리(전체는 [acceptance_replay.json](acceptance_replay.json)의 `replay_3c4fe30e`). leg 끝 오차는 mm(L0 / L1). 등록과 probe의 값은 모두 같아 한 번만 적는다.

| 코호트 / 사례 / 시드 | commands SHA (등록 = probe) | 동등성 | 처음 다른 명령 | leg 끝 오차 (L0 / L1) |
|---|---|---|---|---|
| tS / S01 / 911 | `70bcb8ce94ff` | 같음 | 없음 | 56.510 / 50.784 |
| tS / S02 / 911 | `071532a4e2c5` | 같음 | 없음 | 40.982 / 34.659 |
| tS / S03 / 911 | `0b699a18311d` | 같음 | 없음 | 25.389 / 19.643 |
| tS / S07 / 911 | `c0c5fcd8dfe2` | 같음 | 없음 | 57.882 / 72.124 |
| tR / hR2_01 / 911 | `5f9da3641faf` | 같음 | 없음 | 12.898 / 33.174 |
| tR / hR2_04 / 913 | `cfd6df9a6e7e` | 같음 | 없음 | 70.066 / 67.623 |
| tX1b / X06 / 911 | `d1ef368a7de5` | 같음 | 없음 | 49.206 / 62.409 |
| tX1 / X01 / 911 | `2d2f77a4d529` | 같음 | 없음 | 49.055 / 81.911 |
| tX1 / X03 / 913 | `c28c5a2e5663` | 같음 | 없음 | 34.377 / 28.658 |
| tX1 / X00_F_hR2_04 / 911 | `2ae150658b67` | 같음 | 없음 | 51.041 / 55.710 |
| tX0 / X01 / 911 (lag-off sanity) | `f9d3bd1482ff` | 같음 (tX0와) | 없음 | 69.176 / 124.339 |

이전 재생에서 갈라졌던 6건(S03·S07·hR2_04·X01·X03·X00_F_hR2_04)과 lag-off sanity가 모두 같아졌다. 11건 모두 두 로봇의 모든 명령이 probe와 같다(`command_json_equal`), 분류는 probe와 같은 `STAGE_BUDGET_EXHAUSTED`(leg 1까지만 돌리는 시험의 정상 종료).

### 검증·보관

- raw: `/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3c4fe30e-claude-20260930` (cases.jsonl SHA-256 `6e9437151b158a06975666a6b5be7c1f3013a550a22722740c0d041addbecbaf`, plan.json `0695ece7431de869f0cde089a138781bc5029f4e43e5dccf7424261dda219b5b`, driver.py `2752abed0877b1e2a2a623b2224a3d0c638580c22dd368c6a716215a276f3fea`). 로컬 보관이며 원격 백업이 아니다. Google Drive는 쓰지 않았다.
- probe 원본 raw는 driver가 실행 전 SHA-256(commands.json, cases.jsonl, plan.json)을 재확인했고 변경 없음.
- 같은 SHA에서 `tests/test_zone_pair_v6h.py` + `tests/test_zone_pair_registered_source.py`: 164 passed (driver가 재생 뒤 잠금 안에서 실행, exit 0).
- 남은 범위: leg 2 이후는 비교하지 않았다. 이 PASS는 leg 0~1에서 b-v6h1이 probe b-v6h와 동등하다는 뜻이지 확증 성능이 아니다.
- TensorBoard 스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/0930-v6h1-acceptance-3c4fe30e-replay`, 설정 키 `v6h1_acceptance_replay_3c4fe30e_claude_20260930`. 생성 스크립트: `analysis/acceptance_3c4fe30e/build_section.py`(JSON 구간), raw 폴더의 `build_tb.py`.

---

## 재생 1: `3afc61b0` — 판정 FAIL (아래는 당시 기록 그대로)

# (재생 1) b-v6h1 인수 재생 — 판정 FAIL (10건 중 4건만 같음)

**판정: FAIL. 시험한 lag-on(축방향 지연 보정 켬) 10건 중 4건만 명령 기록(commands.json)의 SHA-256과 leg 결과가 비트 단위로 같고, 6건은 leg 1의 “집기 전 시야 확인(pregrasp look)”에서 갈라진다. 원인은 시험용 덮어쓰기로 확정했다: probe(b-v6h)는 충돌 여유(margin)의 시그마 배수를 모든 팔 스윕에서 1/1로 낮췄지만, 등록 코드(b-v6h1)는 이를 “짐을 든 채 차체가 움직이는 경우”에만 적용한다. 등록 코드는 수정하지 않았다.**

이 기록은 SIM 시간, 모델 호출 0, weld OFF의 정책 동등성 시험이다. 확증·E2E·실물 성공 근거가 아니다. 앞선 Codex 시도(`codex/v6h1-acceptance`, 11건 모두 렌더링 연결 오류 `CGLError`)는 별도 기록으로 남아 있다.

## 실행 조건

| 항목 | 값 |
|---|---|
| 등록 소스 | PR #292 head `3afc61b00f2c127ac3fbe2be5e7bb57da989b15a` (branch `codex/pair-v6h-register`; 검토 반영 커밋 이후). Codex 시도는 `2c863fda`였고 두 커밋 사이 제어기 코드 차이는 없다(차이: 검토 문서, 승인용 admission 스크립트, `run_pair_stage_probes.py`의 봉인 경로 분기 — 비봉인 case에는 영향 없음) |
| 번들 / workflow / 봉인 | `zone-pair-v83-carry-door-gain` / 2.16.0 / 봉인 전(pre-seal), 봉인 변경 없음 |
| 명령 | `--stage chain --sources teacher --policies b-v6h1 --prior-std e2e --chain-stop-leg 1 --render-profile floor_light_v1 --pf-track --contact-track --workers 4 --omp-threads 1` (등록 필드만 사용, probe 패치 없음) |
| probe 옵션 → 등록 필드 | k1g → `loaded_k_xy=loaded_k_yaw=1.0`, `loaded_gate_yaw_deg=(5,4)` / p2f → `progress_arm_on_moved_fix` / pf → `carry_fwd_gain=0.9483378899463337` / axial → `carry_axial_lag` |
| 사례 | Codex가 고정한 `plan.json`(소스 SHA만 갱신)을 그대로 사용: tS S01·S02·S03·S07, tR hR2_01·hR2_04(913), tX1b X06, tX1 X01·X03(913)·X00_F_hR2_04, 그리고 lag-off sanity(tX0 X01) |
| 환경 | 렌더링 정상(스모크 S01부터 완주, CGLError 없음). Python `.venv-sim-worker-mac`, 동시 worker 4, OMP=1. 전원 AC 전체 확인(73회 점검 중 배터리 0), 시작 여유 디스크 충분 |
| 물리 잠금 | owner claude, branch `claude/v6h1-acceptance-run`, driver PID로 잠금 획득 → 정상 해제(재생, 시험용 원인 확인 각각). 잠금 시작 시 부하 평균 [35.3, 21.0, 19.5](다른 작업이 CPU를 쓰는 중이었음; 이 재생은 SIM 시간이라 결과에는 영향이 없지만 wall 시간 측정으로 쓰지 않는다) |

## 사례별 비교 (probe 원본 vs 등록 b-v6h1)

`commands.json` SHA-256은 앞 12자리만 적었고 전체는 [acceptance_replay.json](acceptance_replay.json)에 있다. leg 끝 오차는 mm(L0 / L1). “처음 다른 명령”은 로봇·명령 번호(0부터)·SIM 시각이다. 이 시각 앞의 명령은 두 로봇 모두 비트 단위로 같다(leg 0의 700여 개 명령과 L0 끝 오차가 모두 일치).

| 코호트 / 사례 / 시드 | probe SHA | 등록 SHA | 동등성 | 처음 다른 명령 | 등록 끝 오차 (L0 / L1) | probe 끝 오차 (L0 / L1) | 등록 결과 |
|---|---|---|---|---|---|---|---|
| tS / S01 / 911 | `70bcb8ce94ff` | `70bcb8ce94ff` | 같음 | - | 56.510 / 50.784 | 56.510 / 50.784 | STAGE_BUDGET_EXHAUSTED (probe와 같음) |
| tS / S02 / 911 | `071532a4e2c5` | `071532a4e2c5` | 같음 | - | 40.982 / 34.659 | 40.982 / 34.659 | 같음 |
| tR / hR2_01 / 911 | `5f9da3641faf` | `5f9da3641faf` | 같음 | - | 12.898 / 33.174 | 12.898 / 33.174 | 같음 |
| tX1b / X06 / 911 | `d1ef368a7de5` | `d1ef368a7de5` | 같음 | - | 49.206 / 62.409 | 49.206 / 62.409 | 같음 |
| tS / S03 / 911 | `0b699a18311d` | `417f9975aa54` | **다름** | r1 #710 / 28.2 s | 25.389 / (없음) | 25.389 / 19.643 | PREGRASP_NO_SAFE_VIEW |
| tS / S07 / 911 | `c0c5fcd8dfe2` | `558d599a49f0` | **다름** | r1 #730 / 30.2 s | 57.882 / (없음) | 57.882 / 72.124 | PREGRASP_NO_SAFE_VIEW |
| tR / hR2_04 / 913 | `cfd6df9a6e7e` | `f64e47c99b8f` | **다름** | r1 #730 / 30.2 s | 70.066 / (없음) | 70.066 / 67.623 | PREGRASP_NO_SAFE_VIEW |
| tX1 / X01 / 911 | `2d2f77a4d529` | `97ee81b47d48` | **다름** | r1 #730 / 30.2 s | 49.055 / (없음) | 49.055 / 81.911 | PREGRASP_NO_SAFE_VIEW |
| tX1 / X03 / 913 | `c28c5a2e5663` | `3702e43b0811` | **다름** | r1 #730 / 30.2 s | 34.377 / (없음) | 34.377 / 28.658 | PREGRASP_NO_SAFE_VIEW |
| tX1 / X00_F_hR2_04 / 911 | `2ae150658b67` | `2a2a3f44bd2d` | **다름** | r1 #730 / 30.2 s | 51.041 / (없음) | 51.041 / 55.710 | PREGRASP_NO_SAFE_VIEW |
| tX0 / X01 / 911 (lag-off sanity) | `f9d3bd1482ff` | `bb078374a69b` | **다름** | r1 #735 / 30.7 s | 69.176 / (없음) | 69.176 / 124.339 | PREGRASP_NO_SAFE_VIEW |

(없음 = 등록 실행이 leg 1을 시작하지 못해 leg 1 기록이 없다. lag-on 10건 판정에서 sanity는 제외했다.)

## 처음 갈라지는 곳

- 모든 갈라진 사례에서 처음 다른 명령은 **leg 1 “집기 전 시야 확인(pregrasp_look)” 시작 시각** 바로 그 순간이다(S03 28.2 s, 나머지 30.2 s, lag-off 30.7 s).
- 명령 차이: probe는 팔 서보 3번을 704 펄스로 움직이는 시야 확인 자세(`arm servo 3 pulse 704`, 0.1 s 뒤 시각)를 내리고, 등록 코드는 같은 순간에 `hold`를 낸다. 시각 차이는 0.1 s, 명령 종류가 다르다. 이후 등록 쪽 r2가 `PREGRASP_NO_SAFE_VIEW`로 실패한다(안전한 시야 방향이 하나도 없다고 판단, `harness/zone_pair_grasp.py:219`).
- 갈라지기 전 구간은 모두 같다: 두 로봇의 leg 0 전체 명령과 L0 끝 오차 소수점 끝자리까지 일치.
- 같은 갈림이 lag-off sanity에서도 그대로 나타나므로(시각만 0.5 s 늦음) 축방향 지연 보정(axial lag)이 원인이 아니다. 또 “같음”으로 나온 4건은 leg 0 끝 시그마가 상대적으로 작았던 사례(시그마 xy 0.0386~0.0411, yaw 0.0382~0.0403)이고, 갈라진 6건은 대체로 시그마가 더 컸다. 경계가 좁아 크기만으로 나뉘지는 않는다(S03은 yaw 0.0382인데 갈라짐, 마진은 lever에 따라 다름).

## 원인 (시험용 덮어쓰기로 확정)

코드 대조 후보 중 하나인 **충돌 여유(margin)의 시그마 적용 범위**가 원인이다.

- probe `harness/zone_pair_door_relax.py`(양쪽 probe SHA 5bfd95f0·f5d83fdb에서 동일): `SweepGuard.margin`을 프로세스 전체에서 교체하여 **모든** 호출(접근, 미리 닫기, 짐 없는 팔 스윕, 짐 든 팔 스윕, 차체 이동)에서 시그마 배수를 1/1로 쓴다.
- 등록 `harness/zone_pair_geometry.py`의 `PairSweepGuard.margin`: “짐을 든 채 차체가 움직이는 경우(`_loaded_motion`)”에만 `loaded_k`(=1/1)를 쓰고, 접근·미리 닫기·팔 스윕은 등록 값 2/2를 유지한다(코드 주석에 “Narrow scope”로 의도됨).
- 그래서 leg 1의 집기 전 시야 확인에서 팔이 지나갈 공간의 여유가 probe보다 `(시그마 xy + 시그마 yaw × 레버)`만큼 더 크게 요구되고, 시야 방향 후보가 모두 걸러진다(대략 수 cm).

확인 실험(시험용, 등록 소스 무수정): 갈라졌던 6건 + lag-off 1건을 같은 SHA에서, 워커 안에서만 `PairSweepGuard.margin`이 항상 loaded k(1/1)를 쓰도록 덮어써 재실행했다. **7건 모두 commands SHA·recorded legs·leg checks가 비트 단위로 같았고, lag-off sanity도 tX0와 같았다.** 이 덮어쓰기는 진단용이며 등록 후보가 아니다.

- 재생 raw: `/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3afc61b0-claude-20260930` (cases.jsonl SHA-256 `5ff8a751b312748c7d74159854eb71b523a9d90f83889e735441f00923a16875`)
- 원인 확인 raw: `/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3afc61b0-claude-20260930-attr` (cases.jsonl SHA-256 `6f35f83b019f6b54e66213bdbc0644301cdb1d79b389c90a81e93ab3540d6586`)

## 다른 후보 대조 결과

Codex가 나열한 다른 후보(전진 gain 0.9483…, axial 지속시간, yaw gate, p2f)는 이 10건 범위(leg 0~1)에서는 발현하지 않았다: 시그마 범위 덮어쓰기만으로 7건이 모두 비트 단위로 같아졌으므로, 그 범위에서 그 구현들은 probe와 동등하다. 다만 이 시험은 `--chain-stop-leg 1`까지이고 leg 2 이후(측방 이동, 문 통과, 내려놓기)는 비교하지 않았다.

## 남은 결정 (제어기·PR #292는 수정하지 않음)

1. 등록 b-v6h1을 probe b-v6h와 동등하게 하려면, 시그마 배수 1/1을 **집기 전 시야 확인 등 짐 없는 팔 스윕까지** 확장해야 한다(위 덮어쓰기와 같은 범위: 접근·미리 닫기 포함). 이 확장이 원래 의도한 “좁은 범위”와 충돌하므로 정책 결정이 필요하다.
2. 그대로 두면 b-v6h1은 probe b-v6h와 다른 제어기다. 이 경우 probe 결과(tS/tR/tX 코호트)는 b-v6h1의 성능 근거로 옮길 수 없고, 6/10 사례가 leg 1 집기 전에서 멈춘다.
3. 어느 쪽이든 결정 후 고친 코드로 이 재생을 다시 해야 PASS를 말할 수 있다. 재실행 방법: `driver.py`의 소스 SHA만 바꿔 같은 `plan.json`으로 실행(약 9분, 4 worker).

## 보관·검증

- raw는 로컬 보관이며 원격 백업이 아니다. Git에는 이 문서와 JSON만 올렸다. Google Drive는 쓰지 않았다.
- 재생 후 `tests/test_zone_pair_v6h.py` + `tests/test_zone_pair_registered_source.py`: 129 passed(재생 driver가 잠금 안에서 실행, 두 번 모두 통과; 성능 측정 아님).
- probe 원본 raw는 driver가 실행 전 SHA-256(commands.json, cases.jsonl, plan.json)을 재확인했고 변경 없음. 소스 SHA는 실행 내내 `3afc61b0`(변경 없음, 작업 트리 깨끗).

## TensorBoard

- 스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/0930-v6h1-acceptance-replay`: 20개 run(등록 재생 11 + 시험용 덮어쓰기 7 + 집계 2), 내보내기 오류 0. EventAccumulator와 기존 6006 서버의 scalar-tags API로 20개 run 로딩을 확인했다. 브라우저 화면(고정 카드·HParams 열)은 열어 보지 못했다. 영상은 없다(명령 수준 비교).
- 설정: `outputs/tensorboard-view.json`의 `v6h1_acceptance_replay_claude_20260930` 키(자기 키만 추가).
