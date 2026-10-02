# PR #356 독립 검토 — MERGE AFTER FIXES

- 검토자: Codex, `codex/review-356` (작성자 브랜치 수정 없음).
- 검토 HEAD: `1dd9f0e7d0dcf1864cbe6b23dee76b99af1335cf`.
- 비교 main: `0bf41800272ec4c4bfa035cfc5609af8850e3e48`.
- 검토한 새 validator SHA-256: `65eb7d4c2c70533c8e8399f94bcffdff62508ff0dfef5cec948f809642ac953b`.
- **검증기의 수치·신원·시간 검사에서 새 P0/P1 결함을 발견하지 못했다.** 병합은 실패한 필수 CI의 원인 해소와 전체 통과 확인 뒤 진행해야 한다. 문서의 소스 파일 개수도 정정한다.
- 실제 held-out 채점/loader 호출 없음. 실제 자료는 허용된 plan/bundle/result/artifact manifest, 최상위 driver log의 시작 줄, JSONL 첫 행의 **키 이름만** 확인했다. pose/command/camera 값과 후속 행은 검사하지 않았다. 물리·렌더·모델 호출, 실행 중 프로세스·공용 잠금·서버 조작, `.github/workflows` 변경 없음.

## 지적 한 묶음

### P1 — 병합 전 필수 CI 실패 해소 필요 (이번 diff 밖의 기존 문제)

현재 HEAD의 `offline-regression-shard (6/8)`와 집계 `offline-regressions`가 FAILURE다.
[실패 job](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37047591093/job/110972947200)에서
`tests/test_agent_sim_slots.py:76`의 `test_concurrent_admissions_cannot_both_succeed`가
`scripts/agent_sim_slots.py:104` → `scripts/agent_lock.py:39`의 빈 owner JSON 판독으로
`JSONDecodeError`를 냈다. 두 admission이 동시에 시작하는 구체적 시나리오다.
이 세 파일은 main과 대상 HEAD 사이에 변경이 없다. 새 validator의 결함으로 귀속하지 않는다.
실패를 무시하거나 required workflow를 변경하지 말고, 원인을 처리하고 해당 후보의 전체 필수 CI를 확인해야 한다.
[CI 발췌](REVIEW_356_ci_failure.txt), [확인한 전체 check 상태](REVIEW_356_evidence.json)에 증거를 보존했다.

### P2 — 두 지도 모두 source 253개라는 문구 정정

대상 `experiments/2026-10-03-critb-v91/README.md:24`와 `acquisition_contract.json:10`은
각 bundle에 source 253개라고 적지만, 실제 corridor bundle은 **254개**, door geometry는 **253개**다.
각각 전 항목을 지정 수집 SHA의 `git show <SHA>:<path>` 바이트와 대조했고 모두 일치했다.
전체 bundle 계약 해시도 두 지도 모두 일치하므로, 누락된 provenance나 수용 실패는 아니다.
개수 설명만 지도별로 정정한다. 계약 JSON을 수정한다면 새 validator의 PINNED 해시도 함께 갱신하고 재검증해야 한다.

## 1. 동결 바이트

`git fetch origin`, `git diff origin/main...origin/codex/critb-v91`, 해당 ref의 `git archive`로 검사했다.
`preservation.json`의 23개 파일은 main과 archive의 실제 바이트 및 SHA-256이 모두 같다.
기준 B, r4 후보, 기존 validator, 두 수치 계산 모듈, v88/v90/v91 설정·workflow 등록·수집 소스가 포함된다.
기존 PHYSICS_HANDOFF prefix 보존 검사도 통과했다. `.github/workflows` diff는 없다.

댓글이 열거한 실제 파일 해시:

| 파일 | SHA-256 |
|---|---|
| consumer_criterion_B.json | `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f` |
| calibration_candidate_r4.json | `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071` |
| scripts/validate_consumer_criterion_b.py | `8d2a693a6e3bbca79a8214fd388bff79a0609400f07de831ad9be3cf22e85a88` |
| configs/zone_final_pair_v91.json | `a07d412ced2e5e301c327a07f61ca5ab6bc4cfe1f2c8b7b7f33740e4b3a29307` |

## 2. 수치 동등성과 경계값

새 `score`(대상 `scripts/validate_consumer_criterion_b_v91.py:177`)는 frozen `score`를 직접 호출하고
선후관계 미확인 veto만 해제한다. 원본은 그 veto로 validation pass=null을 유지한다.
따라서 비교한 것은 **원본 numerical_pass/metrics와 신규 validation pass/metrics의 동등성**이며,
원본의 null까지 신규 pass와 같다고 주장하지 않는다.

- 0.2/0.5/1/2/3/3.2초, forward/left/yaw 성분, 지도·축별 steps/PRBS 분리와 모든 그룹 AND 판정 유지.
- 각 병진축 × split × horizon × component의 72개 조합마다 `p95=2±1e-10`, coverage `9/10=90%` 및 `8/9<90%`를 검사: **288개** 경계 조합 통과.
  coverage 반례의 p95는 2 미만이므로 coverage 문턱을 독립적으로 검사한다.
  이 경계 조합은 `metrics`와 `score` 사이의 축 요약 seam을 사용한다. 실제 raw 실행으로 표현하지 않는다.
- 별도 전체 합성 궤적은 seam 없이 frozen/new 경로의 모든 metrics를 정확히 비교했다.
  두 병진축에서 p95 경계를 계산한 뒤 상대 `±1e-8` 바로 안/밖의 궤적이 각각 통과/실패한다.
- 독립 구현으로 0.05초 `v_next`와 `v_next*dt` Euler 변위, running/stop tau, 모든 horizon의
  `sigma_velocity=noise_rel*abs(v_next)+noise_abs`, tick별 분산 및 heading Jacobian 누적을 대조했다.
  적분 대조 오차 허용치는 수치 구현 비교용이고, 판정 문턱에는 slack을 추가하지 않았다.
- 미여기 축, 한 부호만 있는 축, 3.2초 창 부족, null rotation 후보는 null 유지.
  실패 축이 있으면 overall=false, 실패 없이 rotation 미검증이면 overall=null이다.
  1σ와 NEES는 참고값이고 추가 문턱이 없다. 후보 승격도 없다.

## 3. 신원·완료·입력 보존

두 실제 metadata bundle은 `zone-final-pair-v91`, `zone-final-pair-heldout-v91`/`3.3.0`,
`04043e274af7351f3d35cb6be77d948cac1b8c6a`, seed 911,
`HELD_OUT_VALIDATION`, `training_eligible=false`, `teacher_only=true`와 일치한다.

| 지도 | 전체 bundle canonical SHA-256 | 검증한 source 항목 |
|---|---|---:|
| zone_wide_corridor_final_v3 | `c52a72bf25253b9dfa37be275d718c6ad5fb4ecc43c0656413cda78506c9dad2` | 254 |
| zone_wide_door_geometry_v3 | `b8871bb860faa2e4d180c81430d9fa58ee73b32a42c9d19611f252462e68900d` | 253 |

plan의 bundle digest/case 연결, 전체 result와 case result 일치, metadata artifact receipt,
완료·source_unchanged 표기를 확인했다. schedule은 실제 본문을 읽지 않고 manifest 해시가 계약과 같은지만 확인했다.
pose/command/image의 전체 파일 해시는 이번 검토에서 재계산하지 않았다.

합성 검사에서는 훈련 지도 `zone_wide_two_doors_final_v3`, 미등록 지도, source/version/seed/role 오류,
v88/v90 relabel, 미완료·source 변경·명령/pose 누락, 상위 기록에서 분리한 case, 중복 지도,
stale artifact receipt 및 채점 중 입력 변경을 모두 INELIGIBLE/모든 pass=null로 거부했다.
입력 하나만 공급하는 모드는 해당 지도 범위로 허용하며 `maps_not_supplied`를 기록하는 명시된 동작이다.
변조된 모든 기록과 manifest를 함께 재작성하는 공격을 막는 서명 체계라고 해석하지 않는다.

## 4. 수집 전 시간 근거

[issue #219 댓글 5958329647](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5958329647)의
실제 GitHub `created_at=updated_at=2026-10-02T18:04:39Z`다. 추정된 18:1x가 아니다.
live API와 snapshot의 id/URL/생성·수정 시각/본문 및 body SHA, 열거된 네 파일의 실제 바이트가 일치한다.

두 지도의 plan/result/case result에는 직접 `started_utc`/`start_utc`가 없다. bundle에도 시작 필드는 없다.
새 validator가 사용하는 것은 이 세 metadata 파일의 다음 Unix 시각이다:

| 필드 | Unix 초 | UTC |
|---|---:|---|
| host_start.physics_holder.acquired_unix | 1790966027.819724 | 2026-10-02T18:33:47.819724Z |
| host_start.concurrent_holders[0].acquired_unix | 1790966027.8539891 | 2026-10-02T18:33:47.853989Z |
| host_start.concurrent_holders[1].acquired_unix | 1790966027.882921 | 2026-10-02T18:33:47.882921Z |

모든 지도/기록에서 위 값들이 같다. 선택될 최솟값은 physics_holder의 시각이며 댓글보다 **1748.819724초 뒤**다.
최상위 driver log의 `start both maps 2026-10-02T18:33:47Z`도 일치하는 보조 근거다.
**validator는 driver log를 파싱하지 않는다.**

수집 SHA의 `scripts/run_final_pair_fast.py:157-162`는 host snapshot을 plan.json에 쓴 뒤 case를 실행한다.
case의 `host_start`는 같은 파일 `43-46`에서 backend 생성 전에 채집되고,
최종 result는 `172`에서 plan의 값을 복사한다. `scripts/agent_lock.py:55`가 잠금 획득 때 `time.time()`을 기록한다.
따라서 획득 시각은 물리 수집 전 **하한**이며 정확한 collection start 시각은 아니다.
댓글 < 모든 하한의 최솟값이라는 검사 방향은 보수적이다. 오래 유지한 잠금은 거짓 수용 대신 거부를 일으킨다.

댓글과 같은 시각/1ms 전은 거부, 1ms 후는 허용하는 합성 경계 검사 통과.
어느 기록의 더 이른 start, 누락/잘못된 timestamp, snapshot/파일 변조, 요청한 GitHub 조회의 실패/변경은 null로 닫힌다.
mtime이나 Git commit date를 근거로 사용하지 않는다. runner 시계와 GitHub 서버 시계의 동기화·서명은 입증하지 않는다.

## 5. raw schema 대조 (첫 행 키만)

frozen/new validator가 실제로 읽는 JSONL은 r1 pose와 r1 commands다.
`fit_unloaded_consumer`의 수치 함수는 이미 읽은 배열을 받으므로 frame loader를 호출하지 않는다.

| 입력 | 읽는 키와 작성 경로 | 확인 |
|---|---|---|
| eval_only/r1/pose.jsonl | `t`, `sample_index`, `base_position_m`, `base_rotation`, `requested_check`; `sim/final_pair_v3.py:203-209` | 두 지도 첫 행에 모두 존재. `map_id`/`load_state`는 reader의 선택 검사이며 writer/실제 첫 행에는 없음. |
| robots/r1/commands.jsonl | 모든 행 `kind`, mecanum일 때 `t`, `duration_s`, `forward`, `left`, `turn`; `sim/final_environment_checks.py:90-98`, `harness/zone_final_pair_excitation.py:58-64` | 두 지도 첫 행 키는 `kind,pulses,t`. reset writer `sim/final_environment_checks.py:66-67`의 initial servo 형식에 해당하고 loader는 이를 건너뛴다. 이후 행은 열지 않았으며 mecanum 필드 존재는 schedule/writer 코드로 확인. |
| robots/r1/frames.jsonl | capture writer `sim/final_pair_v3.py:173-174`, `sim/camera_robot_port.py:113` | 두 지도 첫 행은 `sim_time`이고 `t` 없음. 이 채점 경로는 frame/camera 파일을 읽지 않으므로 기존 assembler의 frame `t` 오류가 전이되지 않음. |

metadata의 plan/result/bundle 필수 key는 실제 파일과 writer를 대조했고,
실제 첫 pose 행의 선택 label 부재와 초기 servo 명령을 반영한 합성 raw도 신규 경로에서 수용됐다.
단, 전체 실제 행의 타입·간격·값·해시나 실제 raw 수용/점수는 **아직 미검증**이다.
이는 본 검토의 held-out 비열람 경계를 지킨 결과다.

## 재현과 결과 보존

환경: 기존 `/opt/anaconda3/bin/python3` 3.13.5, NumPy 2.4.4, SciPy 1.17.1, pytest 8.3.4.
초기 archive cwd의 `python3`는 pytest 없는 Homebrew 3.14를 가리켜 검사 수집 전에 실패했다.
설치 없이 위 절대 실행 파일로 재실행했다.

```sh
review_scratch=$(mktemp -d /private/tmp/ugrp-review356.XXXXXX)
git archive 1dd9f0e7d0dcf1864cbe6b23dee76b99af1335cf | tar -x -C "$review_scratch"
# archive 안에서 기존 git show 기반 보존 검사만 원래 object DB를 조회한다.
(
  cd "$review_scratch"
  GIT_DIR=/Users/changmin/projects/ugrp/.git GIT_WORK_TREE="$review_scratch" \
    /opt/anaconda3/bin/python3 -m pytest -q \
    tests/test_consumer_criterion_b.py tests/test_consumer_criterion_b_v91.py \
    tests/test_review_346.py tests/test_zone_final_pair_fast.py tests/test_zone_final_pair_heldout.py
)
UGRP_REVIEW_356_ROOT="$review_scratch" /opt/anaconda3/bin/python3 -m pytest -q tests/test_review_356.py
rm -rf "$review_scratch"  # 이 명령에서 만든 disposable git archive만 제거
```

- 관련 기존/신규 suite: **224 passed in 156.14s** — [로그](REVIEW_356_related.txt), [JUnit](REVIEW_356_related.xml).
- 독립 추가 suite: **304 passed in 7.24s** — [테스트](../../tests/test_review_356.py), [로그](REVIEW_356_boundaries.txt), [JUnit](REVIEW_356_boundaries.xml).
- 두 최종 suite의 총 528개 검사. 초기 300개 실행은 후속 304개에 포함되므로 합산하지 않았다.
- [메타데이터·바이트·시각·키·CI 근거](REVIEW_356_evidence.json).
- 이번 review의 disposable archive와 확인한 두 reviewer 합성 임시 디렉터리를 제거하고 부재를 확인했다. 실제 raw와 기존 기록은 보존했다.
- 새 실험/학습/평가 결과가 없는 합성 회귀검사이므로 TensorBoard 변환·서버·표시를 수행하지 않았다. Drive는 프로젝트 예외에 따라 사용하지 않았다.

결론: 검토한 validator 바이트의 의미론 검사는 통과. **필수 CI 실패 해소·전체 통과 및 P2 문구 정정 후 병합**한다.
실제 held-out 채점은 이 리뷰에서 수행하지 않았으며, 변경된 후보가 생기면 그 변경 범위를 다시 검토해야 한다.
