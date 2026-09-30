# 물리(SIM) 인수 점검 큐 — 2026-10-01 (claude)

Refs #221. **탐색용 점검이다. 확증 결과나 E2E 성공이 아니다.** 시계는 SIM, 모델 호출 0, weld OFF, 렌더 프로필 `floor_light_v1`.
봉인 전 b-v6h1 확증 실행(`outputs/v6h1-confirm-*`)은 읽지도 나열하지도 않았다.

## 결과 한눈에

| 점검 | 판정 | SIM초 | 통과/실패 | 원본(raw) |
|---|---|---:|---|---|
| T13b 사건 복구 | **실행 불가** | 0 / 상한 3,600 | 해당 없음 | 없음 |
| T13a 정체성·개수 | **실행 불가** | 0 / 상한 1,800 | 해당 없음 | 없음 |
| L1 최소 차단 재확인 (S07, X01) | **실행함** | 125.6 | 관문 대용(L0·L1 끝점 오차 ≤100 mm) 2/2, 명령 바이트가 3c4fe30e 인수와 2/2 동일 | `/Users/changmin/projects/ugrp/outputs/phys-caps-1001-l1-recheck` |
| L0/L1 측면 오차 탐사 6건 | **실행함** | 357.2 | 관문 대용 6/6 (실패 0, HOST_ERROR 0) | `/Users/changmin/projects/ugrp/outputs/phys-caps-1001-l1-probes6` |
| P01 3×30 s | **실행 불가** | 0 / 상한 90 | 해당 없음 | 없음 |
| P03 3×120 s | **실행 불가(인계 문서 없음)** | 0 | 해당 없음 | 없음 |

L1 합계 **482.8 SIM초**(62.8×2 + 60.8×2 + 58.9×4; 문서 예상과 같다). 선택 항목인 hR2_10 두 건(119.7초)은 사용자가 준 상한(약 483초)을 넘어 실행하지 않았다.
"관문 대용"은 두 구간 끝점의 `hypot(진행축, 측면) ≤ 100 mm`뿐이다. 접촉·재관측·방출·이후 구간·E2E 완주는 포함하지 않는다.
`outcome_class=FAIL`, `STAGE_BUDGET_EXHAUSTED`는 leg 1에서 멈추는 평가용 종료(`--chain-stop-leg 1`)라서 인수 재생(3c4fe30e)에서도 모든 사례에 똑같이 나온 표기다.

## 실행 불가 4건 — 정확한 이유

기준 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`. 즉석 대체 제어기·GT·weld는 쓰지 않았다.

- **T13b** (`experiments/2026-09-30-t13b-recovery/SIM_CHECKS.md`): 문서가 스스로 "현재 정상 복구 실행은 차단"이라 적는다.
  (1) #320의 specific identity가 cyan을 RGB로 구분하는 단서를 갖지 않는다(`resolved_item_id=null`, `SPECIFIC_IDENTITY_UNGROUNDED`).
  (2) 새 `RecoveryJobs`는 target-aware 하위 backend와 실제 RGB 인식기에 연결돼 있지 않다. main의 `ZoneOwnExecutor.deliver(item_ref, zone_slot_id)`(`harness/zone_own_executor.py:277`)는 target 인수를 받지 않고,
  `submit_target` 구현은 `harness/zone_identity_jobs.py`/`zone_item_recovery.py`의 계약 밖 `harness`·`sim`·`scripts`에 없다(`git grep`으로 확인).
  (3) 실행 번들·표준 `sim_cli` workflow가 없다(`configs/`·`scripts/`에 t13 등록 없음). 문서는 "현재 실행할 수 없는 CLI 옵션을 제시하지 않는다"고 명시한다.
- **T13a** (`experiments/2026-09-30-t13a-identity/SIM_CHECKS.md`): 위 (1)–(3)과 같은 차단 조건. I1은 시각 식별 설계·fixture가 정해지기 전에는 실행 명령을 만들 수 없고, 정상 셀도 `UNSUPPORTED_SPECIFIC_GROUNDING / 미실행`이다. P01/P02/P03/P05/P07의 실제 최종 조합 연결도 안 됐다(현황 문서: P03 #312 검토 중, 기존 v6e 소스 고정 검사로 차단).
- **P01 3×30 s** (`experiments/2026-09-30-e2e-p01-env/README.md` 코디네이터 계획): `scripts/zone_environment_bundle.py`가 `runnable: False`, `DRAFT_UNSEALED`, `execution_bundle_id: null`이다. 문 2개·복도·v3 지도 조합은 P03 allow-list·새 보정이 없어 거부된다. 문서가 "P01/P03/P02 합성·독립 검토 뒤, 새 번들 등록·봉인 뒤"에 실행하라고 한다. 아직 아니다.
- **P03 3×120 s**: main에 구체적 인계 문서가 없다. 근거로 볼 만한 것은 준비도 감사(`experiments/2026-09-30-e2e-readiness/READINESS.md`)의 "3×120=360초 단축 연쇄 상한" 제안뿐이며 명령·번들이 없다. P03 PR #312는 아직 OPEN이다. 지시에 따라 건너뛰고 기록만 남긴다.

## L1 점검 — 무엇을 어떻게 실행했나

- 후보: PR #292 head `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`(b-v6h1, 봉인 전). 읽기 전용 고정 worktree `ugrp-wt/phys-caps-1001-src`(detached, 깨끗함)에서 실행. 실행기 `scripts/run_pair_stage_probes.py`의 `admission=unsealed_stage_probe` 경로다(봉인된 확증 경로가 아니다). 실행 중 소스 변경 없음(`source_changed=false`, 두 그룹 실행 트리 해시 `95aae677…` 동일).
- 명령(레지스트리 등가): `--stage chain --sources teacher --policies b-v6h1 --prior-std e2e --chain-stop-leg 1 --render-profile floor_light_v1 --pf-track --contact-track --workers 2 --omp-threads 1 --env-placements <json> --execute --lock-owner claude`. 배치 JSON은 `l1-inputs/`(SHA-256 `blocker_recheck.json`=c7c2d484…, `lateral_probes_6.json`=b1a8637a…). 시드 911. 감쌈 스크립트 `l1-inputs/run_group.sh`가 공용 잠금을 잡고(소유자 claude, pid=스크립트 셸) 소유 세션(`ugrp_session.py run`)으로 돌렸다. 세션·잠금은 모두 해제·종료했다.
- 병렬 작업자 2개(상한 준수). 여유 디스크 34–44 GiB(≥10 GiB), AC 전원.
- **부하 평균**(1/5/15분): 재확인 시작 110.8/76.4/72.2 → 끝 889.5/606.2/334.7. 탐사 시작 885.0/619.1/344.0 → 끝 226.9/301.5/410.7. 다른 작업이 호스트를 크게 눌렀다. 벽시계는 재확인 779.8초, 탐사 1,215.8초(사례당 379–778초)이며 판단은 SIM 시간으로만 했다. 사례별 부하는 `l1_results.json`의 `loadavg_case`.

### 1) 최소 차단 재확인 (S07, X01)

이전 등록 후보 `3afc61b0`은 S07에서 `PREGRASP_NO_SAFE_VIEW`로 L0 뒤 정지했다(#306 감사). 고정 후보 `4c6b439f`에서는 재발하지 않았다.

| 사례 | 진행축/측면/끝점 L0 (mm) | L1 (mm) | SIM초 | 명령 바이트(SHA-256) |
|---|---|---|---:|---|
| S07 (0.932, 0.037, −4.16°, hR2_05) | 23.3 / −53.0 / 57.9 | 29.8 / −65.7 / 72.1 | 62.8 | `c0c5fcd8…` = 3c4fe30e 인수 기록과 동일 |
| X01 (0.940, 0.050, −3.51°, hR2_07) | 31.5 / −37.6 / 49.1 | 37.4 / −72.9 / 81.9 | 62.8 | `2d2f77a4…` = 3c4fe30e 인수 기록과 동일 |

두 사례 모두 두 구간 끝점 기록됨, 벽 접촉 에피소드 0. 3c4fe30e 인수의 같은 사례와 명령이 비트 단위로 같으므로, #292의 3c4fe30e→4c6b439f 변경("명령 흐름 불변")이 이 두 사례에서는 실제로 명령을 바꾸지 않았다. 이것은 두 사례에 한한 확인이다.

### 2) 측면 오차 탐사 6건 (문서의 배치 목록, PF seed 911)

> 주의: 문서(#306 §6)는 "새 탐색 seed 951"이라 적었으나 실행기의 `--seeds` 기본값이 911이고 이번에는 이 옵션을 주지 않아 **seed 911**로 돌렸다. 문서 지시와 다르므로 결과 해석 때 구분한다(배치 6곳은 문서와 같다). 조정자 결정 항목에 올린다.

| 배치 | (x, y, yaw°, prior) | L0 측면 관측/예측 (mm) | L1 측면 관측/예측 (mm) | 끝점 L0/L1 (mm) | SIM초 |
|---|---|---:|---:|---:|---:|
| LE_A_04 | .951, −.025, −4.5, hR2_04 | −40.9 / −66.5 | −45.9 / −80.4 | 72.3 / 70.3 | 60.8 |
| LE_A_07 | .951, −.025, −4.5, hR2_07 | −34.1 / −55.5 | −37.7 / −64.9 | 68.6 / 65.1 | 60.8 |
| LE_B_04 | 1.069, .109, +4.5, hR2_04 | +6.4 / +27.5 | −12.1 / +14.7 | 39.1 / 34.7 | 58.9 |
| LE_B_07 | 1.069, .109, +4.5, hR2_07 | +12.7 / +38.5 | +4.7 / +30.2 | 40.4 / 32.1 | 58.9 |
| LE_C_04 | 1.069, .109, −4.5, hR2_04 | +12.5 / −9.9 | −19.1 / −43.8 | 40.7 / 38.2 | 58.9 |
| LE_C_07 | 1.069, .109, −4.5, hR2_07 | +15.3 / +1.1 | +0.7 / −28.3 | 41.3 / 32.3 | 58.9 |

예측은 #306의 `target_ENV_30_prior` 점 예측이다(같은 계수·입력 공식). 관측−예측(L1): +34.5, +27.2, −26.8, −25.4, +24.7, +29.0 mm. 이 모형의 보류 잔차 표준편차(OOF SD)는 약 19.0 mm이므로 여섯 건 모두 1.3–1.8 SD로, 잔차가 한쪽으로 몰려 있다: 가장자리(yaw ±4.5°)에서 **예측이 실제보다 더 크게 벗어난다**(A는 관측이 덜 음수, B는 관측이 덜 양수, C는 관측이 더 양수). 학습 yaw 범위(−4.16…+4.24°) 밖 외삽 영향일 수 있으나 표본 6건으로 원인을 확정할 수 없다. 이 여섯 건은 모형 보정 자료로만 쓰고 확증 표본에 섞지 않는다. 모형이 바뀌면 사전 등록에 반영한 뒤 봉인한다(#306 지침).
진행축 끝점 오차는 탐사 6건 모두 −32…−60 mm(목표에 못 미침)로 부호가 일정했다.
끝점 오차 최대는 72.3 mm(LE_A_04 L0)로 100 mm 관문 대용에 여유가 있었다. 벽 접촉 에피소드는 전부 0이었다.

## TensorBoard

새 스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/1001-phys-caps-l1-probes`(8 run: `B-S07`, `B-X01`, `P-LE_*`). 기존 공용 서버(6006, 다른 작업 소유)의 logdir가 자동으로 읽어 왔다. 검증: 이벤트를 EventAccumulator로 다시 읽은 값과 실행 중 서버 HTTP API 값 122개가 원본(`l1_results.json`) 값과 일치(불일치 0). 대시보드는 열어 확인했다(run 8개 표시; 공용 logdir의 run이 500개를 넘어 새 run은 기본 미선택이라 왼쪽 목록에서 확인해야 한다).
[대시보드](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpass%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fl1_end_error_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fl1_lateral_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fl1_lateral_pred_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fsim_s%22%7D%5D&smoothing=0&runFilter=%5E1001-phys-caps-l1-probes%2F#timeseries). 설정은 `outputs/tensorboard-view.json`에 내 키 `phys_caps_l1_20261001` 하나만 추가했다(고정 태그와 HParams 열 포함).
첫 변환 시도는 `commands`가 dict라서 8건 모두 실패했다(스냅샷은 실패 manifest만 남김). 지우지 않고 `outputs/phys-caps-1001-failed-tb-attempt-1/`로 옮겨 보존했고, 수정 후 새 스냅샷을 만들었다. 새 영상은 없다(SIM 명령 단위 점검이라 영상 미생성). 실행 불가 4건은 결과가 없어 스냅샷이 없다.

## 원본 위치와 해시

원본은 로컬 보관이며 원격 백업이 아니다. 각 그룹 폴더 전체 크기: 재확인 54.1 MB, 탐사 154.4 MB.

| 그룹 | manifest.json | cases.jsonl | artifacts.sha256.json | plan.json |
|---|---|---|---|---|
| recheck | e233119c3219… | fac7ea9a0aa5… | 77c2620154b0… | 44019ab05435… |
| probes6 | afcac1122ea3… | 8b04e2fbdbcb… | 3ebdb9f71ba7… | 85a183e13cd4… |

전체 해시는 `l1_results.json`(그룹별 `*_sha256`)과 각 폴더의 `artifacts.sha256.json`(모든 파일의 바이트·SHA-256)에 있다. 사례별 `commands.json`·`result.json` 해시도 `l1_results.json`에 있다.

## 파일

- `summarize_l1.py`, `build_tb_l1.py`: 원본을 읽기만 하는 요약·스냅샷 생성(사용한 Python: `Project-Runtimes/ugrp/.venv-sim-worker-mac`).
- `l1_results.json`, `tensorboard_verification.json`, `l1-inputs/`(배치 JSON, `run_group.sh`).
- 검증: `tests/test_offline_audit_export.py` 19 통과, 스크립트 컴파일·`bash -n` 통과. 소스·설정·제어기는 바꾸지 않았다.

## 남은 일·조정자 결정

1. 탐사 6건은 문서의 seed 951이 아니라 seed 911로 돌았다. 951로 6건(약 357 SIM초)을 다시 돌릴지 결정 필요.
2. 예측이 가장자리에서 크게 벗어나는 경향은 6건짜리 탐색 결과다. 측면 모형을 고칠지, hR2_10 두 건(119.7 SIM초)을 더할지는 결정 필요.
3. T13a/T13b/P01/P03은 선행 연결(RGB 특정 물체 식별 단서, target-aware backend, 최종 번들 봉인)이 끝난 뒤 새 인계로 다시 요청해야 한다.

## 참고 자료

- [PR #306 측면 오차 분석·제안 탐사](../2026-09-30-l1-lateral-error/README.md), [PR #292 b-v6h1 등록 후보](https://github.com/kcm0127-dotcom/ugrp/pull/292)
- 3c4fe30e 인수 재생 원본(로컬 `outputs/v6h1-acceptance-3c4fe30e-claude-20260930`): S07/X01 명령 SHA와 비교하려고 `acceptance_receipts.json`만 읽었다.
- T13a/T13b/P01 인계 문서: [T13b](../2026-09-30-t13b-recovery/SIM_CHECKS.md), [T13a](../2026-09-30-t13a-identity/SIM_CHECKS.md), [P01](../2026-09-30-e2e-p01-env/README.md), [준비도 감사](../2026-09-30-e2e-readiness/READINESS.md)
- 새 외부 문헌·라이브러리는 쓰지 않았다(기존 실행기·변환기 재사용).
