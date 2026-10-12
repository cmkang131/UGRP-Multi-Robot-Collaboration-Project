# E2E 14차 통합 브랜치 준비 (DEV, 실행 아님)
- draft PR #446 (base `codex/e2e-integration`).

- 브랜치 `claude/e2e14-combo` = `codex/e2e-integration`(9d6eb567) + PR #443(`codex/e2e-bboundary`, ee3d656b) + PR #444(`claude/e2e-vo`, 02d6af82). 시뮬레이션·VM 사용 0회.
- 새 번들 `e2e-combo14-v202` / workflow `7.95.0`. main과 열린 PR 브랜치 전체 최댓값 v201(`e2e-rgb-vo-v201`, 7.94.0) 다음 번호다. `RUNNABLE_ID`(rgb-standard-dispatch-v63)는 바꾸지 않았다.
- 비교군: 12차 A 그대로(`e2e-stall-budget-v199`). 단 실행 소스 SHA가 새로 바뀌므로 12차 결과를 승계하지 않는다.

## 세 토글 (모두 기본 off, 서로 독립)
| 토글 | 실행기 CLI | 출처 |
|---|---|---|
| B 후보 확인 관측점 `candidate_views_v1` | `--boundary-views candidate_views_v1` (`--exploration-progress frontier_progress_v1` 필요) | PR #443, `harness/e2e_boundary_views.py` |
| B 흰 표식 대비 판정 `contrast_v1` | `--b-marker-detect contrast_v1` | PR #443, `harness/e2e_rgb_gate.py` |
| 자기 RGB 바닥 VO `rgb_vo_v1` | `--stall-odometry rgb_vo_v1` | PR #444, `harness/e2e_rgb_vo.py` |

- #443은 harness(make_goal/Robot)까지만 있었고 실행기 CLI·번들에는 연결되지 않았다. 이번에 연결했다. 켠 경우에만 `e2e_options`에 키를 넣으므로 v185~v201 번들은 수정 전과 바이트 동일하다(off, 12차 A, 12차 B, VO 단독 4종 비교).
- 단독 켬: views 또는 marker → v202, VO → v201(#444 그대로), 셋 다 → v202.

## 12차 A 구성과의 차이 (명시적 이탈)
- 12차 A = v199 예산 + RPP + innovation 위치 보정 + Gemma(OpenRouter) + `rgb_pulse_gate_v1` + `backup_replan_v1` + `amcl_alpha_v1`.
- #444의 VO는 별도 `odometry_source`가 아니라 같은 `stall_odometry` 자리의 값이다. 펄스 게이트를 대체하며, #444 계약상 recovery·noise와 같이 켜면 `RGB_VO_REQUIRES_RECOVERY_AND_NOISE_OFF`로 막힌다. 이 계약은 풀지 않았다.
- 그래서 14차 A(v202) = v199 + RPP + innovation + Gemma + VO(게이트 대체, recovery/noise off) + views + marker다. 14차 B = 12차 A다.
- 따라서 A−B는 다섯 가지가 함께 다르다(게이트→VO, recovery off, noise off, views, marker). 짝 비교는 토글별 원인 분리가 아니다.

## 7시간 상한
- 실행기 `bundle()`가 `0 < wall_cap_s <= 12600`(3.5시간)을 강제해 `--wall-cap-s 25200`이 거부됐다(13차 작업이 발견한 숨은 상한). 한계만 25200초로 올렸다(`WALL_CAP_MAX_S`). 기본값 12600은 그대로 둬서 기존 번들 바이트가 바뀌지 않는다.
- 크기 점검: 12차는 약 330 SIM초에서 wall 약 4,900초로 끊겼다(약 14.8 wall/SIM). `case_cap_s=1800` × 12~15 ≈ 6~7.5시간이다. 3.5시간으로는 사례 상한까지 갈 수 없다.
- 확인 안 됨: Azure 쪽 `/usr/local/lib/ugrp-storage`의 `remote_run_finish.py`·`azure_shutdown.py`는 저장소 밖에 있어 자체 상한 유무를 여기서 확인하지 못했다. 8시간 VM 상한 안에는 들어간다.
- `sim/workflow_manager.py`의 `--timeout`은 유한 양수만 요구한다. A/B 예시 명령은 `workflow plan` 검증을 통과했다(실행 아님).

## 저장 프레임 고정 재생 스모크 (실행 아님)
- 시뮬레이션·물리·렌더 없음. 저장 자기 RGB 394장(e2e11에서 고른 창: e2e10-a-s61001/61002-r2, r1·r2)과 기록된 실제 발행 명령을 시간순으로 실제 `Robot`에 넣었다(실행기 `run()`과 같은 인자 매핑, 개루프). 스크립트 `scripts/smoke_e2e14_combo.py`, 결과 `smoke-replay.json`, Mac wall 288초.
- 구성 4개: 12차 A(v199), VO 단독(v201), #443 두 토글(v202), 셋 다(v202). 오류 0/4구성 × 4사례.
- 셋 다 켬: views 기록·경계 진단 394/394, marker `contrast_v1` 394/394, VO 기록 394/394(측정 340, VO 대체 163).
- #443이 VO를 건드리지 않음: VO 행(상태·융합·적용 증분)과 자기 위치가 VO 단독과 394/394 프레임 일치(4/4사례).
- #443 쪽: 경계 진단 해시가 #443 단독과 394/394 일치. views 단계·관측점 기록은 280/394 일치했다. 차이 114프레임(s61001 r2 42, s61002 r1 72)은 VO가 자기 위치를 바꿔 관측점 선택이 달라진 것으로 본다(입력은 같고 위치만 다름). 이 차이의 좋고 나쁨은 판정하지 않았다.
- 한계: 개루프라 로봇 자신의 명령이 되먹임되지 않는다. 지도 작성 단계·SEARCH 카메라 창만 다룬다. 성공·정확도 근거가 아니다. 코드 파일은 커밋 e8b63c5e와 동일하다(실행 중 커밋, `git diff` 없음).

## 시험
- `tests/test_e2e14_combo.py` 5, `tests/test_e2e_rgb_vo.py`+`tests/test_e2e_boundary_views.py` 22 → 27/27 통과(한 번에 pytest 1개). `scripts/run_ci_tests.py`에 #444에서 빠져 있던 `test_e2e_rgb_vo.py`와 새 시험을 등록했다.

## 실행 명령 예시 (Azure, 짝지은 A/B, 아직 실행하지 않음)
12차 `submit.py`와 같은 형식이다. 같은 시각·같은 부하로 seed마다 A/B를 짝지어 동시에 제출한다. 제출 전에 `azure_shutdown.py admit`, 여유 메모리 6 GiB 이상, 디스크 예산(실행당 4 GiB 가정)을 확인하고 부하 평균을 기록한다. VM은 끝난 뒤 `deallocated`인지 확인한다.

```bash
SHA=<claude/e2e14-combo 커밋 SHA>; R=/home/ugrp/ugrp-sim
COMMON=(--expected-source-sha "$SHA" --driver-profile study_gemma4_31b_v1
  --relay-receipt "$R/relays/e2e14/a.json" --e2e-live --event-driven-llm --compact-prompt
  --setdown-only-when-relook on_v1 --decider off --exploration-progress frontier_progress_v1
  --pose-fix innovation --path-follow rpp_v1 --dev-light --stall-bundle --mapping-budget case_cap_v1
  --wall-cap-s 25200 --execute)
for SEED in 61001 61002; do
  # A: 14차 세 토글 (v202)
  .venv-sim/bin/python -m scripts.sim_cli workflow run e2e-combo14-v202 --timeout 25260 -- \
    "${COMMON[@]}" --seed $SEED --output "$R/runs/e2e14-a-s$SEED/raw" \
    --stall-odometry rgb_vo_v1 --stall-recovery off --stall-noise off \
    --boundary-views candidate_views_v1 --b-marker-detect contrast_v1 &
  # B: 12차 A 그대로 (v199)
  .venv-sim/bin/python -m scripts.sim_cli workflow run e2e-stall-budget-v199 --timeout 25260 -- \
    "${COMMON[@]}" --seed $SEED --output "$R/runs/e2e14-b-s$SEED/raw" \
    --stall-odometry rgb_pulse_gate_v1 --stall-recovery backup_replan_v1 --stall-noise amcl_alpha_v1 &
done
```
- 실제 제출은 12차처럼 `remote_run_finish.py` 래퍼, `RUN_META.json`(class=dev, pr=446, branch, sha, batch), 환경변수 `MUJOCO_GL=osmesa`와 스레드 1개 설정을 붙인다.
- 13차 v200 정확 속도 토글(`--exact-*`)은 60 SIM초 구간에서 상태 일치만 확인됐다. 비교군을 12차 A 그대로 두기 위해 두 쪽 모두 끈다. 켜려면 A/B에 같이 켜야 한다.

## 참고 자료
- VO: Seegmiller & Wettergreen, IROS 2011; Scaramuzza & Fraundorfer, IEEE RAM 2011/2012; Helmick et al., IEEE Aerospace 2004; Moore & Stouch, IAS-13 2014; Grisetti et al., T-RO 2007. 상세는 `experiments/2026-10-12-e2e-vo/references.json`(PR #444).
- B 관측점·표식: Yamauchi 1997; explore_lite(hrnr/m-explore); McGreavy et al. 2017; Bajpai et al. 2025; Pei et al. SAP-Nav 2026; OpenCV 형태학·임계값 문서; scikit-image `clear_border`. 상세·미확인 표시는 `experiments/2026-10-12-e2e-bboundary/REFERENCES.md`(PR #443).
- 이번 통합 자체는 새 알고리즘이 없다. 버전 관리는 `docs/execution_versioning.md`를 따랐다.

Refs #433 #443 #444
