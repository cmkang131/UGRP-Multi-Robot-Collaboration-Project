# T13b — own RGB 복구 결정과 사건 no-op 분리

**Draft 구현, 물리 준비 미완료. 병합하지 않는다.** 원본 s5의 이동30초/낙하62.5초와
`HiddenEventPhysics.apply`를 그대로 보존했다. simulator/renderer/모델 호출은 하지 않았다.

## 변경

- `harness/zone_item_recovery.py`: T13a `IdentityJobs`를 확장하는 opt-in 결정 모듈이다.
  연속된 자기 RGB에서 held→unheld/resting이 확인되면 하위 refresh 전 cancel하고 재관측한다.
  가림/추적 소실/불명은 unknown으로 남긴다. pickup 전체가 명확히 보이는 빈 ROI 두 프레임만
  지역 부재 근거로 쓴다. initial_location이나 새 물체 위치를 고치지 않는다.
- 재시도는 새 자기 프레임과 T13a specific/count/target API 검사를 다시 통과해야 한다.
  같은 local track만 유지되고, 소실한 token을 새 label로 되살리지 않는다. 불명 재관측3회,
  성공적으로 제출한 복구3회 뒤 멈춘다. 자기 open/하위 완료/새 submit만으로 배송·복구
  성공을 만들지 않는다. 성공은 기존 held→own open→목적지 비파지·정지2회라는 자기 믿음이다.
- `harness/zone_recovery_eval.py`: run/event별 할당·applied·no-op·실제 효과·발견·복구를
  평가 전용으로 분리한다. gripper fault 적용만으로 실제 낙하를 확정하지 않는다.
  no-op는 복구 성공/실패 어느 쪽도 아니며 모든 할당 분모에는 남는다. cap/host 오류/미실행도
  보존한다. 효과 성립 분모0이면 rate는 None이다. controller가 이 모듈을 import하지 않는다.
- `tests/test_zone_own_executor_recovery.py`: 기존 CI glob에 자동 포함된다. CI workflow와
  CI 설정은 이 작업에서 수정하지 않았다. 시작 branch의 `run_ci_tests.py` 차이는 #320의
  T13a 검사 등록이며 그대로 상속했다. 이후 #320 main 병합도 확인했다.

현재 `RecoveryJobs`는 실제 RGB recognizer나 target-aware native backend를 제공하지 않는다.
private event/holder/배치/partner 정답/P09 inventory 입력은 받지 않으며, 같은 정책을 모든
actor와 네 조건에 사용한다. 통신 enum/채널도 바꾸지 않았다. 조건별 override는 없다.
실제 어댑터가 RGB 추론의 출처와 오인식을 검증해야 하며, 해시 자체는 올바른 인식의 증명이 아니다.

## 기준과 선행

- 시작 main: `ad496486271f441f00eb7d95fbd44dc454999004`.
- 시작 worktree: `7c2dcead1e96cc113680a0cd28ba95d63e12ddf4`.
  #320 `ad63341d13a175582fbe7f5a664ca5bca5a33eaf`의 로컬 merge commit이다.
  시작 시 GitHub #320은 OPEN/merge SHA null이었다. 작업 중 2026-09-30 13:47 UTC 확인에서
  MERGED, 실제 merge SHA `fbddbefe75adb0b6e3290d8b7a346c0f1dbfd813`로 바뀌었다.
  head는 동일하며 선행 코드 추가 변경은 없다.
- 재개 시 #328이 병합된 main `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`를
  충돌 없이 반영했다. 이전 main 병합 대기 상태를 갱신하면서 T13b 파일 9개의 해시를
  보존했다. 이 main과 CI 설정/workflow 차이는 없다. 오프라인 검사에는 호스트 잠금이
  필요 없으며 물리·렌더는 실행하지 않았다.
- #302 REQUIREMENTS/TASKS의 T13b를 읽고 원본4분기·cap을 따랐다. 선행 PR head/병합 상태와
  검증 범위는 `verification.json`에 기록한다. 선행의 시험 수치를 T13b 결과에 합산하지 않는다.
- primary checkout은 재개 시 깨끗한 main `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`였다.
  이 작업은 draft만 요청받았으며 primary를 변경하거나 PR을 병합하지 않았다.

## 검증과 한계

실제 실행한 fake/관련 회귀, mutation 결과, 코드·원본·JUnit hash는 `verification.json`과
`protected_sha256.json`에 남긴다. 공용 잠금이 점유된 첫 시도는 pytest를 시작하지 않고
거절됐다. 최초 own-lock fake 검사는 48 통과/1 실패였고 취소 오류 뒤 프레임 연결 반례를 수정했다.
이 차단 기록은 과거 이력이다. #328 반영 뒤 호스트 잠금 없이 수정 후 회귀와 mutation
검사를 수행했다. 기존 잠금의 획득·해제·변경은 하지 않았다. 실행 시간은 성능 측정이 아니다.

검사는 production `HiddenEventPhysics.apply`의 4분기를 fake 배열/actuator로 실행한다.
MuJoCo world/Scene/렌더/물리 step은 생성하지 않는다. 원본 specific 주문과 별도 in-memory fungible dev 주문 각각
로봇3명×통신4조건×private4변형(총96흐름)에 동일한 공개 입력과 고정 action을 넣어 관측 전 사건 효과·시각·holder 변경 비간섭을 검사한다.
sealed source 검사는 `test_zone_pair_registered_source.py`와 `test_zone_study_source_pinning.py`다.

최종 구현 `5d1268e8a95cff5506d67d86ddaa6f1948be1908`의 관련 회귀는 **278 passed**다.
T13b 53, T13a 71, 공개 입력45, 공통 계약53, 등록 소스22, source pinning34를 포함한다.
331.49초는 해당 실행의 소요 기록이며 성능 비교가 아니다. mutation **6/6 검출**:
취소 오류 차단·낙하 후 cancel·부재 판단·no-op 분모 제외·held 이동 no-op·unheld 낙하
no-op를 각각 제거하면 해당 assertion이 실패한다. 오류/수집 실패로 검출을 대신하지 않았다.
메모리에서만 바꿨고 디스크 소스는 동일하다. 보호 대상59개도 원래 해시와 일치한다.
기존 입력 회귀의 PIL 정적 지도 그림 생성은 포함되며 MuJoCo 장면/카메라 렌더는 없다.

기존 Mac Python 환경으로 다시 검사할 때:

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_own_executor_recovery.py tests/test_zone_identity_jobs.py \
  tests/test_zone_study_inputs.py tests/test_zone_study_contract.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  scripts/check_zone_item_recovery_mutations.py \
  --output /Users/changmin/projects/ugrp/outputs/t13b-mutations-NEW-ID
```

raw 로그·JUnit·mutation 원본은 primary `outputs/t13b-recovery-offline-20260930-r2/`에
로컬 보관한다. Git에는 요약·전체 파일 해시를 남긴다. raw 원격 백업은 아니다.
새 테스트는 기존 `test_zone_own_executor*.py` glob에 포함된다. CI 설정을 바꾸지 않았고,
정상 PR CI를 실행한다. 제출 이후 상태는 PR checks에서 확인한다.

현재 specific cyan grounding, red/can 하위 skill, 실제 입력·backend·평가 연결은 미완료다.
따라서 알려진 물리 인수 재생은 sandbox 금지와 선행 연결 부재로 실행 불가이며, 과거 성공을
승계하지 않는다. 새 실험/학습/물리 결과가 없어 TensorBoard snapshot은 만들지 않았다.
실제 결과의 native TensorBoard 검증은 [SIM 인계](SIM_CHECKS.md)를 따른다.

## 참고 자료

- [T13a 선행 PR #320](https://github.com/kcm0127-dotcom/ugrp/pull/320)
- [오프라인 테스트 잠금 선택화 #328](https://github.com/kcm0127-dotcom/ugrp/pull/328)
- [P09 요구·작업 배정 #302](https://github.com/kcm0127-dotcom/ugrp/pull/302)
- [T03 red/green #325](https://github.com/kcm0127-dotcom/ugrp/pull/325)
- [원본 v2 s5](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json)
- [기존 hidden event 물리 구현](../../sim/zone_hidden_events.py)
- [코디네이터 4×900 SIM초 체크](SIM_CHECKS.md)

코드는 커밋 `888447674318bc311e1ef65f71c654692b2b76bb`에서 재현(퇴역 전 소스 복구 기준). 당시 실행 SHA·설정·결과는 본문 기록을 따르며, [퇴역 목록](../../docs/retired_modules.md)을 참고한다.
