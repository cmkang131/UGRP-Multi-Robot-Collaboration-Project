# PR #356 독립 검토 P1/P2 일괄 수정

대상 `1dd9f0e7d0dcf1864cbe6b23dee76b99af1335cf`, 검토
[`05b3c845`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/05b3c845bf7e0bf40a6136eea1bbd565f419278e/experiments/2026-10-03-critb-v91/REVIEW_356.md)와
[댓글 5959437915](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/356#issuecomment-5959437915)의
두 지적을 한 묶음으로 수정했다. `origin/main=7cd729416fc04dfc4633cb4da5c4cd9435dd582d`(#357)을
충돌 없이 병합했다. 실행 코호트를 새로 만들지 않았으며 기존 기록을 보존했다.

## P1 — 동시 잠금 획득의 빈 owner JSON

옛 잠금은 디렉터리를 먼저 만든 뒤 `owner.json`에 직접 쓴다. v91 슬롯과 옛 도구가 동시에
획득하면 패자가 아직 비어 있는 JSON을 읽고 `JSONDecodeError`를 냈다. 옛 `agent_lock.py`는
v88/v90 등 과거 등록의 해시에 포함되므로 바이트를 그대로 보존했다.

- v91 슬롯은 기존과 같은 원자적 `mkdir`로 소유권을 정하고, 완성한 임시 JSON을 `replace`하여
  공개한다. 옛 도구가 패자인 경우에도 빈 owner 파일을 보지 않는다.
- 옛 도구가 승자인 경우 v91 판독은 작성 중/불완전한 JSON을 명시적인 `RuntimeError` 거부로
  처리한다. 잠금을 삭제하거나 빈 호스트로 취급하지 않는다. `mkdir` 경쟁에서 진 경우는 owner를
  다시 읽지 않고 즉시 거부한다.
- 양쪽 획득 순서에서 writer를 정확히 멈춘 반례 2개, 빈/부분 JSON 2개, 존재 검사와 mkdir 사이
  경쟁 1개를 추가했다. **수정 전 5개 모두 실패**([로그](before-tests.txt)); 수정 후 모두 통과했다.
  기존 동시 admission 검사의 `RuntimeError` 기대를 완화하거나 CI를 건너뛰지 않았다.
- 같은 coordinator의 여러 슬롯, 마지막 슬롯 해제, borrowed lock 보존과 과거 bundle/plan 전체
  writer 바이트 검사를 함께 통과했다. 이 수정은 옛 도구끼리의 동시 JSON 공개 방식까지 바꾸지 않는다.

## P2 — 지도별 source 개수와 PINNED

README와 `acquisition_contract.json`의 설명을 corridor **254개**, door geometry **253개**로
정정했다. 계약 문서의 새 SHA-256은
`a947308083a03fcb5af3bc6d7155e0727317acb98084027d051bd93f9161c2eb`이며 검증기의
`PINNED`도 함께 갱신했다. 두 지도 bundle 지문, schedule 지문, 수집 SHA, B/r4와 판정 로직은 그대로다.

슬롯 모듈 수정으로 현재 소스 해시가 달라지므로 합성 fixture의 source receipt는 현재 checkout이
아닌 고정 수집 SHA `04043e274af7351f3d35cb6be77d948cac1b8c6a`의 Git 파일로 만든다.
`git archive`로 source 항목 전부를 읽어 해시를 재계산하고 기존 canonical bundle 지문과 정확히
같음을 검사했다. 현재 슬롯 소스를 과거 수집으로 다시 표시하면 거부하는 반례도 추가했다.
이는 합성 자료의 출처를 맞춘 것이며 production 검증기의 해시 비교를 완화하지 않는다.
수정 소스로 앞으로 수집할 자료가 기존 04043e27 자료의 신원이나 성공 판정을 승계하지 않는다.

## 검증과 범위

환경은 기존 `/opt/anaconda3/bin/python3` 3.13.5, NumPy 2.4.4, SciPy 1.17.1, pytest 8.3.4다.
설치·환경 변경은 없다. 명령·부하 평균·pass line은 로그에, 파일 해시·JUnit 집계는
[verification.json](verification.json)에 보존했다.

```text
303 passed in 205.11s (0:03:25)  # 관련 회귀: 잠금, B/v91, #346/#355, fast/heldout fake
304 passed in 7.41s             # origin/codex/review-356의 독립 합성 검사를 수정 소스에 재실행
78 passed in 1.95s              # CI 분기·분할
```

최종 세 suite는 **685 passed**, 실패·skip·xfail 0이다. 먼저 실행한 잠금 38개는 303개에 포함되므로
합산하지 않는다. [관련 로그](related-tests.txt)·[JUnit](related-tests.xml),
[독립 검사 로그](review-tests.txt)·[JUnit](review-tests.xml), [CI 검사 로그](ci-tests.txt)·[JUnit](ci-tests.xml).
독립 검사 재실행은 작성자가 수행한 회귀검증이며 새 독립 승인으로 표시하지 않는다.

보호 파일 23개, 기존 `agent_lock.py`, 기존 PHYSICS_HANDOFF prefix와 등록 보존 검사가 통과했다.
live 약속 댓글과 snapshot도 일치했다. frozen fixture preflight, 현재 bundle 정적 검증,
registry 불변 검사, 미디어 크기 검사와 `git diff --check`가 통과했다.
`.github/workflows`, `configs`, `harness`, `sim` 변경은 없다.

실제 `final-pair-v91-heldout-*` 파일은 신원 필드를 포함해 열지 않았다. 물리·렌더·모델 호출,
실제 held-out 채점, 공용 잠금·실험 프로세스·서버 변경은 없다. 합성 회귀검사만 수행했으므로
새 TensorBoard 평가 결과나 Drive 업로드를 만들지 않았다. `gh` 로그 캐시의 기본 경로 쓰기가
거부되어 작업 전용 `/private/tmp` 캐시로 원래 실패 CI 로그를 회수했다([로그](ci-before.txt)).
두 실패 로그는 Git 표시용 사본의 줄 끝 공백만 정리했다. 정확한 원본은 프로젝트 `outputs/`에
별도 보존했으며 위치·SHA-256은 verification.json의 `log_normalization`에 기록했다.

로컬 검사 통과 후 이 변경을 commit/push하고 PR을 ready로 전환한다. 새 HEAD의 GitHub 필수 CI
결과는 push 뒤 PR 댓글로 확인하며, 로컬 통과를 원격 CI 통과로 표현하지 않는다. 변경 범위의
독립 재검토와 실제 held-out 채점은 별도다. 이번 요청의 종료 지점은 리뷰 준비이며 PR 병합은 수행하지 않는다.
