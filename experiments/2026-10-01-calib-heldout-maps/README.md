# 다른 두 지도 무하중 검증 수집 — v90

Refs #344. 구현 기준 main: `2523269857596ffdd1a8cda9814a6e92f399f1da`.
번들 `zone-final-pair-v90`, 새 workflow `zone-final-pair-heldout-v90` **3.2.0**.
DRAFT_UNSEALED이며 물리·렌더·모델 호출을 실행하지 않은 구현/회귀 기록이다.

## 범위

`zone_wide_corridor_final_v3`와 `zone_wide_door_geometry_v3`를 명시한
`run_final_pair_v3 --check calibration-unloaded`는 v90으로 계획/수집한다.
표준 관리 경로에는 별도의 `zone-final-pair-heldout-v90` workflow를 추가했다.
이 workflow는 지도 생략·두 문 지도·fine/loaded·학생 p03/carry를 거부하며 seed는 911로 고정한다.

- `collection_role=HELD_OUT_VALIDATION`, `training_eligible=false`, `teacher_only=true`를
  plan/bundle/사례 result/전체 result에 기록한다. 이 표시는 수집 용도이며 통과 판정이 아니다.
- 기존 v88 unloaded 스케줄 함수를 그대로 호출한다. 각 지도 370 SIM초, reset 포함 최대 375초.
  #347/v89에서 온 계단·PRBS와 기존 v88 자세 일정 모두 동일하다. pose 0.05초 7,401개,
  RGB 0.2초 대당 1,851장, 0.05초 명령 lease와 발행 순서를 그대로 쓴다.
- 동일 teacher 시작점·floor_light_v1·cargo_noslip_v1·weld OFF·초음파 OFF를 사용한다.
  새 지도에서 시작점과 ADVISORY 운동 범위를 다시 계산한다. 필수 인터록과 abort/hold,
  HOST_ERROR·부분 raw 보존 규칙은 바꾸지 않는다.
- fine/loaded는 두 문 전용이다. 두 문 기본 선택, 사례·시각·계획/번들의 기존 동작 필드,
  세 profile의 명령 파일 바이트를 변경 전 fixture와 대조한다.
  `source_sha256`과 이를 포함하는 `bundles_sha256`는 새 소스의 실제 해시로 바뀐다.
  과거 소스 SHA나 실행 결과로 새 소스를 표시하지 않는다.

## 등록과 보존

[최초 번호 조회](reservation_scan.json)와 [재개 후 최종 조회](reservation_final.json)는 main + 열린 PR 전부의 원격 SHA,
요청한 `git grep` 결과와 workflow 최댓값을 기록한다. 조회 최댓값 v89와 3.1.0 뒤의
**v90 / 3.2.0**을 사용했다. #347은 이미 main에 병합됐고 #339는 여전히 열려 있다.
기존 `configs/zone_final_pair_v88.json`, 모든 기존 workflow JSON, 지도·보정 계약,
clearance 정책·일정 생성기·동결 criterion B는 그대로 보존했다.

[변경 전 v88 fixture](v88_baseline.json)는 위 main에서 물리 없이 만든 계획/번들의
소스 해시 제외 값과 실제 JSON writer의 schedule 파일 해시다. 물리 결과/학습 자료가 아니다.
무하중 schedule SHA-256: `8e9a126cfdcbc5961cacac4165b76ac65da3310aa40b758f0590d999917813db`.

## 검증

재개 후 주요 보정 회귀 **106 passed**, CI sharding **68 passed**, workflow **17 passed**로
**191개**를 확인했다. 재개 전 관련 기록과 중복을 제거하면 **368개 통과 / 1개 미확인**이다.
미확인 항목은 기존 `test_parent_exit_cleans_background_child`의 sandbox `ps` 실행 제한이며
CI에서는 유지한다. 중간 workflow 재검사에서 기존 입력 대기 검사 1개가 3초 timeout에
걸렸으나 소스·제한 변경 없이 단독 재실행에서 **1 passed (1.09초)**였다.

[검증 기록](verification.json)에 명령·검사 결과·소스/로그 해시를 남긴다.
새 테스트 `tests/test_zone_final_pair_heldout.py`를 `scripts/run_ci_tests.py`에 등록했다.
GitHub의 8개 shard는 이 목록을 공유하며 새 파일은 정확히 한 번 포함된다.
새 workflow의 catalog 수와 계획 fixture도 추가했다.
`configs/ci_test_durations.json`에는 재개 전 JUnit에서 측정한 이 파일의 합계 **146.14초**를
추가했다. 새 파일 추가 전 367/407이던 시간 자료 coverage가 367/408로 90% 아래가 되어
실패했으며, 측정값 한 항목을 추가해 **368/408**로 복구했다. 기존 시간 값은 그대로다.

검사는 두 지도 계획, fine/loaded 거부, seed/teacher/지도/시간/인터록/물리 구성 변조 거부,
기존 두 문 계획·세 schedule 바이트 보존, fake 370초 전체 명령/표본 수,
wall/NaN/누락 중단의 hold·HOST_ERROR·부분 해시 보존, 전체 결과의 검증용 표기를 다룬다.
fake backend는 실제 physics가 아니다. native MuJoCo·모델 worker·네트워크는 차단한다.

새 물리/학습/평가 자료가 없어 TensorBoard 변환·뷰어를 시작하지 않았다.
물리 담당자는 [인계의 지도별 두 명령](../../PHYSICS_HANDOFF.md)을 사용하고,
실제 결과를 회수한 뒤 별도 snapshot에 등록해야 한다.
재개 시 `/private/tmp`에서 이 작업의 extraction 디렉터리는 발견되지 않았다.
이번 재개에서도 extraction을 만들지 않았다. 다른 작업의 임시 자료는 삭제하지 않았다.

## 남은 연결과 검증 범위

`consumer_criterion_B.json`과 `scripts/validate_consumer_criterion_b.py`는 아직 v88 ID만
허용한다. 동결 기준을 이번 변경에서 수정하지 않았다. 새 v90 raw를 v88로 바꿔 표시하지 않으며,
v90 허용의 명시적인 후속 검토·연결 전에는 현재 검증기로 B 통과를 낼 수 없다.
실제 수집 완주·안전·fit·B 검증·MEASURED_SIM 승인·학생/실물 성공은 모두 별도다.

## 참고 자료

- [v88 어댑터 #344](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/344)
- [v89 계단·PRBS #347](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/347)
- [v88 원래 구현·결정 2](../2026-10-01-v3-pair-adapter/README.md)
- [동결 consumer criterion B](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)
- [물리 인계](../../PHYSICS_HANDOFF.md)
