# PR #344 수정 확인 — MERGE

대상은 `b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a` →
**`747d2b9f1eb43e21804ccef58fff4db241d1a844`**,
수정 커밋 `46330db9`, `2e53b58e`, `747d2b9f`다.
독립 검토자 Codex가 원격 브랜치를 fetch한 뒤 별도 `git archive`에서 검사했다.
이전 검토는 `17b54de7`, `26534b12`다. 구현 브랜치는 수정하지 않았다.

**판정: MERGE — 요청된 변경 범위에 미해결 P1/P2 없음.**
PHYSICS_HANDOFF.md와 PR 댓글의 조정 결정 1–2를 적용 기준으로 삼았다.
결정 2가 이전 B1의 전체 경로 증명·큰 원의 사전 차단 요구를 대체한다.
시뮬레이션 교사 수집의 참고 범위와 필수 인터록이라는 결정을 재심사하지 않았다.
이 판정은 코드 수정 확인이며, 진행 중인 물리 수집·하중 유지·적합·P03/E2E 인수가 아니다.
리뷰 역할에 따라 draft를 바꾸거나 PR을 병합하지 않았다.

| 확인 대상 | 직접 확인한 결과 |
|---|---|
| B1의 기존 3개 기대실패 | 결정 2에 맞는 3개 필수 통과 검사로 변경됐다. 원래의 사전 거부 assertion이 그대로 통과한 것은 아니다. 세 정상 계획은 큰 참고 범위에도 실행 가능하고 가짜 backend에 도달한다. 원의 크기로 다시 거부하도록 변이하면 3개 모두 의도한 assertion에서 실패한다. |
| B2의 기존 2개 기대실패 | 로봇2·빔 z=NaN의 원래 assertion을 유지한 채 통과한다. `b7bc885a`의 실제 guard/XY 투영 코드를 메모리에서 복원하면 2개 모두 assertion에서 실패한다. 의존성 오류를 통과로 세지 않았다. |
| 사전 차단 | `harness/zone_final_pair_clearance.py:137,154,204`: 시작 벽 거리 ≤0.70 m 및 수치 접점, loaded 빔의 반대각선+0.30 m, NaN·누락 기하를 거부한다. CLI 계획/실행·run_case·직접 생성자가 저장된 PASS를 믿지 않고 재검사한다. |
| 인터록 해제 방지 | `scripts/run_final_pair_v3.py:132`에 해제 CLI 옵션이 없다. 세 수집 × 선언 누락/해제/최소거리/버퍼/반경/substep/주기/측정 계약 변경 24개 조합에서 run_case와 직접 생성자 모두 출력·backend 시작 전에 거부했다. |
| 실행 중 차단 | `sim/final_pair_v3.py:78,86,147,191`: 수집 substep 전후, 명령 직전, 평가 호출에서 NaN을 거부한다. substep 전 오류는 0 step, 직후 오류는 가짜 1 step에서 끝나며 다음 step을 실행하지 않는다. 양쪽 hold와 중단 이유를 확인했다. |
| 부분 자료 보존 | `scripts/run_final_pair_v3.py:103,122`: 실제 guard·JSONL writer·close를 가짜 시계/형상에 연결했다. 벽/NaN/형상 누락 모두 HOST_ERROR, protocol_complete=false, PARTIAL_INVALID_HOST_ERROR, partial_data_retained=true다. 앞선 frame metadata·명령·pose·abort 파일과 전체 hash가 남고 스트림이 닫힌다. |
| 참고값 기록 | `scripts/run_final_pair_v3.py:58,165`: 무상쇄·쌍 상쇄 두 계산이 계획과 사례 결과에 들어간다. 실제 일정의 로봇별·축별 명령 적분을 독립 합산해 아래 수치와 대조했다. 쌍의 나가는 최대 이동과 PRBS 절댓값이 남으며 운반자끼리 상쇄하지 않는다. |

| 수집 | 무상쇄 반경 m | 쌍 상쇄 참고 반경 m | 계획 |
|---|---:|---:|---|
| unloaded | 8.264800 | 3.993983 | 실행 가능 |
| fine | 6.911840 | 3.551185 | 실행 가능 |
| loaded, 각 로봇 | 11.295598 | 4.960012 | 실행 가능 |
| loaded, 빔 | 11.768798 | 5.433212 | 실행 가능 |

measurement-v2 재사용도 확인했다. `rectangles`, `free_floor_area`, `clearance`,
`require_clearance`, `geometry_envelope`는 v88/v89에서 **동일 함수 객체**다.
마지막 함수는 main의 xyz·반경·계산 거리 검사를 그대로 추출했다.
v89의 전체 경로/근거 검사와 실행 차단은 유지된다. v88의 사전 운동 범위만 결정 2의 참고 계산을 쓴다.
공용 경로 계산기의 회전·여러 몸체 거부는 추가됐지만 기존 v89 두 축 일정은 바뀌지 않았다.
v89 설정·실행기·식별 계산기 등 5파일은 병합한 main `2c45b137`과 바이트가 같다.
최종 main `6a0e648e`에서도 해당 공용 소스와 설정이 그대로임을 다시 확인했다.

학생 runtime/vision/명령 일정, 카메라·렌더·모델, v88 등록·보정 계약, 봉인 소스 등
**23파일 SHA-256이 이전 후보와 같다.** 학생 GT 경계, teacher staging 분리, weld OFF,
P03/carry 실측 보정 누락 차단, reset≤5초·수집≤370초·학생 사례≤120초를 관련 검사로 확인했다.
현재 main+열린 PR 12개 고정 SHA에서 v88 선언은 #344뿐이며 v89와 번호 충돌이 없다.
workflow는 v88/3.1.0 그대로다. `.github/workflows` 변경은 없다.

검증 결과:

- 관련 17파일: 최종 **575개 통과**, 기존 sandbox `ps` 제한 검사 1개 제외.
  첫 실행의 558 통과/17 실패는 archive의 Git 이력 조회 설정 오류였다.
  읽기 전용 `git log`/`merge-base`를 후보 SHA의 이력에 연결한 뒤 영향받은 두 파일 **78개 전부 통과**.
  후보 코드는 바꾸지 않았고, 초기 실패와 재검사 결과를 모두 보존했다.
- 새 독립 검사: **40개 통과**(37+3), 이 중 다섯 수정 되돌리기는 전부 assertion 실패를 확인했다.
  관련 검사와 합쳐 고유 **615개 통과**다. 미해결 반례가 없어 새 strict xfail은 0개다.
- 같은 후보 SHA의 GitHub CI **33개 SUCCESS**. 로컬 결과와 별도 확인했다.
- 검사 종료 후 archive의 관련 소스·설정·테스트 등 **2,370개 Git blob 일치**를 확인했다.
  검토용 archive와 보조 임시 파일은 기록 보존 후 삭제·부재 확인했다.

[독립 검사](../../tests/test_review_344c.py) · [검사·초기 오류·변이·해시·ref 기록](REVIEW_344c_EVIDENCE.json).
물리·MuJoCo 모델 컴파일·렌더·모델 추론은 0회다. 병렬 수집의 outputs·잠금·프로세스에 접근하지 않았다.
새 실험 결과를 회수하지 않았으므로 TensorBoard 변환·표시 및 Drive 작업은 하지 않았다.

재현은 후보를 빈 임시 디렉터리에 `git archive`로 풀고 다음을 실행한다.

```sh
REVIEW_344C_ROOT=<candidate-archive> OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -B -m pytest \
  -q -p no:cacheprovider tests/test_review_344c.py
```

관련 suite의 안전한 이력 조회 연결과 실행 목록은 증거 JSON에 있다.
검증 뒤 자신이 만든 archive를 삭제한다.
