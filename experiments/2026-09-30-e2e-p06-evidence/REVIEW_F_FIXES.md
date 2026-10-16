# PR #303 · 6차 독립 검토 F303 수정

2026-10-01 KST. 수정 전 후보 `3782887538db62c4673fe21908d252a3a7616da6`,
독립 검토 `origin/codex/review-303f`의 `b13c9b972d239cc3da67b8b9909e5708ea482917`
([REVIEW_303F.md](https://github.com/kcm0127-dotcom/ugrp/blob/b13c9b972d239cc3da67b8b9909e5708ea482917/experiments/2026-09-30-e2e-readiness/REVIEW_303F.md))의 두 P2를 함께 수정했다.

## 지적 → 수정

- **F303-1, 생성 검사가 원래 귀속 오류를 놓침:** 기존 move는 파일/이벤트 행만
  옮겼다. 이제 move 64개 중 22개에서 A 성공·B 비성공·A 거절 사본을 만들고,
  거절 사본 디렉터리만 B의 run ID로 옮긴다. A/B는 매 사례의 고정 seed로 선택한다.
  옮기기 전 A INVALID·B VALID, 성공 수 `sum(flags)-1`을 확인하고, 모든 파일 바이트가
  그대로이며 이전 위치가 사라졌는지 확인한다. 이후 성공 비증가, A INVALID·B VALID,
  거절 영수증의 A 소유 키를 검사한다. 기존 관계/재생 생성 검사도 유지한다.
- **F303-2, TensorBoard CI의 OpenCV import 실패:** 순수 `claims` 도우미를
  `tests/zone_evidence_fixtures.py`로 옮겼다. E303 검사와 재생 검사는 이 모듈에서
  직접 도우미·지도·입출력 fixture를 가져온다. 실행기 테스트를 통한 `cv2` import를
  끊었으며 의존성 설치 추가·검사 skip·workflow 편집은 하지 않았다.
- **최신 main 반영:** `78ce79162d907d88d38ef3afcfc0c62e4a72aaba`를
  `--no-commit --no-ff`로 먼저 병합했다. 충돌 없이 합쳐졌으며 검사 종료 전에는
  커밋하지 않았다. `.github/workflows` 전체 파일의 바이트와 경로가 origin/main과 같다.
  workflow tree는 `bc804b64df75a6975dbea1e151b0ecefd2717d59`다.
- **독립 반례 유지:** `tests/test_review_303f.py`를 검토 커밋에서 가져왔다.
  수정 전 `--runxfail`에서 2 failed / 0 errors로 두 문제를 재현했다.
  수정 뒤 같은 파일이 `--runxfail`로 10 passed인 것을 확인한 다음 strict-xfail
  표식 둘을 제거했다. assertion 11개는 원 검토본과 AST 기준 동일하다.

## 검증

**최종 관련 회귀 681 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed.**
관계 12,000개·재생 12,000개·원본 변환 192개, 총 **24,192개 생성 사례**를 실행했다.
이는 pytest 항목 안의 사례 수이며 681에 더하지 않는다. 두 xfail을 제거한 F303 10개,
E303 원본 68개, 소유 연결 40개, 등록 소스 22개·source pinning 34개를 포함한다.
`redesign_test_selectors.json`에 F303을 추가해 같은 전체 묶음을 다시 실행할 수 있다.

원 버그를 되살리는 `rejected_owner` 한 줄 변이는 생산 파일을 바꾸지 않고
`collect` 함수만 메모리에서 교체한다. 생성 property만 독립 실행한 결과는
**1 failed / 2 passed / 0 errors / 0 skipped**다. `move`, 첫 사례에서 성공 수
**0 → 1**, `assert 1 <= 0` 실패로 검출했다. 직접 E303 예시의 검출을 대신 세지 않았다.
수정 전에는 이 같은 변이를 넣어도 property 192개가 모두 살아남았음을 재현했다.

OpenCV·MuJoCo·torch·물리 worker import를 차단한 별도 프로세스에서 기존
`tensorboard-export` job과 같은 3개 파일은 **96 passed / 0 failed / 0 errors /
0 skipped**다. 실제 TensorBoard EventAccumulator로 event를 읽었다.
이 결과는 Mac의 기존 Python 3.12 환경에서 CI 의존성 경계를 검사한 것이며,
새 push의 GitHub CI 결과와 구분한다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
REC=experiments/2026-09-30-e2e-p06-evidence
"$PY" "$REC/redesign_test_driver.py" --tb=short
"$PY" "$REC/review_f_offline.py" . --mutation rejected_owner \
  tests/test_zone_referee_ownership.py::test_192_generated_raw_record_transformations_never_increase_success --tb=short
"$PY" "$REC/review_f_offline.py" . --without-cv2 \
  tests/test_tensorboard_export.py tests/test_offline_audit_export.py tests/test_owncam_loop_views.py --tb=short
```

정확한 명령·JUnit 집계·로그 및 소스 해시는 [review_f_verification.json](review_f_verification.json)에 남긴다.
원본 로그/JUnit은 `/Users/changmin/projects/ugrp/outputs/p06-review-f-fix/`에
로컬 보존하며 원격 raw 백업이라고 부르지 않는다. 작은 기록·재현 코드만 커밋한다.
기존 심판·키·귀속·봉인·변환 판정과 고정 실행기 7개 파일은 수정 전 후보와 바이트가 같다.

## 범위와 남은 일

로컬 물리·렌더·학습·실제 모델 호출은 0회다. 공용 잠금·서버·대시보드·Drive는
사용하지 않았다. `docs/tensorboard.md`의 synthetic 경계대로 테스트 event는 OS 임시
경로에만 쓰고 공용 snapshot에 게시하지 않는다. 실제 연구 raw는 변경하지 않았다.
`/private/tmp` 추출 디렉터리는 만들지 않았다. 새 가상환경도 만들지 않았다.

PR #303은 Draft를 유지하고 병합하지 않는다. 수정본의 독립 재검토, 실제 실행기 연결,
물리/E2E 인수, provider 정산과 실제 결과의 공용 대시보드 인수는 이 작업의 검증 범위 밖이다.
