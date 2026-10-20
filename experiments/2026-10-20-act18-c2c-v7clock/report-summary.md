# 원 보고서 요약 — ACT18 C2c v7 clock (2026-10-20)

원 보고서 `outputs/reports/2026-10-20-act18-c2c-v7clock.md`(sha256 `551b9160e7f00f82862f1431287ea54d687997d689e4246f211f27e231b27217`)의 요약이다. `outputs/`는 git 제외 경로라 원문은 repo에 없고, 이 요약과 [log-summary.md](log-summary.md)가 공개 기록이다.

## 상태

engineering-only / sim / HO4 diagnostic / gate 비대상 / pooling 금지. R8 step-100000 평가 전용이고 계약 파일·adapter·가중치·데이터·라벨 변경 0, R3 학습 0이다. 실행: DeepSeek dsh 워커. 승인: 창민 2026-10-19(2.9 VM-h, 새 run root, 새 branch, R3 재학습 no-go).

## 결론 (원문)

1. **C2c = PASS (사전 등록 기준 그대로).** G(C2c-HO4) **11/12**, G(C2c-TRAIN4) **10/12**, Pre(C2c 합계 24) **0**, G(B0-HO4) **0/12**. 기준(≥4 · ≥4 · ≤2 · ≤1)을 모두 충족한다.
2. **v7 시계만으로 done 경로가 열렸다.** B0-HO4는 done **0/12**·post-lift max pe 1.0–1.3 s였고, C2c는 done **21/24**·post-lift max pe 11.0–14.5 s였다. 21건 중 16건은 issued done 시점 pe 11.1–11.4 s, 5건은 직전 틱의 ≥3 PWM 변화로 pe가 0으로 리셋된 직후 발화했다(보정 없이 그대로 기록).
3. **§8 이정표 T(C2c-HO4) ≥ 1 충족.** T(C2c-HO4) **6/12**, T(C2c-TRAIN4) **3/12**(보고용, 판정 미사용). 88668은 release 성공이 3회 중 0회로 남은 병목이다.
4. 9 runs 전부 `DONE`, 체크포인트 sha 불변, 프로세스 0·GPU 0 확인 후 gcp2 **TERMINATED**.

## 실행 (원문)

- **branch/SHA:** `dsh/act18-c2c-v7clock`, 실행 source SHA `257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8`(base `282baf4d8` = C2 summary), 결과 요약 commit `ac274afeb`. prereg `e0b9b1ce3`, code+tests `efa87a762`, path/venv 수정 `f3d64c5b9`·`7a3dbe2de`, HO4 그룹 fallback `093e2c23c`·`257dcaccc`.
- **prereg:** `experiments/2026-10-17-act18/C2C_V7CLOCK_PREREG.json` sha256 `572f82593fb2de916a46af91f883a6a2b42da8f6cbd96d731d342c15503cc4fd` (GPU 추론 전 커밋, 모든 summary/act18-evaluator.json에 기록).
- **checkpoint:** R8 step-100000, `model.safetensors` sha256 `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a` — 실행 전·후·9 runs 전부 동일.
- **run root:** `/home/ugrp/ugrp-sim/runs/act18/c2c-v7clock-20261019T2315Z/`(새 root). 9 runs = `{C2c,B0}-ho4-rep{1,2,3}` + `C2c-train4-rep{1,2,3}`. B0-TRAIN4는 스펙대로 새로 돌리지 않았다(기존 원본·repro 2회는 문맥이며 합산 금지).
- **설정:** te1, `--full-evaluation` 90 SIM s, `--record-done-prob`, 2 robots/group, HO4는 diag stage, TRAIN4는 train stage.
- **v7 구현:** `scripts/act18_evaluate.py`의 `--issued-clock-deadband {0,2}`(기본 0). deadband 2는 직전 관측 issued PWM 대비 servo |Δ|≥3에서만 리셋(±1·±2 무시). 평가 프로세스에서 `contract.IssuedClock`만 교체하고, 관측은 physics owner 별도 프로세스가 만들므로 `Client.read_actor`에서 허용 관측의 `pwm_elapsed_s`만 같은 시계로 재계산한다. `skill_elapsed_s`·다른 필드·계약 파일 sha는 불변.
- **HO4 진입:** `--stage diag --diag-prereg`가 prereg의 HO4 seed만 허용하고 TRAIN4·VAL8·FINAL40과 겹치면 fail-closed. summary에 `stage=diag`, `gate_eligible=false`, prereg path/sha 기록.
- **단위 테스트:** `tests/test_act18_c2c_clock.py` 6 passed, 기존 `tests/test_act18_tsreplay.py` 18 passed와 함께 24 passed.
- **그룹 예외:** 등록 HO4 g000 {88668, 88669}가 owner 사전검사 `warp_act_backend.py:402` model scalar/topology 불일치로 실패했다(88669가 88668보다 geom 2개 적음). 설계 E2 fallback대로 g000 {88668}, g001 {88669}, g002 {88670, 88671}로 실행했다. 결과 기반 변경이 아니다.

## 9 run 표 (world-run 단위, N=4/run)

| run | arm | queue | rep | stage | done(claim) | Pre | G | lift | release | task | cap_end | wall s |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C2c-ho4-rep1 | C2c | HO4 | 1 | diag | 4 | 0 | 4 | 4 | 2 | 2 | 2 | 915.3 |
| B0-ho4-rep1 | B0 | HO4 | 1 | diag | 0 | 0 | 0 | 3 | 0 | 0 | 4 | 1079.9 |
| C2c-train4-rep1 | C2c | TRAIN4 | 1 | train | 3 | 0 | 3 | 4 | 1 | 1 | 3 | 843.6 |
| C2c-ho4-rep2 | C2c | HO4 | 2 | diag | 3 | 0 | 3 | 4 | 2 | 2 | 1 | 836.4 |
| B0-ho4-rep2 | B0 | HO4 | 2 | diag | 0 | 0 | 0 | 2 | 0 | 0 | 4 | 1056.8 |
| C2c-train4-rep2 | C2c | TRAIN4 | 2 | train | 4 | 0 | 4 | 4 | 2 | 2 | 2 | 834.7 |
| C2c-ho4-rep3 | C2c | HO4 | 3 | diag | 4 | 0 | 4 | 4 | 2 | 2 | 2 | 889.1 |
| B0-ho4-rep3 | B0 | HO4 | 3 | diag | 0 | 0 | 0 | 2 | 0 | 0 | 4 | 1053.2 |
| C2c-train4-rep3 | C2c | TRAIN4 | 3 | train | 3 | 0 | 3 | 3 | 0 | 0 | 4 | 814.5 |
| B0-train4 | B0 | TRAIN4 | — | — | 미실행 | — | — | — | — | — | — | — |

- done = issued grasp done(claim) world 수. Pre = done이 있었지만 done 이전 3 s stable lift가 없던 world 수. G = done ∧ done 이전 3 s stable lift.
- B0-TRAIN4는 기존 finish-r3 원본/repro 2회가 문맥이며 **합산하지 않는다**.

## arm×queue 합계

| arm-queue | N | done | Pre | G | lift | release | task | cap_end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **C2c-HO4** | 12 | 11 | 0 | **11** | 12 | 6 | 6 | 5 |
| **C2c-TRAIN4** | 12 | 10 | 0 | **10** | 11 | 3 | 3 | 9 |
| **B0-HO4** | 12 | 0 | 0 | **0** | 7 | 0 | 0 | 12 |
| B0-TRAIN4 | 0 | — | — | — | — | — | — | — |

- seed별 G: C2c-HO4 88668 3/3, 88669 3/3, 88670 2/3, 88671 3/3. C2c-TRAIN4 88600 3/3, 88601 2/3, 88602 2/3, 88603 3/3. B0-HO4 lift 7/12이지만 done 0/12.
- C2c-HO4 done 11/12(88670 rep2 미발화), C2c-TRAIN4 done 10/12(88601 rep1, 88602 1회 미발화). Pre 0/24.

## 판정 (사전 등록)

| 기준 | 요구 | 결과 | 판정 |
|---|---|---|---|
| G(C2c-HO4) | ≥4/12 | **11/12** | 충족 |
| G(C2c-TRAIN4) | ≥4/12 | **10/12** | 충족 |
| Pre(C2c 합계 24) | ≤2 | **0/24** | 충족 |
| G(B0-HO4) | ≤1/12 | **0/12** | 충족 |
| **종합** | PASS 조건 전부 | | **PASS** |
| T(C2c-HO4) (§8 이정표, 보고용) | ≥1 | **6/12** | 충족 |

- FAIL 조건(G≤1 both 또는 Pre≥5) 아님. 결과를 본 뒤 임계·seed·arm·지표를 바꾸지 않았다.
- Fisher 참고치(4/12 대 0/12, p=.047)보다 큰 분리(11/12 대 0/12)지만, HO4는 승격 gate가 아니므로 gate-eligible 주장을 하지 않는다.

## clock receipt

| arm | mode | reset_threshold | resets/world-group | max pe (s) | post-lift max pe (s) |
|---|---|---:|---:|---:|---:|
| B0 | v6 | 1 | 기록 없음(v6 원형) | — | **1.0–1.3** |
| C2c | deadband | 3 | 158–453 | **11.2–14.5** | **11.0–14.5** |

- C2c issued done 시점 pe: 16/21이 **11.1–11.4 s**, 5/21은 직전 틱의 ≥3 PWM 변화로 pe가 0으로 리셋된 직후 발화(그대로 기록, 보정 없음). raw chunk done prob가 처음 ≥.65가 된 pe는 10.6–10.8 s였다(보고용; TE 실행 done과 다를 수 있음).
- B0는 전 run에서 done 0, post-lift pe 1.0–1.3 s로 C2b/E0의 H1(student pe가 4.6 s에 못 미침)과 일치한다.

## 검증·자원 (원문)

- 9 runs `status=DONE`, group exit 전부 0, HOST_ERROR 0. 체크포인트 sha 9회 실행 전후 동일.
- 원본 불변: `finish-r3/R8-train/summary.json` `f2529959…df2896f`, `R100-train` `aca288d1…b77407d`, `finish-r3/summary.json` `54feb0b9…742a6a` — 실행 전후 동일. 원본 쓰기 0.
- 회수: `outputs/runs/act18-c2c-v7clock-20261019T2315Z/` **335 MB**, run별 선택 파일 sha256 검증 **9/9 runs OK**(파일 수 1027/1214/1090/969/1214/992/1021/1214/1192). 원격 전체 41,354 파일/734 MB의 sha256 목록 `remote-full-sha256.txt` 보존(JPEG 원본은 VM 디스크에 유지, 미회수).
- VM: gcp2 `ugrp-act-l4-gcp2`만 사용, **2026-10-20T01:26:26Z TERMINATED**, gcp-sim-gcp2도 TERMINATED. 실행 후 프로세스 0, GPU 0%. VM 가동 22:48:21Z→01:26:26Z ≈ 2 h 38 min(9 runs wall 합 8,323.5 s = 138.7 min). 2.9 VM-h 추정 안.
- 실행 창: 23:03:30Z 시작(오프피크 안), 마지막 run 01:22Z 종료로 창 끝(01:00Z)을 약 22분 초과했다(리스크로 기록).

## 실패·중단 root (판정 미사용)

| root | 중단 이유 | 모델 추론 |
|---|---|---|
| `c2c-v7clock-20261019T2300Z` | prereg 상대경로 → child cwd(Q)에서 미발견, HOST_ERROR | 0 |
| `c2c-v7clock-20261019T2258Z` | physics venv symlink를 resolve해 owner import 실패 | 0 |
| `c2c-v7clock-20261019T2301Z` | 등록 HO4 g000 {88668,88669} model scalar 불일치(88669 group만 41.6 s 완주) | 일부(88669) |
| `c2c-v7clock-20261019T2307Z` | 4-single 그룹 시험, 중단 | ~10 SIM s |

위 root들은 새 run root 규칙에 따라 판정·합산에 쓰지 않았다. `T2301Z`의 88669 결과는 실행 구조 사고의 산물이며 결과 표에 포함하지 않는다.

## 리스크·한계 (원문)

- **HO4는 진단 holdout**이며 VAL8/FINAL40 gate가 아니다. gate-eligible 주장·승격 근거로 쓰면 안 된다. B0-TRAIN4는 새로 재지 않았다(스펙대로 기존 baseline 문맥, pooling 금지).
- **그룹 fallback:** HO4 g000이 model scalar 불일치로 2-world 그룹을 못 만들어 88668/88669를 단독 실행했다. 설계 E2의 사전 fallback이지만 등록 run layout(group-000/001)과 다르므로 결과 표에 명시했다.
- **done pe 5/21이 0:** 전이 tick에서 직전 command의 ≥3 PWM 변화가 시계를 리셋한 뒤 done이 발화했다. 시계가 유일 원인이라는 단정은 피해야 하며, state/이미지 기반 done도 함께 작동할 수 있다. B0 0/12와의 대비는 유지된다.
- **release가 다음 병목:** C2c-HO4 release 6/12, TRAIN4 3/12. 88668은 G 3/3이지만 release done 1/3·release 성공 0/3이다. 88669·88670·88671은 release 성공 2/3.
- **L3 접촉 분기:** 88670(G 2/3, rep2 done 미발화; lift 3/3), 88601(TRAIN4, done 2/3), 88602(TRAIN4, lift 2/3·rep3 무 lift), 88603(TRAIN4, release done 0/3). N=3으로는 분기율을 확정하지 않는다.
- **B0-HO4 lift 7/12 vs C2c 12/12:** v7 시계는 action을 바꾸지 않지만 done/release 전이가 lift 이후 행동에 영향을 줄 수 있다. lift 차이는 접촉 분기와 겹쳐 해석에 주의한다.
- **자원:** gcp2 예산 정지(2,000 KRW)는 발동하지 않았다. 오프피크 창 22분 초과. HO4 3 process/run 구조로 wall이 run당 14–18분이었다.
- **검증 범위:** summary·rejection table·actor-inputs·owner truth·done-prob를 분석했고, policy 행동 영상은 회수·검토하지 않았다(원본 JPEG는 VM 디스크 보존). 실물 sim2real 주장 없음.

## 증거 SHA256 (원문, 일부 축약)

- **branch/HEAD:** `dsh/act18-c2c-v7clock`, 실행 source `257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8`(clean). 결과 요약 commit `ac274afeb`(`experiments/2026-10-17-act18/C2C_V7CLOCK_SUMMARY.json` sha256 `14dd1c46…10f67`). prereg commit `e0b9b1ce3`, sha `572f8259…03cc4fd`. code commit `efa87a762`, driver 수정 `f3d64c5b9`·`7a3dbe2de`·`093e2c23c`·`257dcaccc`.
- **run root:** `runs.json`/`analysis.json` 해시와 파일명 표기 주의는 [log-summary.md](log-summary.md)에 적었다.
- **checkpoint:** `e1ec6592…8d5a`(위). **native gate** `15aa4ea2…a82d`(평가 summary 기록). **protocol** `$B/src/ab89b3c54/experiments/2026-10-17-act18/protocol.json`.
- **원본:** finish-r3 `f2529959…df2896f` / `aca288d1…b77407d` / `54feb0b9…742a6a` 불변.
- **회수 검증:** `remote-sha-<run>.txt` 9개, `remote-full-sha256.txt`(41,354 lines), 선택 파일 9/9 runs sha OK. 압축 원본은 VM 디스크 `/home/ugrp/ugrp-sim/runs/act18/c2c-v7clock-20261019T2315Z/`(734 MB, 41,354 files)에 보존.

## 재현 (원문)

```bash
# code: 257dcaccc checkout, cwd=/home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c
/home/ugrp/ugrp-rl1b-act-env/bin/python -u scripts/act18_c2c_stage.py --enabled \
  --prereg experiments/2026-10-17-act18/C2C_V7CLOCK_PREREG.json \
  --checkpoint /home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000 \
  --run-root /home/ugrp/ugrp-sim/runs/act18/c2c-v7clock-<UTC TS> \
  --native-gate /home/ugrp/ugrp-sim/runs/act17-v7/gate-r1/gate-recount.json \
  --physics-python /home/ugrp/ugrp-sim/runs/simalt3/warp-env/bin/python \
  --qualified-source /home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c \
  --teacher-source /home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e \
  --qualification /home/ugrp/ugrp-sim/runs/warp3/teacher-gate-qualification-r1.json \
  --references /home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1/per-world-references.json \
  --record-references /home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1 \
  --protocol /home/ugrp/ugrp-sim/src/ab89b3c54/experiments/2026-10-17-act18/protocol.json
# analysis (driver가 자동 실행): scripts/act18_c2c_analyze.py --enabled --run-root <root> --prereg <prereg>
```
