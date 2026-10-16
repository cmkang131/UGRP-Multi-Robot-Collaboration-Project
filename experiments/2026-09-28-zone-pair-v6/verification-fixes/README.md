# PR #246 미완료 수정 후속 검증 (2026-09-28)

기준 HEAD: `364c48c7a9edae26a83c594bed3d4e9b7554c329`.
변경은 `codex/zone-pair-beam-relative` 작업 트리에만 저장했다.
사용자 지시에 따라 fetch·GitHub 조회·커밋·push·코멘트 게시·병합은 수행하지 않는다.

## 수정 범위

- **P1-2:** 같은 JPEG의 frame ID/수신 시각이 바뀌어도 원래 관측 시각을 유지한다.
  보고의 좌표·각도·오차는 `advance(now)` 이후 track에서 가져온다. 같은 프레임의 재독도
  시간 전파 상한을 쓴다. 저장 dev09 JPEG를 4초 반복하면 48.3028→50.3028 mm이며 pre-close를 거절한다.
  `ready()`의 관측 신선도 검사를 유지하므로 0.3초가 지난 복사 영상으로 안전을 인증하지 않는다.
  이 경우 정렬은 즉시 실패하지 않고 기존 제한 시간 안에서 새로운 입력을 기다린다.
  `record_standoff → align`이 새 영상을 같은 tick에 다시 읽는 경우에는 원래 형상 판정을 유지하여
  close-in·뷰 전환을 막지 않는다. 해당 재독과 만료된 반복 수신을 별도로 회귀한다.
- **판정 회복:** 거절된 stale·카메라 불일치·역순 입력은 유효 관측 캐시를 덮어쓰지 않는다.
  최초 입력 거절 후 같은 픽셀의 유효 관측과, 유효 입력의 만료 후 새 픽셀 관측의 회복을 시험한다.
- **P1-3:** `zone_pair_status`의 정규화 규칙을 안전 검사와 공유한다. `aligning`에는 열린 집게의
  하강도 포함되고 `ready`는 닫기, `lift`는 들어올리기다. `not_ready`, 6단계×ready/go×8구간의
  모든 barrier 상태도 같은 규칙으로 처리한다. 상대 이동 중에는 앵커를 버리고 새로 만들지 않는다.
  219 mm 위치 오차가 기존 2σ 상한을 넘는데도 안전을 통과하던 합성 반례를 거절한다.
  앵커 자체를 검증하는 기존 양성 테스트는 상대의 `stopped`를 명시한다.
- **P2-2:** frozen M2의 `stored` 경로가 `set('align')`을 거치지 않는 점을 adapter의 `_cp_open`
  진입에서 처리한다. checkpoint 완료 시 다음 `_queue_grasp`보다 먼저 look/HIGH 예산을 초기화한다.
  팔 작업 대기 중·동일 구간의 재시도·relook 복귀에는 예산을 채우지 않는다.
  세 조건에 공통이며 job 전체의 scheduled count/total은 유지한다.

시나리오·조건 설정은 유지하고 조건 선택은 `pair_policy`만 다르다. 새 GT 제어 입력·AprilTag 의존·weld를
추가하지 않았다. 기존 `tags_temporary` provider를 markerless 검증으로 승격하지 않는다.
물리 에피소드·모델 호출·새 운반 결과는 없으며 TensorBoard 실험 결과도 생성하지 않는다.

## 번들과 인계

`bundle_audit.json`에 로컬 origin 참조 121개와 다른 worktree/공용 outputs의 기록 검색을 남겼다.
v70의 외부 일치는 #249 초안 문서의 #246 후보 소개뿐이며, 검색한 등록 JSON·manifest·결과에서는 없다.
v70은 유지하고 v6 DRAFT의 source 계약 및 `scripts/zone_pair_authorization.py`의
`digest(registration_payload(...))`로 등록 해시를 갱신한다. 과거 실행 기록은 바꾸지 않는다.
실시간 원격 PR/참조 확인은 권한 범위 밖이므로 관리자가 재확인해야 한다.
실제 origin은 `https://github.com/kcm0127-dotcom/ugrp.git`이며 원격 설정은 변경하지 않았다.

1차 전체 회귀는 364 passed / 1 failed였다. 실패는 같은 프레임의 재독에서 report 객체가
동일해야 한다는 이전 검사였으며, 관측 시각 유지·오차 상한 증가·현재 track과의 일치 검사로 바꿨다.
최초 반례 실행에서는 stale·카메라 불일치·역순 입력의 회복 실패, 219 mm 반례의 잘못된 안전 통과,
세 조건의 stored 예산 이월을 확인했다. 반복 JPEG 검사의 초기 실패는 테스트가 자기 pose 보고를
새 시각으로 갱신하지 않은 설정 문제도 포함했으므로 제품 실패 수로 합산하지 않는다.

중간 재실행에서 transient 대기 처리가 같은 tick의 첫 영상 재독까지 포함하는 회귀를 발견했다.
67 passed / 8 failed에서 본인이 시작한 테스트 세션을 Ctrl-C로 중단했다
(`pytest-transient-regression.txt`). 새 영상 재독과 반복 수신을 분리한 뒤 최종 소스를 다시 검증한다.

최종 전체 회귀는 **366 passed / 0 failed, 271.97초**다.
`tests/test_zone_pair_v6*.py` 전체와 status/grasp/preclose/standoff/v5h 파일을
지정 Python·OMP_NUM_THREADS=2·no cacheprovider·`.pytest_tmp` 경로로 실행했다.
별도 반례/최종 검토 재실행은 129 passed이며 전체 수에 중복 합산하지 않았다.
`.pytest_tmp` 삭제, `git diff --check` 통과, HEAD 유지도 확인했다.

등록 소스 72개와 현재 내용이 일치하고 등록 SHA-256은
`2453df542e8c7ac7d40af7d7d66593be8cfb4bfda342a13f56a2bdd93f6b5d74`다.
[최종 로그](pytest.txt) · [검증 메타데이터](validation.json) · [등록 검증](registration_validation.json).
루트 `COMMIT_MSG_CODEX.txt`와 `PR_COMMENT_CODEX.md`를 관리자 인계용으로 작성했다.
