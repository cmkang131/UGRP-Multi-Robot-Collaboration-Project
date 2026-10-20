# ACT18 C2c v7 clock — HO4 제자리 집기·3초 들기·내려놓기 진단 (2026-10-20)

> **engineering-only / sim / HO4 diagnostic / not a promotion gate / pooling 금지**
> R8 step-100000 평가 전용이며 재학습은 0이다. 이동·공동 운반 과제가 아니고, 실물(sim2real) 결과도 아니다. 아래 수치를 승격·일반화 근거로 쓰지 않는다.

## 요약

HO4 holdout 4 seed × 3회 = **12 world-run**에서 v7 시계(C2c)는 **과제 성공 6/12**, **3초 안정 들기 12/12**, **내려놓기 6/12**, **집기 완료 11/12**였다. 같은 12회의 v6 기준선(B0)은 과제 성공 0/12, 집기 완료 0/12였다.

**6/12는 관문 미통과 진단 결과다.** HO4는 `gate_eligible=false`인 진단 holdout이라 이 실행으로 통과한 승격 관문은 없고, VAL8·FINAL40·TRAIN4 관문 결과도 아니다. 6/12는 이동·공동 운반 성공이 아니라, 로봇이 물건을 들어 같은 자리에 안정적으로 내려놓은 횟수다.

## 과제 정의

ACT18 근거리 ACT 과제(grasp → stable lift → release)다.

1. **집기**: 큐브를 집는다(issued grasp).
2. **3초 들기**: clearance ≥ 12 mm, tilt ≤ 10°, 손가락 힘 ≥ 0.5 N을 **3초 연속** 유지한다.
3. **같은 자리에 내려놓기**: 집은 자리(pickup site)에서 clearance −5..+6 mm, tilt ≤ 10°, 손가락 힘 < 0.1 N, linear speed ≤ 0.02 m/s를 **3초 연속** 유지한다.

내려놓기 판정이 집은 자리 기준이므로 **운반 구간이 없고 운반 거리는 0**이다. 두 로봇이 함께 물건을 나르는 공동 운반 과제가 아니다. 성공 판정은 [`harness/grasp_act_rollout.py`](../../harness/grasp_act_rollout.py)의 `LiftScore`·`SoloScore`(평가 전용, 정책 입력·행동 보정에 쓰지 않음)로 계산한다.

## 실행

| 항목 | 값 |
|---|---|
| 브랜치 | `dsh/act18-c2c-v7clock` (공개 repo에 push됨) |
| 실행 source | `257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8` |
| 결과 요약 commit | `ac274afeb26a5d738a146eea92fea88eae3fcb87` |
| 체크포인트 | R8 `/home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000`, sha256 `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`, 실행 전후 불변 |
| 평가 조건 | HO4 seeds 88668(cyan)·88669(red)·88670(green)·88671(yellow), rep1–3, 90 SIM s |
| arm | C2c = v7 own-issued clock(deadband 2, reset threshold 3), B0 = v6 clock |
| 변경 범위 | 평가 프로세스의 issued PWM clock 정의만. 계약 파일·adapter·가중치·데이터·라벨 변경 0, 학습 0 |
| 실행 시각 | 2026-10-19T23:03:30Z–2026-10-20T01:22Z, 9 runs 전부 `DONE`, HOST_ERROR 0 |

HO4는 TRAIN4·VAL8·FINAL40과 겹치지 않는 holdout이다. 등록 그룹 `{88668, 88669}`가 owner 사전검사에서 토폴로지 불일치로 실패해, 설계 E2의 사전 fallback대로 88668·88669를 단독 실행하고 88670·88671은 검증된 쌍으로 실행했다. 결과를 본 뒤 바꾼 것이 아니다. 자세한 내용은 [report-summary.md](report-summary.md)에 있다.

## 결과 (HO4, N=12)

| 지표 | C2c (v7 clock) | B0 (v6 clock) | 정의 |
|---|---:|---:|---|
| 집기 완료 (done) | **11/12** | 0/12 | issued grasp done 발화 |
| 3초 안정 들기 (lift) | **12/12** | 7/12 | 3 s stable lift |
| 내려놓기 (release) | **6/12** | 0/12 | pickup site에서 3 s stable setdown |
| **과제 성공 (task)** | **6/12** | 0/12 | lift + release, drop 없음 |
| Pre (lift 전 done) | 0/12 | 0/12 | 3 s stable lift 없이 done |
| G (done ∧ lift) | 11/12 | 0/12 | — |
| cap_end (90 s 상한 종료) | 5/12 | 12/12 | 실패(valid)로 집계 |

- seed별 내려놓기 성공(release): 88668 **0/3**, 88669 **2/3**, 88670 **2/3**, 88671 **2/3** = 6/12. 88668은 lift 3/3·G 3/3이지만 내려놓기 성공 0/3으로 남은 병목이다.
- 9-run 상세 표·clock receipt·자원·실패 root는 [report-summary.md](report-summary.md), run별 상태·wall·로그/분석 해시는 [log-summary.md](log-summary.md)에 정리했다.

## 해석 (진단)

- v7 시계는 done 경로를 열었다. B0는 12회 모두 done 0·post-lift max pe 1.0–1.3 s였고, C2c는 done 11/12·post-lift max pe 11.0–14.5 s였다. issued done 시점 pe는 21건 중 16건이 11.1–11.4 s, 5건은 직전 tick의 ≥3 PWM 변화로 pe가 0으로 리셋된 직후 발화했다(보정 없이 기록).
- 남은 병목은 내려놓기다. C2c-HO4 release 6/12, C2c-TRAIN4 release 3/12다. 이 문서의 6/12는 **내려놓기까지 안정적으로 끝난 횟수**이지 이동·운반을 성공한 횟수가 아니다.
- 그룹 fallback·done pe 0 사례·L3 접촉 분기 때문에 "v7 시계가 유일 원인"이라거나 "일반화된다"고 주장하지 않는다.

## 범위와 한계

- **gate 아님:** HO4는 진단 holdout이며 `gate_eligible=false`다. VAL8·FINAL40·TRAIN4 관문, 승격, Release 판정에 쓰지 않는다.
- **합산 금지:** VAL8·FINAL40·finish-r3·20261019c·E0/E1·act17/act16w 결과와 pooling하지 않는다. B0-TRAIN4는 이번에 새로 실행하지 않았다(기존 원본은 문맥일 뿐 합산 금지).
- **실물 아님:** sim 결과이며 sim2real 주장이 없다. 정책 행동 영상은 회수·검토하지 않았다(원본 JPEG는 VM 디스크 보존).
- **N=3:** rep 3회로 분기율을 확정하지 않는다. cap_end는 실패로 집계했다.
- **원 보고서:** `outputs/`는 git 제외 경로라 원 보고서는 repo에 커밋되지 않았다. 서버 사본 `outputs/reports/2026-10-20-act18-c2c-v7clock.md`(sha256 `551b9160e7f00f82862f1431287ea54d687997d689e4246f211f27e231b27217`)를 요약해 이 디렉터리에 보존했다.

## 증거

- 공개 브랜치: <https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/tree/dsh/act18-c2c-v7clock>
- 결과 요약 JSON: [`experiments/2026-10-17-act18/C2C_V7CLOCK_SUMMARY.json`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ac274afeb26a5d738a146eea92fea88eae3fcb87/experiments/2026-10-17-act18/C2C_V7CLOCK_SUMMARY.json), sha256 `14dd1c46333d69513b96474979cd05f399119a8937128a9712c06ec313e10f67`
- 사전등록: [`C2C_V7CLOCK_PREREG.json`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/e0b9b1ce3/experiments/2026-10-17-act18/C2C_V7CLOCK_PREREG.json), sha256 `572f82593fb2de916a46af91f883a6a2b42da8f6cbd96d731d342c15503cc4fd`
- 주요 commit: prereg `e0b9b1ce3`, code+tests `efa87a762`, driver 수정 `f3d64c5b9`·`7a3dbe2de`·`093e2c23c`·`257dcaccc`, 결과 요약 `ac274afeb`
- 실행 root(VM, git 제외): `/home/ugrp/ugrp-sim/runs/act18/c2c-v7clock-20261019T2315Z/` (41,354 files/734 MB). 로컬 회수본 `outputs/runs/act18-c2c-v7clock-20261019T2315Z/` 335 MB, 선택 파일 sha256 9/9 runs OK.
- 원 보고서 요약: [report-summary.md](report-summary.md) · 실행/로그 요약: [log-summary.md](log-summary.md)
