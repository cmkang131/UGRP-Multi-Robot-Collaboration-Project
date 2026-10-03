# PR #356 독립 재검토 R2 — MERGE

- 검토자: Codex, `codex/review-356`. 작성자 브랜치의 구현은 수정하지 않았다.
- 검토 HEAD: **`352a2389b30b6e95025e375beec0ec9eb68c2355`**.
- 변경 범위: `1dd9f0e7d0dcf1864cbe6b23dee76b99af1335cf..352a2389b30b6e95025e375beec0ec9eb68c2355`만 재검토.
- main: `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`. 이 범위에 들어온 #357 운영 기록 8개는 main과 동일하다.
- 이전 [R1](REVIEW_356.md)과 [수정 대응 댓글 5965818596](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/356#issuecomment-5965818596)의 P1/P2를 모두 확인했다.
- **이전 지적 2개 해소. 변경 범위에서 새 P0/P1/P2 지적 없음. MERGE 권고.** 실제 held-out 점수나 물리 성공에 대한 판정은 아니다.

## 지적 일괄 확인

| 이전 지적 | R2 확인 | 판정 |
|---|---|---|
| P1: 동시 admission에서 빈 owner JSON을 읽어 필수 CI 실패 | `scripts/agent_sim_slots.py:43`의 판독 거부, `:98`의 원자적 mkdir 및 완성된 JSON 공개, `:123`·`:131`의 새 획득 경로를 검토했다. 패자가 owner를 재판독하지 않고 거부한다. 아래 5개 반례는 이전 코드에서 전부 실패하고 현재 코드에서 전부 통과했다. 같은 HEAD의 원격 CI도 전체 통과했다. | 해소 |
| P2: 두 지도 모두 source 253개라고 쓴 설명 | `experiments/2026-10-03-critb-v91/README.md:24`, `acquisition_contract.json:10`은 corridor 254개 / door geometry 253개로 정정됐다. `scripts/validate_consumer_criterion_b_v91.py:36`의 PINNED가 실제 계약 바이트 SHA-256 `a947308083a03fcb5af3bc6d7155e0727317acb98084027d051bd93f9161c2eb`와 일치한다. | 해소 |

P1 반례는 `tests/test_agent_sim_slots.py:81`의 양방향 공개 경쟁 2개,
`:109`의 빈/부분 JSON 2개, `:120`의 존재 검사와 mkdir 사이 경쟁 1개다.
현재 테스트를 별도 Python 프로세스에서 이전 `1dd9f0e7` 슬롯 모듈에 연결하여
**5 failed, 27 deselected**를 독립 재현했다. 현재 슬롯 suite는 **32/32 통과**했고,
기존 동시 admission, 같은 coordinator의 복수 슬롯, 마지막 슬롯 해제,
borrowed/replaced lock 보존과 stale 거부도 통과했다.
공용 잠금 대신 테스트 임시 경로만 사용했다. 옛 도구끼리의 잠금 구현은 이번 변경 범위가 아니다.

P2의 합성 fixture는 `tests/test_consumer_criterion_b_v91.py:55`에서 고정 수집 SHA
`04043e274af7351f3d35cb6be77d948cac1b8c6a`의 Git 바이트로 source receipt를 재구성한다.
`:176`의 지도별 개수·전체 canonical 지문 일치와 `:185`의 새 슬롯 소스 relabel 거부를 확인했다.
production bundle/schedule 지문·수집 SHA는 변경되지 않았고, production 검증을 완화하지 않았다.

## 동결 바이트·채점 동등성·시간 검사

- `preservation.json`의 **23개 파일**은 기록된 SHA-256과 일치하며, 원래 base `0bf41800`, R1 HEAD,
  R2 HEAD, 현재 main, 검토용 archive의 바이트가 모두 동일하다. B/r4, 기존 validator,
  두 수치 계산 모듈, v88/v90/v91 설정·등록·수집 writer가 포함된다.
- 별도로 기존 `scripts/agent_lock.py`의 SHA-256은
  `709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce`로 유지된다.
  PHYSICS_HANDOFF의 고정 prefix와 v88/v90 bundle/plan writer 바이트 검사도 통과했다.
- 신규 validator의 전체 SHA-256은
  `d166d76900480ae47dcea0b0e3c2ad854288953aa9e0d1cab19606d5db2ea3b9`다.
  R1 바이트에서 **계약 PINNED 문자열 한 곳만 치환하면 현재 파일과 정확히 같다**.
  계약 JSON에서도 `source_verification` 설명 외 모든 값이 같다. 채점·시간 검사 코드는 변경되지 않았다.
- 기존 독립 `tests/test_review_356.py` **304개**를 현재 소스에 재실행했다.
  288개 축/split/horizon/component 경계 조합, 전체 합성 궤적의 metrics 동등성,
  독립 Euler·분산 누적, 미검증 축/null, 입력 변조 거부, ±1ms·동일 시각 chronology 경계를 통과했다.
  frozen `numerical_pass`와 신규 validation pass의 동등성을 검사하며,
  frozen 원본의 chronology veto로 인한 null을 신규 pass와 같다고 표현하지 않는다.
- 관련 suite의 더 이른 시작 시각, 누락·잘못된 runner timestamp, snapshot/파일 변조,
  요청한 GitHub 재조회 실패·변경, 채점 중 입력 변경 거부도 통과했다.
- `verify_commitment([], refetch=True)`로 live GitHub 댓글과 저장 snapshot의 신원·본문·시각·해시를
  다시 대조했다. 댓글 생성·수정 시각은 모두 **2026-10-02T18:04:39Z**로 동일하다.
  R2에서는 실제 수집 metadata를 다시 열지 않았다. 실제 수집 시각 근거의 R1 감사 범위는 그대로이며,
  잠금 시각은 수집 전 하한이고 runner/GitHub 시계 동기화·서명을 보증하지 않는다.

## 검증 결과와 재현

현재 HEAD를 `/private/tmp`의 disposable `git archive`로 풀고 기존 Python 3.13.5 환경을 사용했다.
원래 Git object DB는 보존 검사와 고정 source receipt를 읽는 데만 연결했다.
실행 명령과 시작 부하 평균은 각 로그에 보존했다.

| 검사 | 이번 독립 재실행 결과 | 근거 |
|---|---:|---|
| 잠금·B/v91·#346/#355·fast/heldout fake 관련 suite | **303 passed in 295.31s**, 실패·skip 0 | [로그](REVIEW_356_R2_related.txt), [JUnit](REVIEW_356_R2_related.xml) |
| R1 독립 경계·전체 합성 궤적 suite | **304 passed in 9.95s**, 실패·skip 0 | [로그](REVIEW_356_R2_boundaries.txt), [JUnit](REVIEW_356_R2_boundaries.xml) |
| 이전 코드에 현재 잠금 반례 연결 | 예상대로 **5 failed** | [로그](REVIEW_356_R2_before.txt), [JUnit](REVIEW_356_R2_before.xml) |

현재 코드의 최종 합계는 **607 passed**, 실패·skip·xfail 0이다.
32개 슬롯 검사와 5개 수정 반례는 303개에 포함되므로 중복 합산하지 않았다.
이전 코드의 예상 실패 5개도 현재 코드 합계에 넣지 않았다.

기본 재현 명령은 아래와 같다. `REVIEW_ROOT`는 해당 HEAD의 archive 경로다.

```sh
# archive 안에서
GIT_DIR=/Users/changmin/projects/ugrp/.git GIT_WORK_TREE="$REVIEW_ROOT" \
  /opt/anaconda3/bin/python3 -B -m pytest -q \
  tests/test_agent_lock.py tests/test_agent_sim_slots.py tests/test_review_355.py \
  tests/test_consumer_criterion_b.py tests/test_consumer_criterion_b_v91.py \
  tests/test_review_346.py tests/test_zone_final_pair_fast.py tests/test_zone_final_pair_heldout.py

# codex/review-356 worktree 안에서
GIT_DIR=/Users/changmin/projects/ugrp/.git GIT_WORK_TREE="$REVIEW_ROOT" \
  UGRP_REVIEW_356_ROOT="$REVIEW_ROOT" \
  /opt/anaconda3/bin/python3 -B -m pytest -q tests/test_review_356.py
```

[GitHub CI run 37098753504](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37098753504)의
head SHA가 검토 SHA와 같고 **33/33 checks SUCCESS**임을 live API로 확인했다.
이전에 실패한 shard 6과 필수 집계 `offline-regressions`도 SUCCESS다.
PR은 OPEN·Ready·MERGEABLE이며 `reviewDecision=REVIEW_REQUIRED`다.
이 문서는 독립 검토 권고이고 GitHub의 승인 리뷰나 실제 병합 완료 기록은 아니다.

세부 SHA·체크 URL·테스트 집계는 [evidence JSON](REVIEW_356_R2_evidence.json)에 보존했다.
예상 실패 로그의 Git 사본에서는 줄 끝 공백만 정리했으며, 정확한 원본의 로컬 경로·해시도 기록했다.

## 범위와 남은 작업

이번 재검토에서 실제 `outputs/final-pair-v91-heldout-*` 아래 파일은 신원 필드를 포함해 **하나도 열지 않았다**.
실제 자료 채점·수용 여부, 물리 실행·렌더·모델 호출은 수행하지 않았다.
실행 중 프로세스·공용 잠금·서버 및 `.github/workflows`를 변경하지 않았다.
R1 이전 구현 전반의 재감사는 수행하지 않고, 변경에 관계된 의존성과 동결 계약만 확인했다.

#357에서 들어온 운영 기록은 저장소 안의 문서·JSON만 확인했다.
수집 4개의 파생 뷰는 기록의 해시·개수·시각 차와 내부적으로 일치하고,
v91은 `heldout-unscored`를 유지하며 통제된 속도 비교나 성공 판정으로 표시하지 않는다.
그 기록의 raw·대시보드는 재검증하지 않았다.

새 실험/학습/실제 평가 결과가 없는 합성 회귀검토이므로 TensorBoard 변환·화면을 추가하지 않았다.
프로젝트 예외에 따라 Drive는 사용하지 않았다. 리뷰 결과는 이 브랜치에 보존하며,
요청된 종료 지점에 맞춰 PR 댓글 전달까지 수행하고 실제 병합·held-out 채점은 별도 작업으로 남긴다.
