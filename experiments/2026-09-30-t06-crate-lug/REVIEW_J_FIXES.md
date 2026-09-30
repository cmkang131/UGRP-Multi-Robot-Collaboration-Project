# #336 Batch J 지적 수정 — 2026-10-01

독립 검토 `b77a811970f95a9a69ee3ee15f9d09c3b99a137e`의 J1(P1)을 한 묶음으로 보완했다.
검토 후보는 `98ff3a1e3f3ecf7df18b339ae2e476327ac63ddd`이며, 먼저 main
`318f03731b4c0ba649faccc0bedd6b14c5da6a97`을 병합한 HEAD
`761928409c27d82e4c2c1c50179b82eb990297a9`에서 수정·검증했다.
최종 테스트 파일 해시와 원본 로그 해시는 [review_j_verification.json](review_j_verification.json)에 있다.

## 원인과 수정

원본 제어기는 안전하게 멈추지만 기존 회귀 검사는 상대가 스스로 abort하는 흐름과
양쪽이 함께 GO를 놓치는 흐름만 확인했다. 따라서 상대 holding 확인과 상대 GO 소비
확인을 각각 제거해도 55개 검사가 모두 통과했다. 가져온 독립 검토 테스트를 현재
tree에서 먼저 실행하여 **4 passed, 2 strict xfailed**를 재현했다.

- `test_fresh_peer_status_without_holding_stops_carry`: 양쪽 역할 × 최신
  `not_ready/ready/busy/done` enum, 총 8개. 양쪽의 정상 carry 진입 뒤 수신 wire에만
  holding 없는 상태를 넣는다. 상대 제어기는 abort하지 않고 heartbeat와 자기 holding
  RGB는 유효하다. 자기 출력이 `hold`, 실패 이유가 `PARTNER_HOLDING_UNCONFIRMED`이며
  이후에도 움직이지 않는지 검사한다.
- `test_one_peer_misses_go_stops_before_next_barrier`: 양쪽 역할 ×
  close/lift/carry/lower/open, 총 10개. 양쪽 ready 이후 한쪽만 GO를 소비한다.
  다음 tick에서 상대 heartbeat가 아직 유효해도 `PARTNER_MISSED_GO`로 hold·종료하고
  다음 단계의 동작을 내지 않는지 검사한다.
- 검토 브랜치의 `tests/test_review_e2e_batch_j.py`를 가져오고 strict xfail 2개를
  제거했다. 기본 대상은 **현재 tree**이고, 명시적인 `UGRP_REVIEW_J_CRATE_REF`만
  자체 정리되는 과거 archive를 사용한다. 정상 방어 2개, 제거 시 행동 변화 2개,
  전체 crate suite의 변이 검출 2개가 모두 필수 통과 검사다.
- `test_zone_own_executor_crate_review_j.py`가 검토 검사를 기존 CI glob으로 수집한다.
  CI 목록 확인에서 원래 crate 파일과 wrapper가 각각 한 shard에 포함된다.
  workflow와 CI runner를 수정하지 않았다. 변이는 자식 프로세스 메모리에만 적용한다.

제어기·dispatch·입력 형식·봉인 등록·기대 해시에는 수정이 없다.
자기 RGB, 정적 지도/공개 주문, 자기 발행 명령, 전달된 enum 경계와
`physical_supported=False`를 그대로 유지한다.

## 확인 결과

| 검사 | 결과 |
|---|---|
| crate 단독 + 검토 테스트 직접 실행 | **79 passed** (73 + 6) |
| 최종 관련 회귀 12개 파일 | **361 passed**, 실패·오류·skip 0 |
| 위 관련 회귀의 세부 | logic 189, integration 110, pinning 56, review J 6 |
| 기존 7종 + J1 변이 2종 | **9/9 검출**, collection error·skip 0, 원본 소스 해시 불변 |
| 상대 holding 방어 제거 | 전체 crate 73개 중 **8 failed / 65 passed** |
| 상대 GO 확인 제거 | 전체 crate 73개 중 **10 failed / 63 passed** |
| 봉인 보존 | v6e source 85개 + scene source 12개 모두 등록 해시 일치 |
| 추가 바이트 보존 | 원본 시나리오 12개, 두 crate runtime 파일, 필수 pin 테스트 두 파일 동일 |
| workflow | `.github/workflows/tests.yml`이 `origin/main`과 바이트 동일 |

79와 361은 중복 검사이므로 합산하지 않는다. 필수
`tests/test_zone_pair_registered_source.py` 22개와
`tests/test_zone_study_source_pinning.py` 34개가 56개 pinning에 포함된다.
Mutation 실패는 실제 assertion 실패이며 실행/collection 오류를 검출로 세지 않았다.

기존 Mac Python 3.12 환경을 재사용하고 host lock 없이 검사했다. 관련 회귀와 변이
드라이버는 MuJoCo·모델 SDK import와 network connect를 차단한다. **로컬 물리·SIM step·
렌더·모델 호출은 0회**다. 정상 GitHub CI는 push 후 별도로 실행하고 정확한 SHA와
상태를 PR 댓글로 남긴다. CI를 취소하거나 skip하지 않는다.

재현:

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-t06-crate-lug/offline_checks.py --output /absolute/NEW-offline
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-t06-crate-lug/mutation_check.py --output /absolute/NEW-mutations
```

원본은 primary `outputs/t06-crate-lug/review-j-20261001/`에 보존했다.
이 실행에서 `/private/tmp` 추출 디렉터리는 만들지 않았다. 원격 raw 백업을 뜻하지 않는다.
물리 실험 결과가 생기지 않았으므로 새 TensorBoard 실험 snapshot은 만들지 않았으며,
UGRP 예외에 따라 Drive 작업도 없다.

J1의 검사 공백은 닫혔지만 실제 JPEG 인식·arm/navigation 어댑터·runner 연결과 물리 인수는
여전히 미완료다. 기존 [물리 인계](PHYSICS_HANDOFF.md)의 제한을 유지하며
**draft PR로 남기고 병합하지 않는다.**
