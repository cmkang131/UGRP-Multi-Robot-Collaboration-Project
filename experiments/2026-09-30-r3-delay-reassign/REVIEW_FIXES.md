# T12 Batch F 수정과 main 합성 검증

2026-10-01 KST. PR #324는 DRAFT로 유지하며 GitHub에서 병합하지 않는다.
오프라인 코드·fake API 검사이며, 로컬 물리·MuJoCo 렌더·외부 모델 호출은 0회다.

## 수정과 지적 대응

- #323 `ad22566311cf1efb2911af69ee2b8e4c9c650dd0`를 merge했다. 첫 merge 커밋은
  `d779085619d23bced0aec97c2e78e0168a78db09`다. rebase나 force push는 사용하지 않는다.
- main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`도 merge했다. 이 main에는 #323이 병합되어
  있고 #324의 GitHub base도 main으로 바뀌었다. 두 merge 모두 텍스트 충돌은 없었다.
- T12 역할 통합 테스트의 `setup`을 `tests.test_zone_pair_role_exchange`에서 가져오도록 수정했다.
  기존 executor의 `active` helper와 r1/r2 fixture는 유지했다.
- `RoleAwareOwnPairPort` 설명과 인계에 `zone_pair_role_host.OwnCamTeamHost` 및
  `zone_pair_role_integration`을 명시했다. 봉인 host에서 네 인자 역할 API가 거절되고
  구형 API로 재시도하지 않는 실제 fake-host 검사 2개를 추가했다.
- T07의 역할 구현이나 T12의 복구 제어 로직을 수정·복제하지 않았다. 봉인 소스·등록 해시·
  시나리오·bundle은 그대로이며, workflow도 합성한 main과 동일하다(#332 변경만 상속).

#327 `887b4d5e73823733a39d10060734080e46668548`의 #324 지적은 선행 #323에서 상속한
F1 봉인 파손과 main 합성 재검사였다. 두 pin 파일은 #323 합성 후와 최종 main 합성 후 모두
통과했다. v6e 소스 85개·scene 소스 12개가 원래 해시와 일치한다. F2 수정도 그대로 가져와
T12 tree에서 keepout 제거 및 반대 역할 전달 변이로 다시 검사했다.

## 검증

| 실행 | 결과 | 범위 |
|---|---|---|
| #323 합성 뒤 핵심 6파일 | 447 passed | T12 206, T07 145, 기존 executor 40, pin 56 |
| 최종 main 합성 18파일 | 463 passed + 280 subtests passed | pair/status/review, v6e, study, 혼합 작업, CI, 두 pin 파일 |
| 변이 전 / 원본 복구 | 각각 79 passed | 반복한 기준 검사이며 새 통과 수로 더하지 않음 |

최종 정상 검사의 실패·오류·skip은 모두 0이다. 두 suite 사이의 pin 56개를 빼면 고유 테스트는
**854개 + 280개 subtest**다. JUnit testcase ID의 교집합/합집합도 56/854로 확인했다.
main 합성 전후 T12·T07 전체 의존 소스 202개와 이미 검사한 핵심 테스트는 바이트가 같다.
이전 입력 목록에서 바뀐 것은 합성된 `scripts/run_ci_tests.py`뿐이며 추가 suite에서 검사했다.
CI 목록 340파일/8 shard에 누락·중복이 없고 T12/T07/P02/P01/T13b 항목이 각각 한 번 포함된다.

| 변이 | assertion 실패 | errors / skipped |
|---|---:|---:|
| stale 취소 방어 제거 | 18 | 0 / 0 |
| 제출 timeout 제거 | 32 (정상 경계 16개 통과) | 0 / 0 |
| 구형 r1/r2 fixture 복원 | 1 | 0 / 0 |
| opt-in 계획의 keepout 제거 | 12 | 0 / 0 |
| driver에 반대 역할 keepout 전달 | 6 | 0 / 0 |

다섯 변이는 임시 사본의 봉인되지 않은 모듈·테스트에만 적용했다. 작업 트리와 봉인 파일은
변이하지 않았다. 각각 원본으로 복구했고 마지막 79개 기준 검사도 다시 통과했다.

## 실패 보존과 검증 도구 복구

구형 fixture의 `BAD_PAIR_ARGUMENTS` 실패 1개를 먼저 보존한 뒤 연결을 고쳤다. 첫 447개 통과
직후에는 변이 선택 문자열 대신 정수 필드를 읽는 도구 오류가 났다. 선택 인덱스를 고쳐
변이 단계만 새 원본 폴더에서 다시 실행했다.

첫 main 추가 검사는 406 passed + 280 subtests passed / 1 failed였다. 검증 도구가 실제
worktree에도 `GIT_DIR`/`GIT_WORK_TREE`를 전달해 CI의 임시 Git 저장소 검사가 실제 pending
merge를 `CI Fixture` 작성자와 `fixture` 메시지로 커밋했다. `git init`은 공용 config의
`core.worktree`도 바꿨다. 이는 제품 제어기 실패가 아닌 검증 도구의 잘못이다.

실제 worktree 검사에서는 두 환경변수를 제거하고, 역사 blob을 읽는 임시 변이 사본에서만
지정하도록 수정했다. 공용 config에 잘못 추가된 현재 worktree 경로 값 하나만 제거했다.
기본 checkout/worktree의 각각의 top-level과 기본 checkout의 clean 상태를 확인했다.
그 뒤 18파일을 모두 재실행해 463 + 280 통과와 검사 전후 HEAD 불변을 확인했다.
미전송 fixture 커밋 `59e68c338cbf8904ab3177c833e852ad4c8098bc`의 메시지·부모·tree와
사고 기록은 raw에 보존했다. 검증 뒤 해당 미전송 merge 커밋의 작성자·메시지·trailer를
바로잡았다. 원격은 이 복구 전까지 시작 SHA 그대로였으며 정상 push만 사용한다.

## 재현과 남은 범위

기존 Mac Python을 쓰며 host lock 없이 실행한다. 오프라인 guard가 simulator/worker/외부
network 사용을 막는다. 실제 명령·JUnit·입력 해시·원본 위치는
[review_fixes_verification.json](review_fixes_verification.json)에 있다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-30-r3-delay-reassign/review_checks.py --related
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-30-r3-delay-reassign/review_checks.py --tests-only tests/test_ci_sharding.py tests/test_ci_fast_path.py
```

원본은 primary `outputs/cap-t12-r3-delay/review-*`에 로컬 보존하며 원격 raw 백업으로 표현하지
않는다. 실행·학습·평가 cohort가 아니므로 TensorBoard snapshot/로봇 성공률을 만들지 않았다.
Drive는 프로젝트 예외에 따라 사용하지 않는다. 정상 GitHub CI 결과는 최종 SHA와 함께 #324의
한 번의 후속 댓글에 남긴다. 기존 425개 기록은 당시 증거로 보존한다.

40초 늦은 제출 검사는 실제 hold 주입·바퀴 정지·own RGB 인지·물리 재집결의 근거가 아니다.
기본 study actor 연결과 최종 환경의 물리 2셀은 계속 미실행이며 [인계](COORDINATOR_HANDOFF.md)의
경계를 유지한다.
