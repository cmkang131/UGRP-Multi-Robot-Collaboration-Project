# #335 Batch I 수정 기록 — 2026-10-01

독립 검토 `e24cb9ce3c10236efe03a1b66c9ec7671ece71b9`의 #335 지적
**I-335-1/P1**을 한 묶음으로 수정했다. 검토 대상은
`e9665534782811870482086768d2c88d681fd865`였으며 시작 시 main
`26bfcf8e2977e85132845d7704fe1070f277dd13`을 병합한
`cfe416300f2fe5e83a5e283ddad5a0371fa83b0d` 위에서 검사했다.

## 문제와 수정

`CanSkill._arm_to`는 공용 guard가 생성한 60 PWM 경로를 검사한 뒤
실제로는 관절마다 40 PWM만 움직였다. 짧은 잔여량의 관절이 먼저 목표에
도달하므로 두 경로는 달랐다. 기존 반례를 현재 checkout에서 먼저 실행해
**1 failed, AssertionError**를 재현했다. 정적 여유는 시작 +2.757 mm,
기존 검사 경로 +0.933 mm인데 발행 자세는 −0.389 mm였다.

수정은 다음 40 PWM 명령을 먼저 한 번 계산하고, 그 자세까지의 동시 전이를
검사한 뒤 **검사한 값 그대로** 발행한다. 매 tick 현재 발행 이력에서 다시
검사하며 그리퍼·pan·팔의 양방향 이동과 작은 잔여량에도 같은 규칙을 쓴다.
전이 시작·중간·끝을 기존 guard로 검사하고 loaded 여부도 그대로 전달한다.
최종 목표까지 전 구간을 미리 통과시킨다는 뜻은 아니다. 다음 증분이 막히면
그 자리에서 `failed/static_arm_sweep_blocked`와 `hold`를 반환한다.

수정 뒤 원래 반례는 새 팔 명령 없이 `hold`만 반환하여 시작 자세의
+2.757 mm 여유를 유지했다. 정적 post를 뺀 대조에서는 기존 40 PWM 명령을
정상 발행한다. 이 수치는 정적 기하 검사이며 실제 충돌·접촉 측정이 아니다.
봉인된 `zone_own_guards.py`와 `zone_own_guards_v3.py`는 바꾸지 않았다.

## 회귀와 변이 검사

- 검토 브랜치 `tests/test_review_e2e_batch_i.py` 중 #335 반례만 가져왔다.
  장애물·초기 PWM·최종 안전 assertion을 유지하고 xfail을 제거했다.
  과거 SHA 추출 대신 현재 checkout을 직접 검사하도록 바꿨다. #330 반례는
  이 수정의 범위가 아니다. Git 이력이나 `/private/tmp` 추출 디렉터리가 필요 없다.
- 양방향·서로 다른 잔여량·loaded/unloaded·여러 tick의 발행/검사 일치,
  양 끝은 허용되지만 중간이 막힌 전이 거절, post 없는 정상 대조를 추가했다.
  새 반례와 전이 검사 **11개 통과**.
- 기존 인식·들기·방출·자기 카메라 경계 제거 4종과, 잘못된 전체 목표 검사
  복원·팔 안전 검사 제거·중간 검사 제거 3종의 **7/7 변이 검출**.
  모두 행동 assertion으로 실패했고 import/collection/setup 오류는 없었다.
  변이는 자식 Python 메모리에서만 적용했다.
- `scripts/run_ci_tests.py`의 기존 목록에 승격한 반례를 추가했다.
  수집·shard·집계 검사 **66개 통과**. `.github/workflows`는 수정하지 않았다.
- 전체 관련 회귀는 **245 passed, 1 deselected, 107 subtests passed**다.
  물리 host 검사 1개는 명시적으로 제외했다. 등록 소스 22개·source pinning
  34개가 모두 통과했고 금지 import·네트워크 시도는 0회였다. 봉인·기존 의존
  파일 122개가 병합 직후와 바이트 동일하며 필수 두 검사와 `tests.yml`도
  origin/main과 같다. 전체 결과와 파일 해시는
  [review_i_fixes_verification.json](review_i_fixes_verification.json)에 기록한다.
  기존 검토/검증/의존성 기록은 당시 자료로 보존한다.

## 경계와 남은 일

런타임 입력은 기존 자기 JPEG·정적 지도·자기 발행 명령으로 동일하다.
GT·측정 관절·심판·다른 로봇 입력이나 새 통신 통로를 추가하지 않았다.
네 통신 조건의 controller/profile은 동일하다. 단위검사에서 쓴 자세와 그림은
합성 fixture이며 실제 위치 추정이나 can 성공의 증거가 아니다.

물리·렌더·학습·모델·네트워크 호출 없이 로컬 offline 검사를 실행했고 host lock을
사용하지 않았다. 작은 물리 인수 재생도 이번 요청의 **No physics** 범위에 따라
실행하지 않았다. 실제 rim 가시성·파지·방출, can navigation·새 workflow/번들,
s6 T11은 [PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)의 별도 인수 범위로 남는다.
단위 회귀를 새 실험 성과로 TensorBoard에 변환하지 않았다.

로그는 `/Users/changmin/projects/ugrp/outputs/cap-t04-can/review-i-fixes-20261001/`에
로컬 보관한다. 커밋한 소형 요약/해시와 raw 원격 백업은 구분하며 Drive는 쓰지 않는다.
이번 수정에서 `/private/tmp` 추출 디렉터리를 만들지 않았다.
일반 PR CI를 실행하도록 정상 push하며 **PR #335는 draft로 유지하고 병합하지 않는다**.
