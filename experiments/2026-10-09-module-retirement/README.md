# 2026-10-09 미사용 모듈 퇴역 감사

요청 범위: main에서 현재 사용하지 않는 Python 소스를 제거하고 Draft PR만 연다. 시뮬레이션·모델 호출·물리 실행 0회. `outputs/`, `maps/`, `sim/assets/` 및 실험 결과 원본은 변경하지 않았다. Google Drive·TensorBoard 변환은 이 코드 감사의 대상이 아니다.

## 기준과 결과

- main/기본 체크아웃: `888447674318bc311e1ef65f71c654692b2b76bb` (시작 시 깨끗함). 원격 `origin`을 확인하고 fetch했다. 작업 브랜치는 `codex/repo-cleanup`.
- 실제 Git 추적 Python 분모는 harness/sim/scripts **1068개**다(전달받은 1012개보다 56개 많음). 퇴역 **87**, 보류 **14**, 유지 **967**. 전용 시험 **2개** 별도 삭제, 합계 **10,211줄** 제거. 파일별 마지막 변경 SHA·참조·재현 방법: [퇴역 표](../../docs/retired_modules.md), [기계 판독 목록](retirement.json).
- 실험 README **25개**에 퇴역 전 전체 소스 커밋을 추가했다. 결과/실행 SHA는 기존 기록을 보존한다. 이 메모는 과거 결과를 다시 실행했다는 뜻이 아니다.
- workflow는 기본 41항목+조각 18항목 **59개 유지**, 퇴역 0. 모든 runner가 현재 보호 집합(안내 명령·열린 PR·고정 의존성·유지 시험) 안에 있어 삭제 확신이 없다. 고정 bundle JSON·그 시험도 그대로다. 퇴역 파일을 직접 고정한 현재 config JSON은 **0개**였다([검사](configuration_references.json)).
- 실물 depth-provider 계약과 보정/기하 도구, 보존하는 과거 실행 Python이 호출하는 파일은 보류했다. 지도·자산은 [범위 밖 목록](out_of_scope.txt)만 저장했다.
- AGENTS.md에 새 버전 채택 시 이전 버전을 같은 PR 또는 다음 정리 PR에서 퇴역·기록하는 한 줄을 추가했다.

## 그래프 방법과 경계

`audit.py`는 Git 객체를 읽고 AST `Import`/`ImportFrom`과 상대 import·별칭, importlib 상수/테이블, 완전한 문자열 모듈 경로, `python -m` 대상, pathlib `/`·joinpath를 해석한다. 모듈 이름의 부분 문자열 검색으로 후보를 정하지 않는다. 현재 docs의 정확한 경로 언급도 보수적으로 시작점에 넣었다. CI 목록은 실행 결과 선택이므로 그 자체가 모든 과거 시험을 살리는 시작점이 되지는 않는다. 시험의 직접 대상 중 유지 모듈이 있으면 그 시험과 전이 의존성 전체를 살린다.

[PR 스냅샷](prs.json)의 열린 10개 PR 및 S3 v107/v108·S4·sim-speed 브랜치를 고정 SHA로 읽었다. S2 v140, 자기 지도 run_teach_capture/run_own_map_return_repeat, ownmap-s2의 변경 Python·설정·실행 명령 및 전이 의존성을 보존했다. 최종 재조회 때 새로 열린 #416 S3 no-prior 브랜치도 추가했으며 삭제 대상 의존성 0개를 확인했다. 요청의 `codex/sim-speed`는 실제 원격/작업 경로인 `codex/sim-speed-egomap53`로 확인했다. main과의 merge-base부터 브랜치에서 변경한 소스를 시작점으로 계산했고, 변경하지 않은 공통 과거 시험 전체를 무조건 루트로 삼지는 않았다. 삭제 후 가상 병합 결과의 모든 잔존 Python을 다시 검사한다.

[시작점/분류/미해결 동적 호출](inventory.json), [AST 간선](edges.json). 외부 입력·사용자가 지정한 임의 모듈·체크포인트 pickle 테이블은 정적으로 모든 값을 결정할 수 없다. 설정의 모듈 경로와 loader의 상수 테이블은 추적했으며 미해결 호출을 숨기지 않았다. 단순 이름 일치만으로 삭제 안전성을 주장하지 않는다.

재생: 이 정리 PR checkout에서 `python3 experiments/2026-10-09-module-retirement/audit.py`. 삭제 전 소스는 별도 복제본에서 위 main SHA를 checkout해 복구한다. 감사기는 삭제·시뮬레이션을 실행하지 않는다.

## 검증

- 감사기의 상대 import/동적 import/경로 조합/`-m`/이름 부분 문자열 반례 + CI shard + workflow manager: **92 passed**, 동시 pytest **1개**. 정확한 명령은 [validation.json](validation.json).
- 잔존 AST 간선의 삭제 대상 참조 **0**. `scripts/run_ci_tests.py --shard-count 8 --list-shards`에 지운 시험 **0**. 두 시험은 원래 명시 항목이 아닌 glob으로 선택되므로 선택 코드·시간 사전 수정은 필요하지 않았다([확장 목록](ci-shards.json)).
- 기존 MuJoCo 환경의 실제 `python -c` 일괄 import **962/981 통과**. 실패/차단 **19개**는 삭제 전 main과 [결과가 바이트 동일](imports-baseline.jsonl)했다. torch/draccus/stable_baselines3 없는 별도 환경과 import 시 CLI/출력 작업을 시작하는 기존 모듈이다. subprocess/네트워크/물리/outputs 접근 차단을 둔 import 감사이며 전 모듈 무조건 성공으로 표현하지 않는다. [삭제 후](imports.jsonl), [검사 코드](check_imports.py).
- 기존 reference-ACT 환경에서도 선택 의존성 실패 12개를 추가 확인했다([기록](imports-reference-act.jsonl)): 2개 통과, 10개 미통과. import 중 라이브러리 캐시 쓰기를 차단한 뒤 일부 Torch 초기화가 연쇄 실패했고 stable_baselines3도 없다. 이 제한된 재시도를 독립적인 제품 회귀나 추가 통과로 합산하지 않는다. 환경 설치·모델 로딩·학습은 하지 않았다.
- merge-tree 검증은 `check_merges.py <후보 SHA>`로 각 PR 및 명시 경로 브랜치를 가상 병합한다. 체크아웃/브랜치는 바꾸지 않으며, main과 병합해도 있던 충돌과 정리 때문에 새로 생기는 충돌을 구분한다. 충돌 Python은 양쪽 원본을 각각 AST 검사한다. 후보 `c1bf70795c84c46961a47d20a13f8e9dd0589fa9`에서 **13개 브랜치(열린 PR 10개+추가 경로 3개) 모두 삭제 파일 import/호출 0, 삭제 파일 재등장 0, 새 충돌 0, AST 구문 오류 0**. 기존 main 병합에서도 충돌하던 9개 브랜치는 같은 충돌 경로만 남았다([merge_checks.json](merge_checks.json)). 뒤의 기록 커밋은 코드·시험을 바꾸지 않는다.
- CI는 Draft PR 생성 후 원격에서 실행하며 기다리지 않는다. 병합하지 않는다. 전체 import 성공 조건은 위 환경/CLI 경계 때문에 미충족이다.

## 조사 자료

표준 방법은 도달 가능한 시작점의 전이 폐쇄와 삭제 후 참조 검증이다. 새 정적 분석 프레임워크를 도입하지 않고 Python의 AST와 Git의 가상 병합을 사용했다. 프로젝트에 이미 있는 `harness/python_source_closure_v2.py`도 읽고 상대 import·패키지 초기화·동적 loader 경계를 확인했다.

- [Python AST 공식 문서](https://docs.python.org/3/library/ast.html): 소스를 실행하지 않는 구문 분석과 Import/ImportFrom/Constant 노드.
- [Python importlib 공식 문서](https://docs.python.org/3/library/importlib.html): 문자열 기반 모듈 로딩과 상대 import.
- [Git merge-tree 공식 문서](https://git-scm.com/docs/git-merge-tree): worktree/index를 바꾸지 않는 실제 merge 계산과 충돌 출력.

새 알고리즘이나 최신 논문이 필요한 문제라는 근거가 없어 표준 도구를 사용했다. 미확인 논문 인용은 없다.

## 제출

[Draft PR #417](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/417), 제목 `cleanup: 쓰지 않는 모듈 퇴역`. 최초 게시 HEAD `ffd62d89258c041764bd6014714a9cbb72bb703d`의 로컬·원격·PR SHA 일치와 OPEN/DRAFT 상태를 확인했다. 이 게시 기록의 후속 커밋은 문서만 바꾸며 검증한 코드/시험은 그대로다. 병합·자동 병합 예약·CI 대기는 하지 않았다.
