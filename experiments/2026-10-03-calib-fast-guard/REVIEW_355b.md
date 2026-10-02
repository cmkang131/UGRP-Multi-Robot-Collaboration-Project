# PR #355 독립 재검토 — MERGE

- 대상: **04043e274af7351f3d35cb6be77d948cac1b8c6a** (`codex/calib-fast-guard`).
- 비교 main: **6f8460ad61ed858025a9e1d5d6ce77d7b92d9b1f**. 이전 검토: [fd1e82d2의 REVIEW_355.md](REVIEW_355.md).
- 검토자: Codex, `codex/review-355`. 구현자의 결과를 합산하지 않고 대상 `git archive`에서 직접 재검사했다.
- **판정: MERGE — 이번 범위의 P1a/R1·P1b/R2 해소.** 이는 해당 SHA의 코드 재검토 판정이다. GitHub 검사 33개 SUCCESS도 확인했다. PR은 draft이며 사용자 지시대로 병합하지 않는다.

## P1a/R1 — 해소

`scripts/agent_lock.py`는 origin/main과 바이트 동일하다. SHA-256은
`709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce`다.
옛 모듈에 새 슬롯 모듈 import가 없고, v91만 `scripts/agent_sim_slots.py`를 사용한다.

PR에서 추가했던 `historical_lock_receipt`, heldout 해시 치환과 `agent_lock_successor.py`가 없어졌다.
`test_review_352.py`, `test_zone_final_pair_heldout.py`,
`test_final_environment_measurement_v2.py`, `test_zone_final_environment_floor_light.py` 네 파일은
main 바이트와 동일하며, 해당 PR의 lock 예외도 제거됐다. 해시 monkeypatch나 source 항목 제외 없이 검사했다.

이전 리뷰의 독립 [audit_hashes.py](review355/audit_hashes.py)를 수정 없이 실행하여
v88 7개 + v90 2개, **9/9 등록 조합**의 전체 `source_sha256`, bundle writer SHA,
canonical bundle digest, plan writer SHA, plan의 `bundles_sha256`이 이전 main 원값과 모두 같음을 확인했다.
`source_sha` 인자는 양쪽 모두 `a` 40개로 고정했다.
[전체 원값](review355b/head-hashes.json), [비교·바이트 검사](review355b/static.json).

## P1b/R2 — 해소

대상 `scripts/agent_sim_slots.py:71–77,88–112,115–138`에서 다음을 직접 확인했다.

- 다른 owner의 non-timing 잠금과 모든 timing-sensitive 잠금은 슬롯을 거부한다.
  claude/codex/kiro의 holder·entrant 9개 조합 × timing 2개를 검사했다.
- 기존 잠금을 빌릴 때는 같은 owner·같은 살아 있는 coordinator PID·non-timing이어야 한다.
  다른 live PID, 잘못된 owner/branch, 죽은 PID, 불완전·고아 슬롯, 교체된 physics 소유권은 거부한다.
- 잠금이 없으면 첫 슬롯이 **변경하지 않은 legacy acquire의 atomic mkdir**로 physics를 예약한다.
  따라서 슬롯↔배타 잠금 양쪽 획득 순서와 main SHA의 옛 timing acquire에서도 우회가 막힌다.
  기존 `agent_lock.py` API 테스트와 슬롯 없는 v91 exclusive 실행 경로도 통과했다.
- 첫 슬롯 해제 후에는 physics가 남고 마지막 슬롯에서만 자동 생성한 physics를 해제한다.
  두 해제 순서와 세 owner를 검사했다. 빌린 기존 잠금과 교체된 잠금은 보존한다.
- 살아 있는 슬롯의 stale 해제는 같은 owner도 거부한다. 죽은 두 슬롯은 각각 명시적으로 해제해야 하며,
  첫 stale 해제 뒤에도 legacy exclusive 진입이 차단되고 마지막 해제 뒤에만 재개된다.
- 두 슬롯·두 지도 fake 실행의 출력 디렉터리와 plan의 slot/map을 구분했다.
  같은 출력 재사용과 exists→mkdir 경쟁은 거부하고 먼저 작성한 파일을 바이트 그대로 보존한다.

예전 exclusive 실행기와 v88/v90 소스 closure는 바뀌지 않았다. 이 보존과 legacy API 테스트를 함께 확인했다.
동시 수집 운영은 인계문서의 coordinator가 모든 자식을 기다리고, 실행 중 legacy release/stale로
physics를 삭제하지 않는 계약을 전제로 한다. coordinator 사망 후 실제 자식 종료 확인은 운영자의 책임이다.
이번 검사는 그 운영 계약을 실제 두 지도 물리 수집으로 검증한 결과가 아니다.

## 독립 실행 결과

원래 fd1e82d2의 반례 파일을 별도 이름으로 복사하고 슬롯 함수의 import 대상만 새 모듈로 연결했다.
assertion과 원본 expected hash를 유지한 채 `--runxfail`로 실행하여 **18/18 passed**를 확인했다.
실패를 xfail로 숨긴 통과가 아니다. [원본 이식 파일](review355b/original_counterexamples.py),
[JUnit](review355b/original18.xml), [로그](review355b/original18.txt).

추가 직접 작성한 [인접 변형](review355b/nearby_variants.py) 29개와 대상 SHA의 리뷰·슬롯·legacy lock·
v91 등록/실행·guard 검사는 **154 passed, 실패·skip·xfail 0**이다. 최종 집계는 [verification.json](review355b/verification.json)과
[scoped.xml](review355b/scoped.xml)에 있다. 원래 18개와 대상에 이식된 동일 반례는 중복 합산하지 않는다.

완료 raw 두 개에 대상 verifier를 `--benchmark` 없이 다시 실행했다.

| 완료 원본 | 행별 guard 일치 | 불일치 | 50 ms 순차 일치 / 합성 변위 abort |
|---|---:|---:|---:|
| unloaded r1 | 7,401/7,401 | 0 | 7,401 / 7,286 |
| fine r6 | 7,401/7,401 | 0 | 7,401 / 7,286 |

합계 **14,802/14,802**. 예외 종류·문자열, 최소 간격 float hex, hold, eval_only abort 내용,
이전 geometry 좌표 바이트를 대조했다. trajectory/bundle/result 해시와 최소 간격 시리즈 해시도
이전 리뷰와 동일하다([raw-equivalence.json](review355b/raw-equivalence.json)).
`render=False`, renderer 없음, 기록된 qpos/qvel 설치 후 `mj_kinematics`만 사용했다.
50 ms 순차 비교는 0.25 ms substep 복원이 아니며 합성 abort를 수집 실패로 해석하지 않는다.
속도·처리율·wall timing은 측정하지 않았다.

## 범위·정리

렌더링·모델 호출·새 수집·기존 프로세스 조작·공용 잠금 쓰기는 수행하지 않았다.
테스트 잠금·fake 출력은 공용 경로와 분리된 pytest 임시 경로만 사용했다. raw는 읽기만 했다.
실행 중 claude v88 non-timing physics 소유권 파일의 전후 SHA는 동일하다.
`.github/workflows`는 대상 PR과 이번 리뷰 모두 변경 없음이다.
코드 회귀와 기존 raw 재검토이므로 TensorBoard 재변환·서버·대시보드는 만들지 않았으며 Drive도 사용하지 않았다.

scratch의 tracked blob **9,188개 모두 대상 SHA와 동일**함을 검사한 뒤 추출 디렉터리를 삭제했다.
scratch 경로·대상 tracked 파일 보존 검사·삭제 후 부재 확인은
[cleanup.json](review355b/cleanup.json)에 기록했다. 리뷰 파일과 작은 검증 기록만 커밋·push한다.
PR head·CI 조회는 [pr-checks.json](review355b/pr-checks.json)에 보존한다.
병합·기본 checkout 갱신은 하지 않는다.

실제 두 지도 동시 수집과 처리율, frozen criterion B의 v90/v91 수용, 학생/실물 성공은 여전히 미검증이다.
기존 claude 잠금이 유지되는 동안 codex v91 슬롯은 시작할 수 없으며 이 판정은 실행 권한을 확대하지 않는다.

## 재현 명령

`git archive 04043e274af7351f3d35cb6be77d948cac1b8c6a` 추출본에
`original_counterexamples.py`와 `nearby_variants.py`를 각각
`tests/test_review_355b_original.py`, `tests/test_review_355b_variants.py`로 복사한다.
아래 명령은 추출본 cwd에서 실행한다. GIT_DIR은 읽기 전용 역사 조회 테스트에만 제공했고
git init/add를 하는 workflow fixture는 실행하지 않았다. 모든 검사 출력은 리뷰 기록 경로에 저장했다.

```bash
GIT_DIR=/Users/changmin/projects/ugrp/.git /opt/anaconda3/bin/python3 -B -m pytest -q \
  tests/test_review_355b_original.py --runxfail \
  -k 'legacy_registered_source or legacy_writer_bytes or exclusive_lock_excludes or pinned_legacy_timing'
GIT_DIR=/Users/changmin/projects/ugrp/.git /opt/anaconda3/bin/python3 -B -m pytest -q \
  tests/test_review_355.py tests/test_agent_sim_slots.py tests/test_agent_lock.py \
  tests/test_zone_final_pair_fast.py tests/test_final_pair_fast_guard.py \
  tests/test_final_pair_fast_replay.py tests/test_review_355b_variants.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -B \
  -m scripts.verify_final_pair_fast_guard --output /private/tmp/review355b-raw-equivalence.json
```
