# VIS5 작업·범위 기록

- 작업 브랜치 `codex/vision-loc-v5`, 시작 SHA `137ba742493b1f09c68238525cfc44a57054ae48`.
- 이슈 #216의 최신 [VIS5 코디네이터 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5855928447)을 connector로 확인했다. 관련 열린 PR은 VIS4 #242, 통합 #229다. VIS5는 실험 디렉터리의 opt-in 보고 계층에 한정하며 worker/통합 러너를 바꾸지 않는다.
- `git fetch origin`은 공용 Git 메타데이터의 `FETCH_HEAD` 쓰기가 sandbox에서 거부됐다. `gh` 네트워크 연결도 실패하여 공식 저장소 이름 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`의 connector로 이슈와 열린 PR을 읽었다. origin URL·main·다른 worktree는 바꾸지 않았다.
- primary main은 로컬 origin/main보다 315 커밋 뒤라고 표시됐다. 원격 fetch 완료 상태를 뜻하지 않는다. primary는 쓰기 허용 범위 밖이며 이번 작업은 커밋 금지이므로 갱신·커밋·push·PR·병합을 하지 않는다.
- 후보·fit/validation·선택 규칙은 `dev_plan_v5.json`에 **관측 feature 추출·GT 적합·후보 비교 전에** 고정했다. SHA256 `c81f4977ebb72e8f0c3109b93e2f4235df826e8d5c2ab5c360e98dbe2f4cb217`.
- 기존 학생 추정에 적용하는 보고 계층의 shadow 비교를 선택했다. yaw 보정은 현재 관측이 적용된 프레임에서만 수행하며 다음 PF 예측에는 되먹임하지 않는다. 이 선택은 물리/새 렌더 금지 범위에서 보고 계층을 동일한 저장 자료로 검증하기 위한 것이며 새로운 PF 전체 궤적·폐루프 개선의 증거가 아니다.
- VISW 원본 inventory에 분할 관측 캐시·분할 마스크·pre-resampling ESS가 없다. `n_eff`는 재표본화 후 값이어서 대신 사용하지 않는다. 새 추론 예산을 0으로 정하고, VISW는 baseline/s1 yaw 보정 fit 진단에만 포함한다. y1/y2/m1의 VISW 결과를 만들어내지 않는다.
- 모드 소실에 대한 첫 후보는 σ 팽창이다. 재초기화는 이번 유한 후보에 넣지 않았다. 앞선 대칭 지도 재초기화 실패와 혼동하지 않으며, 보고 불확실성 증가를 실제 위치 회복으로 부르지 않는다.
- 소스 동결 전 합성 검사에서 명령 필드 `pulses`, 최소 관측 열 수, 보정 테이블 fixture 오류를 수정했다. 활성 런타임 검사는 PF 적분 시각의 부동소수점 끝점 오차로 새 관측을 놓치는 문제를 찾았고 1e-8 s 비교 허용차로 수정했다. 단순 판정 임계값 조정이나 후보 추가가 아니다.
- 첫 추출은 9회 모두 완료했지만 비교는 fit 결과 생성 전에 `different report at the same timestamp`로 중단됐다. 교사 dev 495쌍·VISW 41쌍의 연속 프레임이 같은 SIM 시각을 가진다. 모두 유지하고 dt=0·last_scan 불변이면 새 근거로 집계하지 않도록 수정했다. 최초 산출물을 그대로 보존하고 `outputs/vision-loc-v5/final/`에 추출부터 전체 재실행한다. 사전 계획·후보·격자·선택 규칙은 변경하지 않았다.
- 물리 step·새 렌더·새 모델 추론·LLM 호출은 하지 않는다. pytest는 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행하고 finally에서 임시 폴더를 제거한다. 실행 로그는 `outputs/vision-loc-v5-checks/`에 보존한다.
- TensorBoard 공용 view 설정은 읽었다. `/bin/ps`가 sandbox에서 거부되어 서버 PID·소유권 확인은 불가능하다. primary 공용 root도 쓰기 허용 범위 밖이다. 이번 local native snapshot은 실제 event 재로딩으로 검증하며 공용 등록·화면 표시는 미완료로 명시한다. 기존 서버·다른 작업의 프로세스는 변경하지 않는다.
- 프로젝트 예외에 따라 Google Drive는 사용하지 않는다. 기존 raw·스냅샷·실험 기록을 보존한다.

## PR #243 P2 후속 수정 — 2026-09-27

- 검토 파일 `codex-243-review1.md`(검토 세션 `01a0e301-e1f1-76d3-9544-7c8768fbd484`)와
  로컬/원격 PR HEAD `5cc83adbcbaab80191a84f592a88139d89ebe7a9`를 확인했다.
  `HEAD`를 이전 소스로 읽는 테스트는 커밋 후 자기 비교가 된다. 런타임 결함 수정이 아니라
  기본 OFF 불변을 지속적으로 검증하기 위한 테스트 수정이다.
- `git fetch origin`은 공용 `FETCH_HEAD` 쓰기 권한으로, `gh pr list`는 네트워크로 실패했다.
  GitHub connector의 PR 정보·열린 PR 목록으로 #243 및 관련 #242를 읽었다. primary는 로컬
  `origin/main`보다 341커밋 뒤였으며 원격 최신 fetch 완료로 해석하지 않았다. primary·Git 메타데이터는 수정하지 않았다.
- VIS4 `137ba742`의 `vision_pf.py`(18,596 bytes)와 기존 M1 고정 소스(21,097 bytes)를
  `tests/fixtures/vision_loc_v5_off/`에 바이트 그대로 보존했다. 출처·전체 SHA·SHA-256은
  fixture README에 있다. 실행 시 Git 없이 읽고 해시를 검사하며, 파일 누락·변조는 실패한다.
  M1의 공통 runtime 해시 검사도 유지했다. PF·보고 계층·선택 설정 소스는 변경하지 않았다.
- 기본값 생략과 명시적 OFF 각각에서 기존 보고값 전체·입자·가중치·RNG를 대조한다.
  현재 PF의 x 보고만 +1 m 변경하는 음성 테스트 2개와 fixture 누락/변조 검사 4개를 추가했다.
  정상 회귀검사는 subprocess 실행 자체를 금지하여 Git 의존성이 다시 들어오면 실패한다.
- 최종 VIS5 suite: **38 passed, 0 skipped (0.65 s)**.
  명령: `OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_vision_loc_v5.py --basetemp=./.pytest_tmp`.
  로그: `outputs/vision-loc-v5-p2-checks/pytest-vis5.log`.
- Git 메타데이터·객체·outputs·모델이 없는 최소 소스 복사본에서도 **38 passed, 0 skipped
  (0.65 s)**. 첫 복사본은 `harness`의 import에 필요한 `scripts/robot_actions.py`를 빠뜨려
  collection 오류 1개였다. 의존성을 복사하고 sparse 필요 경로에 기록한 뒤 재실행했다.
  실패/재실행 로그는 각각 `pytest-source-only.log`, `pytest-source-only-fixed.log`에 보존했다.
- 정상 OFF 회귀검사에 별도로 메모리 내 +1 m 변이를 적용하자 **예상대로 2 failed,
  36 deselected (0.13 s), pytest 종료 코드 1**이었다. 둘 다 `VIS4 report mismatch at t=0.1`로
  실패했고, 변이는 프로세스 안에서만 적용했다. 로그: `pytest-injected-plus-one-metre.log`.
  위 통과 수와 합산하지 않는다.
- 모든 pytest 실행에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 사용했다.
  각 실행 종료 후 `.pytest_tmp`와 임시 소스 복사본을 삭제했다. 물리 step·렌더·모델 호출은 0이며
  사용자 허용에 따라 잠금 없이 실행했다. 새 연구 실험/평가 결과는 없어 TensorBoard 재변환·재기동은 하지 않았다.
- README 끝에 **다음 방향(검토 제안, 미결정)** 절을 추가했다. 정상 추적과 실패 감지·복구의
  차이, 코호트/test 오염 한계, 세 제안의 근거와 검토가 인용한 두 논문을 기록했다.
  CMU·arXiv 원문 페이지로 서지와 해당 주제를 확인했으며 새 연구 방향을 채택하지 않았다.
- 사용자 지시에 따라 커밋·push·PR 수정·병합은 하지 않았다. 기존 raw·결과·모델·사전 계획은 그대로다.
