# T07 — r3와 양끝 역할 교환

구현 후보다. 여섯 배정을 공개 요청으로 표현하고 양쪽이 독립 제출한 뒤에만
기존 상태 채널로 시작한다. **로컬 검증의 물리·SIM·렌더·실제 모델 호출은 0회다.**
최종 환경에서의 접근·파지·운반·방출 성공과 정식 s3 지연 의미는 아직 미검증이다.

**Batch F 수정:** 현재 사용 경로·소스 봉인·변이 검사와 #324 이관은
[REVIEW_FIXES.md](REVIEW_FIXES.md)를 따른다. 아래 최초 검증 442개는 당시의
부분 검사이며, 현재 v6e 소스 보존을 입증하지 못했다. 이 한계와 원본 기록은 보존한다.

## 공개 요청과 호환 범위

`harness.zone_pair_roles.PairRoles`의 입력은 `end_neg`와 `end_pos`에 배정한
로봇 ID 두 개뿐이다. 각 값은 r1/r2/r3이며 중복은 거부한다. 위치·접촉·상대 job·
사건·inventory/feasibility를 읽어 partner를 고르지 않는다.

고수준 호출자는 다음처럼 배정을 선택한다. `executor_plan`은 자기 claim을
명시된 역할과 대조하고 partner 및 role을 자기 API에 전달한다.

```python
from harness.zone_pair_role_integration import executor_plan, IntegratedTrial
from harness.zone_pair_role_host import OwnCamTeamHost

# host는 위 opt-in 클래스로 구성한다. 기존 host/study의 API는 그대로다.
assignment = {'end_neg': 'r3', 'end_pos': 'r1'}
plan = executor_plan(
    {'kind': 'claim', 'order_id': 'cargoX', 'destination_zone': 'B', 'role': 'end_neg'},
    None, actor='r3', orders=public_orders, role_assignment=assignment,
)
# plan: pair_carry('cargoX', 'B', 'r1', 'end_neg')
host.call('r3', plan.api, *plan.args)
host.call('r1', 'pair_carry', 'cargoX', 'B', 'r3', 'end_pos')
```

`IntegratedTrial(..., pair_role_assignment=assignment)`는 같은 공개 배정을
고정한 fake/고수준 호출용 연결이다. trial은 네 조건에 같은 mapping을 사용해야
하며, `condition_invariant_config`에 그 값과 별도 해시를 포함한다. 원본
LLM action/message schema와 prompt v3는 변경하지 않았다. 기존 claim에는
partner 필드가 없으므로 **이번 PR은 LLM이 대화 중 partner를 새로 결정하는
정책이나 runner CLI 옵션을 추가하지 않는다.** 공개 배정을 고수준 호출자가
명시하는 API와 고정 배정 비교를 제공한다. 동적 재배정·취소 정책은 T12다.

3인자 legacy 호출은 r1/end_neg·r2/end_pos만 허용한다. r3 호출에 역할을
생략하면 거부한다. 이전 배정의 계획·기록 형식, frozen M2/study 소스와 원본
시나리오·성공 bundle은 보존한다. 4인자 요청은 `zone_pair_roles_v1`로 기록한다.
한 세션의 양쪽은 같은 호출 형식·배정·정적 입력을 제출해야 한다.

실제 M2의 schedule 계산은 role 상수를 읽는 작은 읽기용 view로 재사용한다.
실제 controller ID·카메라·port·status·로그 ID는 배정된 물리 로봇 그대로다.
module 전역 ROLES, 기존 DOOR_PLAN과 controller의 rid는 바꾸지 않는다.

## 기록과 실패

- 새 세션은 `role_to_robot`, `role_assignment_sha256`과
  `controller_source_sha256`/`controller_source_files`를 따로 남긴다.
  코드 해시는 새 role executor/host/study adapter의 정적 Python import closure다. 동적 provider,
  모델·보정·지도·센서·메모리는 별도의 전체 실행 bundle로 고정해야 한다.
- `PairStatusChannel`의 FIELDS/STATES/heartbeat/readiness/GO 규칙은 유지한다.
  역할·좌표·이유·고수준 task 내용을 상태 메시지에 더하지 않는다.
- 같은 쌍의 주문/목적지/양끝 배정/정적 입력 불일치는 대기 중단과 자기 거절로
  남는다. busy caller는 상대 제출을 검사하지 않는다. 다른 쌍을 지정한 세 번째
  로봇은 기다리는 쌍을 취소하거나 참여하지 못한다.
- timeout 뒤 새 요청은 새 task ID를 사용한다. 과거 readiness/GO는 재사용하지
  않는다. 한쪽 abort/무응답은 선택된 쌍의 큐만 비우고 hold한다.
- `PAIR_SEQUENCE_DONE`은 하위 명령 순서의 완료이며 배송 성공 판정은 아니다.

## 선행 PR과 검증 범위

시작 main/HEAD: `c12796676802ab54cad2f0635e3e96e911691c76`.
작업 시작 조회에서 아래 PR은 모두 OPEN/Draft, **mergeCommit=null**이다.
표의 수치는 해당 PR의 자체 보고이며 T07의 검증 수에 더하지 않는다.

| PR | 조회한 head SHA | 선행 범위 |
|---|---|---|
| #302 P09 | bd95530a2d5a8b8467620809749273068a7ed55d | 원본 요구·T07 작업 계약, 정적 감사 |
| #305 P01 | 5a852fbfde3b0df836f3a423be29a774a9c54614 | 정적 resolver; 278 fake, 최종 v3 보정/물리 미검증 |
| #307 P02 | 6bb522b14aa28fcaa3ff30f988aebca4ab3aee15 | cyan+고정 r1/r2 봉 혼합 admission, r3 solo 제한 |
| #308 P05 | 5411f5e8d29186c00b44c2731e9915583da39aae | fake wire/대화·원장, 656 회귀; 실제 호출 아님 |
| #312 P03 | 919f78ef6ebaf2495633338bcb1b9510f46399bd | provider 수명·지연, 277 회귀; 실제 추론/물리 아님 |
| #311 P07 | bd011c997f9f7946de28f912dbdd3833ebb33988 | 실행 없는 manifest/관문; runnable=false |

선행 branch를 병합하거나 구현을 복제하지 않았다. P02의 고정 혼합 profile을
자유 배정으로 넓히지 않는다. P02 executor_plan의 order/목적지 거절과 P05의
usage 경로는 이 diff와 별도 hunk다. P03 provider·P01 resolver·P07 manifest는
수정하지 않는다. 합성 후 최종 SHA/실효 설정으로 재검증해야 한다.

## 로컬 검사와 인계

최초 제출 당시 14개 파일 회귀는 **442 passed / 0 failed / 0 skipped**, 128.85초다.
새 T07 검사 127개를 포함한다. 여섯 배정×네 조건의 실제 action validator→
IntegratedTrial dispatch→host API를 fake 호출로 검사하고, 모든 배정의 정적
geometry·실제 M2 schedule 계산식·불일치·timeout/재시도·private 변조·한쪽 실패를
확인했다. 첫 후보의 fixture 연결 실패 54개(capture 누락), 좁은 재검사의
1개 실패(가짜 pending 호출 기록 누락)를 보완했다. 초기 실패와 잠금 경합 원본은
보존했다. 원본 시나리오/지도/frozen 소스/registry **60파일 bytes 불변**도 확인했다.

검증한 제어 Python closure는 181파일이며 SHA-256은
`0b2a7939cd53b23d8fce88f91a690ec2d22e59551df1408fb54f06099ed5ca14`다.
커밋 전 작업 트리에서 검사한 코드/테스트 해시는 `verification.json`에 남긴다.
최종 검사 뒤에는 이 설명과 검증 기록만 추가했다.

`offline_checks.py`는 thread 1로 fake/저장 RGB 검사를 수행한다. main #328에
따라 공용 잠금은 기본 off이며 `UGRP_TEST_HOST_LOCK=1`일 때만 획득한다. guard가 MuJoCo/torch/network/render/실제 vision worker를 차단한다.
실행마다 primary `outputs/t07-r3-roles/offline-*`에 새 JUnit과 명령·종료코드를
남긴다. 잠금 경합·실패도 보존한다. 최종 수치/원본 해시는 `verification.json`에
기록한다. raw는 로컬 보관이며 원격 백업이 아니다.

새 실제 cohort가 없으므로 TensorBoard 성공 지표나 snapshot을 만들지 않는다.
실제 결과 수집·native TensorBoard readback·영상 확인은
[물리 인계](COORDINATOR_PHYSICS.md)의 필수 단계다. Drive 작업 없음.

정상 GitHub CI는 이 PR에서 실행한다. 로컬 fake 통과, 원격 CI, 독립 검토,
최종 환경 물리 준비는 별도 판정이다. Draft PR로 인계하며 병합하지 않는다.

## 참고 자료

- [P09 #302](https://github.com/kcm0127-dotcom/ugrp/pull/302): `REQUIREMENTS.md`, `TASKS.md` T07/T12
- [작업 경계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302#issuecomment-5911109450)
- [P02 공유 파일 경계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/307#issuecomment-5911109943)
- Refs #221, #223, #224
- `AGENTS.md`, `CONTRIBUTING.md`, `docs/execution_versioning.md`
