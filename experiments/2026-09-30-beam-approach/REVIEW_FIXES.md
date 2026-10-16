# T08b H333-1 수정·오프라인 검증 — 2026-10-01

독립 검토 `d17327aeacf858108179ebbad2a85d0a9e357608`의 **#333 지적 전체**를
한 묶음으로 수정했다. 검토 대상은 `cb0735efcd79ebaefd511eb7cd123979512dd0ed`였다.
물리·SIM step·렌더·모델 호출은 0회이며 호스트 잠금은 사용하지 않았다.
PR #333은 draft로 유지하고 병합하지 않는다.

## 원인과 수정

기존 코드는 실제 발행 PWM 대신 0–1000 단위를 요구하고, 비활성 channel 2까지
필수로 삼았다. 표준 `SEARCH_POSE={1:2000,3:740,4:2320,5:1320,6:1500}`를 그대로
넣은 독립 반례를 수정 전 실행해 `BAD_ISSUED_SERVO` 실패를 재현했다.
양성 fixture도 잘못된 단위를 사용하여 이 문제를 가렸다.

- 초기 이력·후속 arm/look 이력·검색 자세 모두 활성 채널 **1/3/4/5/6**과 정수 PWM
  **500–2500**을 사용한다. 범위는 기존 `visual_arm` 상수를 읽으며 해당 파일은 수정하지 않는다.
- 현재 집게 명령과 목표 집게 명령이 모두 **2000 이상**이어야 접근을 시작한다.
  기존 `zone_pair_grasp`의 열린 집게 판정과 같다. 이는 발행 명령의 판정이며 실제 파지/개방 측정이 아니다.
- pulse를 축소·클램핑·반올림하지 않는다. JSON의 문자열 채널 ID만 정수 키로 읽고,
  원본 history 행은 그대로 유지한다. 누락/비활성/알 수 없는/중복 채널과 범위 밖·실수·bool·NaN PWM은 거절한다.
- 자세 전이는 현재 발행 PWM에서 한 번에 20만큼 이동하며 pan은 native `look/pan_pulse`로
  발행한다. 실제 발행 ACK 뒤 같은 servo/history를 갱신하고 같은 provider에 한 번 전달한다.
  새로운 위치 초기화·측정 관절·GT 입력은 없다.

## 반례와 연속 인계 검사

`tests/test_review_e2e_batch_h.py`에서 #333에 해당하는 독립 반례만 가져왔다.
assertion 본문은 원본과 AST가 같고, strict xfail과 과거 Git blob fallback을 제거했다.
항상 현재 후보를 검사한다. #334 반례는 해당 PR의 소유 범위로 남겼다.
기존 CI navigation 테스트 파일에서 이 반례를 수집하므로 CI 목록/workflow 변경은 없다.

기존 양성 fixture를 표준 `SEARCH_POSE`로 교체했다. 새 회귀는 실제
`OwnCamPoseSource.on_command`를 재사용하며 위치 추정/영상/guard만 fake로 둔다.
양끝 역할 × 네 통신 조건 × 정수/JSON 채널 키의 16가지에서 팔·pan 전이,
정적 경로 접근, 두 영상 확인, 정렬 인계를 실행한다. 동일 provider/기억/servo/history 객체,
발행 원문, provider 소비값, 인계 receipt와 history hash가 유지됨을 확인한다.
PWM 양끝 500/2500, 열린 집게 경계 1999/2000, 잘못된 초기·목표·후속 명령도 검사한다.
제어 입력은 자기 RGB·정적 지도/공개 sheet·자기 명령 이력·실제 배달된 메시지로 유지한다.

최종 관련 검사는 **단일 실행 316 passed**, 실패·skip·xfail·collection error 0이다.
T08b 124 + T08a 64 + registered source 22 + study source pinning 34 +
기존 approach 12 + passage 44 + STATUS 16이다. 독립 반례의 별도 재실행도 1 passed지만
이 반례는 T08b 124에 이미 포함되므로 총합에 다시 더하지 않는다.
이는 오프라인 제어/계약 테스트 수이며 로봇 trial·물리 성공의 분모가 아니다.

## 변이와 보존

기존 8개에 native PWM/채널 회귀 7개를 더한 **15/15 변이 검출**이다.
정상 대조군은 124 passed였고 변이는 모두 pytest exit 1, assertion 실패 1개 이상,
collection/import error 0이었다. 변이는 각 Python 프로세스 안에서만 적용하며 실제 파일은 쓰지 않는다.

추가 변이는 0–1000 범위 복구, channel 2 필수화, 현재/목표 집게 열림 검사 각각 제거,
PWM 축소, 발행 ACK의 servo 반영 제거, pan PWM 축소다. 전체 항목별 결과와 로그 해시는
`REVIEW_FIXES_VERIFICATION.json` 및 로컬 `mutations/results.json`에 연결한다.
과거 `VERIFICATION.json`과 `mutation_results.json`은 덮어쓰지 않는다.

봉인 v6e 소스 **85/85 해시 일치**, 필수 두 source 테스트 및 `.github/workflows`,
`scripts/run_ci_tests.py`는 origin/main과 동일하다. 두 source 테스트는 검토 대상 HEAD와도
바이트가 같다. T08a 구현/기존 검사도 이번 수정으로 바꾸지 않았다.
T08b 124개와 T08a 64개는 기존 CI glob/shard에서 각각 한 파일로 수집되며,
그 안의 H333-1 반례는 한 번 수집된다.

## 소스와 재현

- 시작 시 `git fetch origin` → `git merge origin/main` 실행. 반영한 main은
  `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`, 통합 HEAD는
  `0a8f0d4c`다. #315 `86847071f0332c23e5858c93607e2b0bbeb6dc98` 재병합은
  already up to date였다. 재조회에서도 새 커밋은 없고 #315 자체는 OPEN/draft·미병합이다.
- 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python` 사용:
  Python 3.12.13, pytest 9.1.1, NumPy 2.5.2, OpenCV 5.0.0.
- 수정 소스 SHA-256: `334e5403542b4d9f3ab9c1ade4d7ebaa64422e9e69c134893ad7f322aacea959`.
  테스트·보존 검사·로그의 해시는 JSON에 별도 기록한다.

```sh
PYTHONPATH=.:experiments/2026-09-30-beam-approach \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -p offline_guard \
  tests/test_pair_navigation_beam_approach.py tests/test_pair_navigation_beam_initial_pose_plan.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_pair_owncam_approach.py tests/test_pair_passage_plan.py tests/test_zone_pair_status.py -q

/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-beam-approach/mutation_check.py /absolute/NEW-output
```

로컬 원본은 `/Users/changmin/projects/ugrp/outputs/t08b-review-fixes-20261001/`에 보존했다.
이 자료는 로컬 보관이며 원격 raw 백업이 아니다. UGRP 예외에 따라 Drive를 사용하지 않았다.
`/private/tmp` 추출 디렉터리는 만들지 않았다.

## 남은 범위

검토 지적의 코드 수정과 오프라인 회귀 범위다. #315의 최종 main 병합본 반영,
최종 v3 observer/provider/full-body guard·표준 adapter 연결과
`PHYSICS_HANDOFF.md`의 6셀 실제 출발→정렬 인수는 여전히 별도다.
이번 작업에서는 물리 재생을 요청에 따라 수행하지 않았다.
`physical_ready=false`, 배송 성공 null을 유지한다. 물리/학습/평가 결과가 없으므로
TensorBoard에 새 성공률 snapshot을 만들거나 기존 서버를 변경하지 않았다.
