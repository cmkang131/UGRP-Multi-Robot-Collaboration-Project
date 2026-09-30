# T12: 자기 요청의 짝 대기·재배정·취소

상태: **구현 후보·DRAFT, 물리 실행 준비 미완료**. `r3_hold_late`의 실제 정지·발견·집결 지연·정식 s3 배달은 측정하지 않았다. 정상 GitHub CI는 실행하며 PR을 병합하지 않는다.

## 변경과 경계

`harness/zone_pair_rendezvous.py`는 로봇 한 대에 묶인 `OwnPairPort`로 자기 job을 제출·취소·재배정한다. 새 파트너와 양끝 역할은 호출자가 고른 명시적 `PairRequest`다. host가 상대 private state를 보고 파트너·양보를 고르지 않는다. `replace(old_job_id, request)`는 자기 취소의 완료를 확인한 뒤에만 새 요청을 보낸다. 과거 job ID의 취소는 `STALE_JOB`으로 거절하므로 새 job을 지우지 않는다. 취소 거절/미확인은 새 제출을 차단한다.

제출 집결은 공통 5 SIM초 제한을 사용한다(허용 설정 범위 .2–30초, PairTeam과 같은 값으로 묶어야 한다). 기존 상태 채널에서 양쪽 `start_ready`가 자기 deadline보다 먼저 게시되었는지만 확인한다. 경계는 기존 `EPS=1e-8`과 같아 `deadline-EPS`부터 만료한다. 제한시간 직전 제출, 늦은 제출, 과거 상태 기록은 구분된다. timeout 후 재시도도 새로운 명시적 요청·job·상태 채널이어야 한다.

**제출 대기와 실제 접근은 다르다.** 이미 참여한 짝의 물리 접근·집결은 기존 M2 `APPROACH_WAIT_S=150` 및 own RGB/ready/GO 경로가 담당한다. T12는 이를 5초로 줄이지 않는다. 12–52초 사건이나 r3의 실제 바퀴·접촉·성공 정보는 이 모듈의 입력이 아니다. 명령을 받았다는 사실은 이동 성공이 아니며, 사건 종료시각에 job을 자동 부활시키지 않는다. 실제 진행 없음 발견은 기존 자기 관측/제어기(P08 등)의 별도 근거가 필요하다.

기존 API용 `LegacyOwnPairPort`는 r1/end_neg–r2/end_pos만 허용하고 r3 또는 역할 교환은 `T07_ROLE_ROUTING_REQUIRED`로 거절한다. 새 `RoleAwareOwnPairPort`는 T07 #323의 `pair_carry(order, zone, partner, role)`를 그대로 호출한다. T07의 role→robot mapping·하위 routing을 재구현하지 않았다. 실제 host의 r3 API/취소/재배정을 fake 포트로 검사하며 물리 이동 지원과 구분한다. T12의 독자 변경은 새 모듈·검사뿐이며 T07 소유 executor·상태 채널·시나리오·지도·봉인·bundle/workflow 등록부는 그대로 사용한다. 기본 study actor에 자동 연결하지 않는 opt-in 후보이다.

네 조건은 같은 모듈·설정·센서·기억·고정 enum 채널을 사용한다. 모듈에는 condition/leader 인자가 없다. leader 순환은 기존 `leader_for_seed`를 테스트하며 pair role과 별도로 기록한다. `assignment_record()`의 역할 배정 해시와 검증 기록의 제어 소스 파일 해시를 구분한다. 정적 공개 요청의 ID는 평가 item identity나 실제 물체 인식 결과가 아니다.

## 선행 소스와 소유 경계

작업 시작 base/main: `c12796676802ab54cad2f0635e3e96e911691c76`. 최초 T12 코드 `485a7627`은 main 위에서 관련 253개 검사를 통과한 뒤 커밋했다. 이후 T07 검증 커밋 `1a17829e79cdf7771ee2d09ca25e444c39cf37be`를 의존 소스로 연결했다. 아래는 착수/합성 시 GitHub 확인값이며, 모두 OPEN/DRAFT·`mergeCommit=null`이다. PR base는 T07의 `codex/r3-role-exchange`이며 GitHub PR 병합은 하지 않았다. 타 작업의 pytest 수치는 이 작업의 통과 수에 합산하지 않는다.

| 선행 | 확인 HEAD | 사용/남은 범위 |
|---|---|---|
| P09 #302 | `bd95530a2d5a8b8467620809749273068a7ed55d` | REQUIREMENTS/TASKS의 s3·T12 계약. inventory/feasibility는 제어 입력으로 쓰지 않음 |
| P01 #305 | `5a852fbfde3b0df836f3a423be29a774a9c54614` | 정적 map resolver만 참고. 최종 v3 물리/provider 보정 미확인 |
| P02 #307 | `6bb522b14aa28fcaa3ff30f988aebca4ab3aee15` | 고정 r1/r2 봉+r3 cyan 혼합 계약. 자유 r3 pair 지원 아님 |
| P05 #308 | `5411f5e8d29186c00b44c2731e9915583da39aae` | 조건별 transport/원장 소유. 새 한국어 모델 호출 없음 |
| P03 #312 | `919f78ef6ebaf2495633338bcb1b9510f46399bd` | fake provider 연속성. 최종 v3 실제 관측·지연 검증은 별도 |
| P07 #311 | `bd011c997f9f7946de28f912dbdd3833ebb33988` | 미실행 manifest 관문. 새 source/role/config pin은 합성 뒤 작성 |
| P06 #303 | `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8` | 평가·raw manifest·TensorBoard 소유. 그 파일들은 수정하지 않음 |
| T07 #323 | `1a17829e79cdf7771ee2d09ca25e444c39cf37be` | 역할 6종/명령 routing. 자체 442 offline 통과 기록 확인. 병합 SHA 없음; 이 소스를 그대로 합성 |

[범위 공유 #302](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302#issuecomment-5910995738), [P06 조율 #303](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/303#issuecomment-5910996337). 처음 검토했던 `PairExecution` 직접 변경은 필요하지 않아 하지 않았다. 새 모듈·테스트 2개·이 기록·CI 목록 두 행만 소유한다. T07 코드/기록은 원래 커밋의 이력과 바이트를 보존한다.

## 검증 항목

- r3가 양끝에 들어가는 요청 × 상대 r1/r2 × 네 조건 × 세 leader 값의 공통 enum/ready/GO. 별도로 T07 실제 host API에서 r3 양끝·재배정·상대의 독립 요청·오래된 취소·늦은 재요청을 검사한다.
- timeout 전/직전/경계/후 제출, 늦은 과거 채널 재생, 자기 시계 역행/NaN 및 불완전 포트의 안전 거절. host가 수락 직후 heartbeat 유실로 종료한 ack는 정상 terminal로 기록하고 자동 재시도하지 않는다.
- fake plant의 40초 명령 불응과 같은 허용 입력의 private 변화 비간섭. 기존 채널에서 partner 준비 전 WAIT, 새 own readiness 뒤 공동 GO.
- 명시적 상대 변경·취소 실패·stale job 취소 거절. main의 실제 host cancel 경로를 fake ports로 실행하여 양쪽 arm/schedule/port/host queue 잔류0, 무관한 r3 미변경.
- r3가 solo이면 역할 배정에 r3가 없으며 그 private state가 r1/r2 결과에 영향을 주지 않음. 이를 짝 지연 성립으로 세지 않음.
- 이미 조작한 job의 취소 후 holding=unknown이면 재시도를 `SELF_OCCUPIED`로 거절. 안전 상태를 host가 몰래 비우지 않음.

최종 7개 파일 회귀는 **425 passed / 0 failed / 0 errors / 0 skipped**, 142.43초다. T12 신규 검사는 204개(단독 계약159 + T07 실제 host 합성45)이며 나머지는 기존 PairTeam·T07·상태 채널 회귀다. 검증 코드 SHA는 `3a86d8700ee099520ea1dc846ae5e742dca2a049`이고 뒤 커밋은 이 기록만 추가한다. Python 3.12.13/pytest 9.1.1, 공용 `run_ci_tests.run_locked` 잠금 아래 수행했다. 최종 검사가 끝나고 자기 잠금을 반환했으며 다른 작업의 잠금은 변경하지 않았다.

최초 157개 검사 중 155 통과·2 실패도 raw JUnit에 보존했다. 경계 fixture가 대기자의 heartbeat를 갱신하지 않아 host가 수락 직후 안전 종료했으며, 이를 포트 오류로 분류하던 처리를 정상 terminal 결과로 고쳤다. healthy heartbeat 경계 검사와 silent peer 반례를 분리했다. 중간 253개 통과를 최종 수에 더하지 않는다. 시작 시점 보존 파일62개 중58개 바이트/해시 불변, T07에서 물려받은4개 파일은 `1a17829e`와 바이트 동일함을 확인했다. `git diff --check`와 변경 Python 구문 검사도 통과했다.

최종 명령·결과·환경·raw 해시는 [verification.json](verification.json)에 있다. 원본 JUnit은 `/Users/changmin/projects/ugrp/outputs/cap-t12-r3-delay/20260930T213220-junit.xml`이다. 단위/fake 검사는 물리·학습·평가 cohort가 아니므로 TensorBoard 성공률을 만들지 않았다. 실제 결과의 snapshot/화면 검증은 [코디네이터 인계](COORDINATOR_HANDOFF.md)를 따른다. 로컬 raw는 primary `outputs/cap-t12-r3-delay/`에 보존하며 원격 백업으로 표현하지 않는다. UGRP 예외에 따라 Drive 작업은 없다.

## 참고 자료

Refs #221, #223, #224

- #302 `REQUIREMENTS.md`, `TASKS.md` T07/T12; 원본 `configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json`
- `harness/zone_pair_executor.py` PairTeam/PairExecution, `harness/zone_pair_status.py`
- `harness/zone_own_team_host.py` `_drop_scheduled`/`call`, `harness/zone_own_executor.py` abort/holding
- `scripts/run_m2_pair.py` `_wait_approach`, `harness/zone_pair_grasp.py` close barrier
- `AGENTS.md`, `CONTRIBUTING.md`, `docs/current_status.md`, `docs/simulation_management.md`, `docs/tensorboard.md`
- 새 외부 의존성/논문/모델 없음. Python 표준 라이브러리, 기존 pytest와 fake host/저장 JPEG 재사용.
