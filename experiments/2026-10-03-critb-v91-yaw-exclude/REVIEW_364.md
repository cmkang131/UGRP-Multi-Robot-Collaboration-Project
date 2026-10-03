# PR #364 독립 검토 — MERGE

2026-10-03, Codex 독립 검토. **수정이 필요한 P0/P1/P2 지적 없음.**
판정은 아래 SHA의 제외·범위 표시 구현에 한정한다. 실제 v91 재채점이나 두 지도 yaw 통과 판정이 아니다.

- 대상: `5b61d5b21f0107ed38a9d404ad2c2c877a42469b` (`codex/critb-v91-yaw-exclude`).
- 기준 main: `89ea80d536b3d2406848ba6e85ead4150ac06bd6`.
- 작업: `codex/review-362`, 시작 HEAD `c25be095e4b8d7215fe6eb7cd44c4752e5d904b3`.
  첫 명령으로 fetch하고 지침·열린 PR·기본 checkout의 origin/main/청결 상태를 확인했다.
  기존 #362 검토 기록을 보존하고 대상 PR을 검토 브랜치에 로컬 병합했다.
  `scripts/`, `tests/`, `harness/`, `sim/`, `configs/`, `maps/`는 대상 PR과 동일하며 작성자 구현은 수정하지 않았다.

## 1. 이미 고정된 B 제외 규칙과의 대조

근거는 `experiments/2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json:36`의
“identical recorded pose bytes are ineligible regardless of renamed paths”와
같은 폴더 `README.md:110`의 “이미 본 pose 바이트·훈련 지도는 held-out에서 제외한다”이다.
전자는 `6ed94e4c341cbca206bcd8a92d0ef64194590f60`(2026-10-01 07:29:54 KST),
후자는 `65886a7efc206f3fe42416d13a27a2ce7789a289`(2026-10-01 08:25:41 KST)에 이미 있었다.

동결 구현 `scripts/validate_consumer_criterion_b.py:287`–`:315`는 각 사례마다
`pose_sha256 in prior`를 확인하고 해당 축의 검증 판정을 null로 남긴다.
새 `scripts/validate_consumer_criterion_b_v91.py:169`도 같은 해시 소속 조건을 사용한다.
prior 구성(`:138`, `:433`)은 기존 r5·훈련 manifest·r4의 고정 해시 집합 그대로다.
이번에 corridor/door 이름, 오차, 통과 여부, 특정 실행 경로로 선택하는 규칙이나 새 prior 해시는 추가하지 않았다.

**검증 자격의 사례별 제외 의미가 같다.** 진단 출력까지 같은 것은 아니다.
원래 B는 제외 사례에도 진단 `metrics`/`numerical_pass`를 계산하지만 `pass=null`로 남긴다.
이번 yaw는 요청된 대로 그 계산을 생략해 `metrics=null`이고 `numerical_pass`도 없다.
독립 합성 검사에서 이 차이와 검증 판정의 일치를 직접 확인했다.
수정 자체는 첫 채점 뒤에 이루어졌으나, 제외 근거와 집합은 그 전에 고정돼 있었다.

## 2. 사례·지도 범위와 강제 거부

`scripts/validate_consumer_criterion_b_v91.py:154`–`:162`는 빈 입력·지도 중복·훈련 여부·
허용 지도·dt=0.05를 먼저 검사한다. prior에 있는 사례라도 이 검사는 예외로 실패하며,
호출 경로 `:437`–`:438`에서 yaw 전체 `INELIGIBLE`이 된다.

`:165`–`:185`에서 제외 사례는 `PREVIOUSLY_SEEN_POSE_BYTES`, `pass=null`, `metrics=null`,
pose 해시를 남긴다. `maps_observed`와 실제 계산한 `maps_scored`를 구별하고,
누락·제외·지원 부족은 `maps_not_scored`에 포함한다. 계산하지 않은 지도가 있으면 `PARTIAL_MAPS`다.
CLI가 출력하는 결합 요약에도 `:459`–`:461`의 동일 범위·지도 목록이 들어간다.

| 합성 사례 | 검증 결과 |
|---|---|
| 한 지도 제외, 다른 지도 통과 | `PARTIAL_MAPS`, 제외 지도 명시, 전체 null |
| 한 지도 제외, 다른 지도 실패 | `PARTIAL_MAPS`, 실패를 유지해 전체 false |
| 두 지도 모두 제외 | `maps_scored=[]`, 두 지도 미채점 명시, 전체 null |
| 지도 누락 또는 yaw 지원 없음 | 미채점 지도 명시; 관측한 실패가 없으면 null |
| prior 여부와 함께 training/훈련 지도/미등록 지도/dt/지도 중복 오류 | 계산 전 강제 거부 |

두 지도가 제공됐다는 사실을 두 지도 모두 채점·통과했다는 뜻으로 사용하지 않는다.
숫자 입력 자체가 없는 제외 사례와 새 실패 사례를 섞은 독립 반례에서도 제외 사례는 계산하지 않고
새 실패는 유지했다. 좋은 오차만 남기는 선택이 아니다.

## 3. forward/left·동결 파일·yaw 기준 보존

실제 기준 커밋 `89ea80d5`의 검증기를 `git show`로 읽어 별도 모듈로 실행했다.
forward/left 각각 통과·실패·지원 누락·prior·훈련의 10개 합성 상태에서 보고서 JSON 직렬화
바이트가 같았다. 두 지도 합성 raw에서도 제외 없음/첫 지도/둘째 지도/전부 제외의 네 조건에 대해
기준·변경 검증기의 옵션 OFF/ON을 대조했다. 새 yaw 필드 둘을 분리한 **기존 전체 B 보고서가
바이트 동일**했다. 실제 held-out 보고서의 재생·열람으로 확인한 것은 아니다.

[보존 검사](review_364_static.json)는 작성자가 기록한 66개 파일 각각을
기준 Git blob·대상 Git blob·검토 작업 파일·등록 SHA-256과 교차 대조했다.
B/r4/r5/부록/manifest/약속·기존 기록이 모두 같다. 검증기 함수 15개도 바이트 동일하며,
변경 함수는 `score_rotation`, `validate`뿐이다. `validate`는 yaw 요약 필드 세 개 추가만 다르다.
PR 전체 변경 목록에도 동결 파일 변경은 없다.

yaw는 `scripts/validate_consumer_criterion_b_v91.py:172`의 기존
`frozen.evaluate_axis(case, 2, profile, gate)`를 그대로 호출한다.
0.2/0.5/1/2/3/3.2초, 계단·PRBS, 세 성분, `p95(abs(error)/sigma) <= 2`,
`coverage_2sigma >= 0.90`, 실패 우선 집계와 후보 미승격 상태를 유지한다.
남은 지도 수치는 동결 evaluator 직접 호출과 같음을 합성 검사했다.

## 4. 합성 검사

**321 passed in 71.73s**: 관련 기존 회귀 305개 + 이번 독립 검사 16개.
작성자 로그를 이 실행 횟수에 합산하지 않았다. 실패·오류·skip은 0개다.
Python 3.12.13, NumPy 2.5.2, SciPy 1.17.1의 기존 Mac 환경을 사용했다.

- `tests/test_consumer_criterion_b_v91_yaw.py:152`: 어느 지도든 제외 가능, 남은 지도 통과/실패와 동결 수치 일치.
- 같은 파일 `:185`, `:199`: 전부 제외 및 prior로 가릴 수 없는 강제 거부.
- 같은 파일 `:338`, `:362`: manifest prior 및 임시 pose 파일을 실제 바이트 복제한 중복, CLI의 범위·지도·종료 코드 2.
- [독립 검사](review_364_checks.py): 실제 base와의 출력 동일성, B 제외 의미 대조, 제외 사례 수치 미접근 및 새 실패 유지.

[로그](review_364_tests.txt), [JUnit](review_364_tests.xml),
[환경·정확한 실행 명령·증거 해시](review_364_evidence.json)를 남긴다.
검사에는 실제 outputs 파일 열기, 물리/모델 import 및 네트워크 연결을 거부하는
[접근 가드](review_364_safety/sitecustomize.py)를 적용했다.

## 5. 결정론 기록과 후속 설계

README의 발견 경위는 [코디네이터 댓글 5966536405](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966536405)와 일치한다.
허용된 여섯 pose 파일(v88 훈련 r1/r2와 v91 두 지도 r1/r2)의 **크기·스트리밍 SHA-256만**
별도 대조했다. [독립 identity 기록](review_364_identity.json):

- door r1: 훈련과 동일, `7eea9447212e3de1ffea9a61876e3234c2d348bc38de7962cca0cc169b86b216`.
- door r2: 훈련과 동일, `d38c0eccffc035258b46144278f73d092593594f83655e69fb6d83a6f2c5a79e`.
- corridor r1/r2: 각각 훈련 파일과 다름. 다르다는 해시만으로 독립성·일반화·성공을 입증하지 않는다.

같은 시작 자세·벽 비접촉이 원인이라는 설명은 README `:19`–`:20`에서도
코디네이터 관찰로 귀속한다. 이번 검토는 pose 행이나 접촉을 열지 않았으므로 그 인과관계를 독립 재현했다고 하지 않는다.
첫 실행의 forward/left PASS·yaw INELIGIBLE도 코디네이터 보고이며 실제 결과 파일은 열지 않았다.

README `:26`–`:30`은 v92를 포함한 다음 수집에서 지도 이름만 바꾸지 말고 시작 자세·
명령 궤적을 다르게 설계하고, 수집 전 기존 훈련 해시와 예정 조건으로 중복 가능성을 점검하며,
수집 후 채점 전에 실제 파일 해시를 다시 확인하도록 구체적으로 구분한다.
아직 생성되지 않은 pose의 실제 해시를 수집 전에 알 수 있다고 주장하지 않는다.
이는 다음 설계 지침이며 현재 corridor 결과를 새 확증 코호트로 승격하는 근거가 아니다.

## 남은 절차와 검토 경계

- 실제 v91 pose 행·명령·카메라 자료와 채점 결과 파일은 미열람. 실제 validator 실행·재채점 0회.
- 물리·렌더·모델 호출·기존 프로세스 조작 0회. 공유 잠금·서버·Drive는 사용하지 않았다.
- 같은 head는 GitHub `MERGEABLE`이다. 저장한 [CI 조회](review_364_github.json)에서는 23개 성공,
  9개 실행 중이며 required check 전체 완료는 아직 확인되지 않았다. **코드 검토 판정 MERGE**와 실제 병합 준비 완료는 구분한다.
- 실제 PR 병합과 검토 뒤 한 번의 v91 재채점, 결과·TensorBoard 등록은 코디네이터에게 남긴다.
  이번 합성 코드 검증은 새 실험 결과가 아니므로 TensorBoard 변환·뷰어를 실행하지 않았다.
- 이전 #362 검토 파일은 그대로 보존했다. 대상 head가 바뀌면 변경 범위를 다시 검토해야 한다.
