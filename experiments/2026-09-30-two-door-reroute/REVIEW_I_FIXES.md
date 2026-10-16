# #330 독립 검토 I-330-1 보완 — 2026-10-01

독립 검토 `e24cb9ce3c10236efe03a1b66c9ec7671ece71b9`의 #330 지적 전체(I-330-1)를
한 묶음으로 수정했다. 검토 대상은 `f5d5af557525c9aa6d7fff043d933d2fc2c67967`이다.
main `26bfcf8e2977e85132845d7704fe1070f277dd13`을 merge
`3aaf62e6dbb460d6b998bcb97d876b79056b3bec`로 합친 뒤 수정했다.
#314의 `994b269d97d05dd2159c1a78f2b9eae9955790f9`는 이미 ancestor다.
이 PR은 draft로 유지하며 병합하지 않는다.

## 원인과 변경

새 순번/이미지 해시만 확인하면 새로 도착한 영상과 새로 촬영한 영상을 구별할 수 없다.
원본 반례를 현재 작업 트리에서 먼저 실행해 `RUNNING`, 새 navigation 호출 1회,
stop 0회를 재현했다. 수집/환경 오류가 아닌 원래 assertion 실패 1개다.

- `OwnFrame.captured_at_s`를 필수 필드로 추가했다. `now_s`와 같은 **자기 단조 시계**로
  촬영 시각을 찍으며, 수신/디코드 시각으로 덮어쓰지 않는다. 사건 시계나 평가 상태가 아니다.
- observer, 수신 메시지 반영, navigation 전에 시각을 검사한다. 유한하지 않은 값,
  bool/문자열/누락값/음수, 미래 촬영, 250 ms 초과 지연, 재사용·역행 촬영을 거절한다.
  시각 검사 실패는 기존 명령 큐 취소와 pair abort로 이어지며 이후 fresh 영상도 job을 되살리지 않는다.
- NEW/RUNNING/STOPPING/REPLAN_READY에 같은 검사를 적용한다. 재출발은 큐 취소를 확인한
  tick보다 뒤에 촬영한 영상만 허용한다. 비동기 취소가 여러 tick 걸리는 경우도 검사한다.
- controller 버전은 `ugrp.observed_door_reroute.v2`다. 250 ms 상한과 촬영 순서/취소 tick
  조건을 configuration invariant에 넣었고 네 통신 조건의 값은 같다.
  **250 ms는 후보 입력 계약이며 실제 카메라에 대한 지연/안전 보정 결과가 아니다.**
- 입력은 자기 RGB(자기 촬영 메타데이터 포함), 정적 지도, 자기 발행 명령 이력,
  실제 전달 메시지와 기존 fixed-enum 상태 채널뿐이다. private 사건/좌표/접촉/심판을 추가하지 않았다.

`tests/test_review_e2e_batch_i.py`의 #330 반례 본문과 assertion은 독립 검토에서 가져왔다.
xfail은 제거했고 과거 SHA 추출 fixture만 현재 작업 트리 검사로 바꿨다. 따라서
미커밋 수정과 정상 CI HEAD를 검사하며 /private/tmp 추출 디렉터리를 만들지 않는다.
#335 반례는 다른 PR 소관이라 가져오지 않았다. `scripts/run_ci_tests.py`의 기존
오프라인 목록에 이 파일을 명시했으며 `.github/workflows`는 수정하지 않았다.

## 검증 및 재현

- 통합 회귀 **518 passed + 280 subtests passed**, 실패/오류/skip/xfail 0.
  지정한 과거 등록 22개·source pinning 34개와 독립 반례 1개를 포함한다.
- 별도 CI 목록·분할·무잠금 검사 **90 passed**. 중복 제외 **608 passed + 280 subtests**다.
- 제거 변이 **9/9 검출**. 관측 87, 재계획 88, 정지 177, 메시지 3, 편대 실패 11,
  오래된 촬영 21, 미래 촬영 16, 촬영 순서 2, 취소 tick 이전 촬영 4개 assertion 실패.
  각 변이의 분모는 T09b 223개이며 모든 XML의 errors/skip은 0이다.
- 병합 직후 대비 보호 대상 소스·설정·지도·workflow·필수 검사 **955개 바이트 불변**.
  지정 두 검사와 `tests.yml`은 `origin/main`과도 직접 대조해 동일하다.
- 시험 중 소스 해시 불변. 이후 독립 반례 파일의 끝 빈 줄만 제거하고 AST 동일성을 확인했으며
  해당 반례 1개를 다시 통과했다(총계에 중복 합산하지 않음). 최종 SHA-256도 별도 보존했다.
  시험 당시 HEAD는 수정 전 base이며 이 파일을 담은 commit의 변경 바이트와 해시로 연결한다.

결과와 원본 해시는 [REVIEW_I_VERIFICATION.json](REVIEW_I_VERIFICATION.json)에 기록한다.
기존 Python 3.12 환경을 재사용하고 공용 host lock을 획득하지 않는다.
로컬 MuJoCo/glfw/torch/모델 SDK import와 네트워크를 차단한 fake 검사다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-two-door-reroute/run_checks.py --mutation suite \
  --output /Users/changmin/projects/ugrp/outputs/2026-10-01-t09b-review-i-fixes/NEW-checks
```

통합 묶음은 T09b·독립 반례·T09a·passage·모델 기하·pair status·메시지 protocol·
CI fast-path와 필수 `test_zone_pair_registered_source.py`,
`test_zone_study_source_pinning.py`를 포함한다. 별도 CI 목록 검사로
`test_ci_sharding.py`, `test_ci_host_lock.py`를 실행했다.

기존 5개 변이(관측/재계획/정지/메시지/편대 실패 검사 제거)에 촬영 유효기간·미래 시각·
촬영 순서·취소 tick 이후 촬영 검사 제거 4개를 더했다. 메모리에서만 변이하며
원본 파일은 바꾸지 않는다. 각 변이는 행동 assertion 실패로 검출돼야 하고
수집/import/setup 오류를 검출로 세지 않는다.

## 남은 범위

실제 Observer/Navigation/T06 연결, 촬영 시계 출처·adapter latency·주행 중 live RGB
안전 lease, 실제 큐 취소, 새 pair matching job과 실제 우회 인수는 남았다.
`now_s`는 tick 진입 때의 자기 시각이어야 한다. 진입 검사를 통과했다고 이후
느린 observer/actuator 실행 중 안전이 자동 보장되는 것은 아니며 하위 navigation의
지속 관측·정지 계약도 인수해야 한다. 새 bundle/workflow는 등록하지 않았다.

물리·렌더·모델 호출 0회, 확증·E2E 성공 주장 없음. 사용자 지시에 따라 물리 인수 재생은
실행하지 않았다. 새 물리/학습/평가 결과가 없으므로 TensorBoard 변환·서버 실행도 없다.
Google Drive는 프로젝트 예외에 따라 사용하지 않았다. raw 로그는 primary outputs에
로컬 보관하며 원격 백업으로 표시하지 않는다. Git에는 이 설명과 해시·검사 요약을 보존한다.
