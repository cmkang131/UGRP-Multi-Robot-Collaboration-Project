# R20 · #6 CI 세션 종료 실패의 현재 증거

**판정: 현재도 지원되는 테스트 경로이지만, 과거 간헐 실패의 원인과 현재 잔존 여부는 증거 부족이다.** 현재 main의 CI는 통과했다. 이를 원인 해결로 표시하지 않으며, 옛 실패를 현재 blocker로 재등록하지 않는다. 새 구현 finding이나 CI 재실행은 없다.

공식 [#6](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/6)은 계속 open이다. 당시 docs PR #5의 테스트가 예상 143 대신 1을 반환했고 같은 source의 push CI는 통과했다고 기록한다. [유일한 후속 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/6#issuecomment-5844318978)은 #212의 macOS EPERM 정리 수정과의 관련성이 미확인이라고 명시한다. 이번에는 그 문구를 해결 증거로 바꾸지 않았다. PR #5 자체는 2026-09-09에 merged/closed됐으므로 원래 이슈의 병합 보류 문장을 현재 PR 상태로 재사용하지 않는다.

## 확인한 현재성과 과거 로그

| 근거 | 직접 확인한 범위 | 판정에 쓰지 않은 추론 |
|---|---|---|
| [원래 실패 run 34330522269](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/34330522269), API head `4bad601e…`, 실제 checkout merge `630ef9fe…` | 2026-09-09, `offline-regressions`의 `Run offline regression suite` step failure. 해당 테스트 traceback에서 `AssertionError: 1 != 143`을 확인. 별도 checkout 인프라 줄로 실제 merge SHA를 구분 | wrapper stderr나 실제 예외가 여기에 없으므로 EPERM, process race, 신호 준비 순서 중 원인을 확정하지 않음 |
| [현재 main run 37134025697](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37134025697), head `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` | 2026-10-03 push run success. job metadata 33개 모두 success; offline shard 0–7 및 shared checks/필수 aggregator가 실제 success이고 skipped가 아님 | 연구/물리 artifact 내용을 읽거나 개별 test 결과를 별도로 검증한 것은 아님. 그날 한 정상 CI가 모든 간헐 조건의 부재를 입증하지 않음 |
| 최근 main push 8개 목록 | 조회한 8개 run-level conclusion은 모두 success | 과거 전체 CI 실패율, PR별 성공률, 8회 모두 동일 환경·동일 test case였다는 독립 증거로 계산하지 않음 |

`ci-currentness-metadata.json` (Mac 전달본 증거)에 조회 시점·source SHA·job/step 결과를 보존했다. 전체 작업 로그를 분석하지 않고 원래 실패 job에서 해당 세션 테스트 traceback 구간만 선택해 `ci-original-assertion-excerpt.txt` (Mac 전달본 증거)로 저장했다. `ci-checkout-excerpt.txt` (Mac 전달본 증거)는 PR의 API head와 실제 test checkout을 구별하는 세 줄뿐이다. 실패 checkout `630ef9fe0e302f1a6878d83a6971fcc5145e8735`와 [성공 push](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/34330496329)의 head `4bad601ee05f86def034a2f4da686fcd010a4cad`에서 workflow, CI runner, session wrapper, 해당 test 파일 네 개는 바이트 동일했다. 전체 dependency·host timing까지 같았다고 확장하지 않는다. JUnit·실험 outcome·영상·upload artifact는 열지 않았다.

## 테스트는 현재 workflow에서도 선택된다

현재 `.github/workflows/tests.yml:117–148`은 Ubuntu/Python 3.12에서 `run_ci_tests.py --shard-count 8`을 호출한다. `scripts/run_ci_tests.py:310`의 명시된 test patterns에 `tests/test_ugrp_session.py`가 있고, `collect_test_files → shard_test_files → validate_shards → pytest`가 missing/duplicate 없이 분배한다(`430–486,506–556`). 이번에 이 runner나 pytest를 실행하지 않고 source를 읽었다.

현재 `test_wrapper_signal_cleans_up_child_process_group`는 임시 session 디렉터리에 wrapper와 child/grandchild를 만들고, 기록·PID 파일이 생기면 SIGTERM을 보낸다. 반환 143 이후 group·grandchild 소멸과 session 파일 제거를 검사한다(`tests/test_ugrp_session.py:39–64`). 이 method의 AST는 원래 실제 실패 checkout과 현재 main에서 동일하다. 현재 setup은 추가된 disk guard를 위해 `UGRP_MIN_FREE_GIB=0`을 사용하므로 테스트 환경 전체가 동일하다는 뜻은 아니다.

현재 workflow에는 docs-only에서 full suite를 건너뛰는 별도 routing과 aggregator가 있다. 따라서 문서 PR의 녹색 check만으로 이 테스트의 실행/통과를 추정하지 않는다. 위 현재성 확인은 모든 offline shard가 실제 success인 main push를 선택했다. CI status는 원인 진단과 별개다.

## 남아 있는 진단 한계와 수정의 의미

현재 테스트도 `wrapper.wait()` 반환값을 먼저 assert하고, 그 다음에 `wrapper.communicate()`를 호출한다. returncode가 1인 바로 그 경로에서는 assert로 중단되어 캡처한 stderr를 오류 메시지에 넣지 않는다. 이는 이슈가 이미 지적한 진단 한계가 source상 남아 있다는 확인이다. 새로운 cleanup 구현 결함으로 세지 않는다. 옆의 SIGINT 테스트는 `communicate()` 결과를 `(out, err)`로 assert에 붙이지만 이 별도 테스트의 로그가 과거 SIGTERM 실패 원인을 보완하지는 않는다.

`cc7aca7a`의 cleanup 변경은 기존 직접 `os.killpg`를 `signal_group`으로 감싸 `PermissionError`와 `ProcessLookupError`를 처리한다. 현재 main에도 그 변경이 있다. 이전부터 신호를 받고 child cleanup을 기다리는 방식도 바뀌었으므로 현재 소스는 원래 failure checkout과 동일하지 않다. 그러나 원래 traceback에 wrapper 예외가 없으므로 **이 수정이 #6의 원인을 고쳤다고 연결할 수 없다**. `ci-source-manifest.json` (Mac 전달본 증거)에 원래 reported head/actual checkout, current, cleanup change 네 pin을 따로 보존했다.

다시 같은 현상이 관측될 때 가치 있는 최소 증거는 해당 wrapper의 종료코드와 stderr, session/child/grandchild identity, ready→signal→exit→cleanup 시각이다. 같은 소유 프로세스의 유한한 정리 및 session 파일 소멸을 함께 남기면 원인을 좁힐 수 있다. 이것은 미래 검증 기준이며 이번에 테스트나 구현을 바꾸거나 반복 실행을 예약한 것이 아니다. 무작정 전체 CI를 다시 돌려 녹색만 얻는 것으로 이슈를 닫지 않는다.

R12의 LLM worker constructor cleanup 반례나 다른 runtime의 leak은 별도 caller이며 #6의 원인으로 합치지 않는다. 현재 증거 기준으로는 추가 broad CI 감사보다 이 한 진단 연결이 필요하다. 새 실패·수정이 나오기 전에는 **현재 suite 선택 확인 / 최근 main 정상 / 역사적 원인 미확인**으로 남긴다. [독립 QA](validation.md#ci-source-and-status)는 네 pin의 16개 source hash·target AST와 공식 현재 issue/run/job/PR 정보를 대조해 이 한정 결론에 동의했다. CI 실행이나 원래 실패 원인의 독립 재현은 하지 않았다.
