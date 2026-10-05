# R17 — 최종 lower → open → retreat → done의 명령 계약

**검토한 정상 경로는 마지막 구간에서 명령상 바닥 자세를 확인한 뒤 open barrier를 통과하고, 팔 큐가 끝난 후 남은 released 시간 동안 후진을 요청한다. `done`은 이 절차의 완료이며 물리적 배치 성공이 아니다.** 이번 범위에서는 새 결함을 확인하지 않았다. R15의 중간 checkpoint attachment 문제나 이미 수정된 같은 tick abort dispatch를 다시 세지 않는다.

고정 소스는 PR #363의 `66ff0978a817caa949d2d738b51d7ae89dd17e71`이다. `../round16/control-currentness.json` (Mac 전달본 증거)은 2026-10-04 08:47:00.544 UTC이며 그 이후 변경까지 검토했다는 뜻은 아니다. 최신 공개 실행은 정렬 중 재관측에서 멈췄으므로, 이 최종 구간이 그 실행에서 실제 도달됐다고 주장하지 않는다.

## 원본 경로와 재현 범위

`final-release-repro.py` (Mac 전달본 증거)는 exact Git object의 선택한 클래스·메서드를 AST로 읽는다. 원본 `HighController._wait_lower/_start_transit/_monitor_transit/_lower/_wait_open`, `TransitMonitor`, `ArmSequence`, `PairStatusChannel/Endpoint`, `PairStudent._wait/_released`, `PairGraspRelook.on_issued_command`와 `PairExecution.on_command`를 연결했다. `PairGraspRelook.tick` → `PairAlignRelook.tick` → `PairStudent.tick`의 최종 상태 위임도 원본으로 실행한다. `M2DoorStudent._wait_open`은 마지막 구간에서 부모의 release 경로로 위임한다.

```sh
python final-release-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project
```

Python 표준 라이브러리와 해당 커밋이 있는 Git clone만 필요하다. 결과는 `final-release-result.json` (Mac 전달본 증거)에 고정했으며 11개 원본 파일 SHA256을 포함한다.

선언한 시작 조건은 **최종 seg=2, 이전 grip epoch에서 HIGH·closed 명령 상태, 합성 own frame과 peer readiness**다. 이전 전체 grasp/lift/carry를 실행한 증거는 아니다. floor/hover 값은 R15에서 원본 v3 IK로 독립 확인한 정적 명령값을 사용한다. 시각 모니터는 log-only double이다. 실제 PF, frame gate, collision guard, lower CameraRobotPort 보간, 이미지 추론, 물리 관절, 바닥 접촉은 실행하지 않았다. 기록 포트는 production 순서처럼 endpoint command hook을 호출한 다음 own issued servo를 갱신한다.

기본 receipt는 이전 seg=0 그대로 두었다. 따라서 R15에서 발견한 stale-segment attachment flag를 이 재현에서 몰래 수정하지 않았다. receipt=2인 경우는 open 중 두 명령 기반 판정이 갈라지는 **별도 조건부 대조**다.

## 실행된 경계

| 경계 | 원본 판단 | 합성 재현 결과와 제한 |
|---|---|---|
| 최종 lower GO | `seg+1 == len(segments)`일 때 STOP checkpoint 대신 lower path 시작. fixed-enum barrier GO 필요 | 두 endpoint가 lower readiness를 보고하고 GO한 뒤 t=10.2에 시작. 중간 checkpoint 분기는 R14/R15 범위다. |
| lower 완료 | 실제 issued 명령이 예정 궤적에서 과도하게 뒤처지지 않고 peer 상태가 맞아야 한다. 충분한 transit sample, arm idle, floor 명령 일치, 같은 epoch의 closed 명령 필요 | 13.6 s로 예정한 upper path에서 137 command/status checks, 원본 요구량 134. 고유 RGB 수나 물리적 floor 관측 수가 아니다. t=23.8에 `floor_return_verified=True`, `wait_open`. 여기서 verified는 **commanded floor pose** 확인이다. |
| open 진입 | 마지막 segment이며 floor return이 확인돼야 한다. 이후 별도 open barrier | 정상 t=24.1 GO. 마지막 구간이 아니거나 floor flag가 False이면 각각 `FINAL_FLOOR_RELEASE_REQUIRED`. |
| open/retract 큐 | open .4 s + settle .5 s, hover .6 s + 기본 settle .1 s, SEARCH .8 s + 기본 settle .1 s | upper 큐 계획 합계 2.5 s. grip open PWM=2000은 t=24.5 발행. 팔 큐 완료를 기다린 뒤 후진 handler로 간다. 이것이 실제 관절의 도달 측정은 아니다. |
| retreat | `arm_idle`이고 `now-state_t < 6`일 때 reverse -.04, duration .15 명령 요청 | 첫 후진 t=26.7, 마지막 t=30.0, 34회 요청. **6초는 released 진입부터 흐르며 팔 동작 시간도 포함한다.** 34×.15를 이동 시간으로 더할 수 없고 실제 거리도 이 결과에서 얻지 못한다. |
| done | arm idle이고 released phase 6 s 경과 뒤 hold, own view 기록, `set('done')` | t=30.1. 합성 observer가 visible=False여도 `claims.placed.beam_visible_on_floor_plane=False`를 남기고 done. 성공 판정을 True로 바꾸는 동작은 없다. |

위 수치는 `10.2 + i×.05`로 만든 host grid와 .1 s controller 호출의 결과다. 부동소수점의 `arm.until` 비교도 그대로 사용했다. 정확한 절대 시각·처음 후진 tick을 모든 production clock에서 보장하는 값으로 읽지 않는다. **시간 계약의 핵심은 lower의 증거 확인, 팔 idle 선행, released 진입을 기준으로 한 6초 창**이다.

## 파지 표시의 해제는 한 시점이 아니다

| 표시 | 기본 stale receipt(seg0→현재seg2) | same-segment 대조 |
|---|---|---|
| `held_by_command()` | 첫 partial-open PWM=1521(t=24.15)부터 False | 동일. closed=1500과 exact equality이기 때문이다. |
| `beam_grasp_confirmed` | 시작부터 False. R15를 유지한다. | 1500 < PWM < 2000 동안 True일 수 있다. receipt의 segment 일치와 PWM<2000 계약이다. |
| receipt 객체 존재 | partial open 동안 남고 PWM=2000(t=24.5)에서 None | 동일. 실제 issued-command hook이 `close_issued_at`와 함께 지운다. |

어느 표시도 물리적 파지력·접촉 해제를 측정하지 않는다. 저장 receipt가 있다고 현재 segment의 geometry flag가 True인 것도 아니다. 이 차이를 새 release 결함으로 승격하지 않았다.

## 음성 대조와 닫힌 가설

| 대조 | 결과 | 해석 경계 |
|---|---|---|
| lower 도중 peer abort | `PARTNER_ABORT`, open/reverse 없음 | controller tick이 먼저 실패한다. 이 좁은 fixture는 즉시 중단하므로 남은 upper 큐를 계속 dispatch하지 않는다. 큐가 남았다는 값만으로 최신 runtime의 final veto를 우회한다고 해석하지 않는다. |
| lower 도중 heartbeat 중단 | `TRANSIT_PARTNER_DESYNC`, upper 큐 제거, open 없음 | original transit peer-state/freshness 확인. full endpoint에서는 별도 peer-silence 검사가 먼저 실패시킬 수 있으므로 이 reason의 전역 우선순위는 주장하지 않는다. |
| arm 명령은 실행하되 lower 관측 호출을 생략 | `LOWER_TRANSIT_EVIDENCE_INCOMPLETE`, open 없음 | 단순 elapsed time/arm idle만으로 완료되지 않는 handler 대조. 정상 host가 이렇게 호출을 생략한다는 주장이 아니다. |
| peer는 살아 있으나 open ready 미보고 | `BARRIER_OPEN_BARRIER_LIMIT`, closed 유지, release/후진 없음 | lower 완료만으로 open을 허가하지 않는다. |
| 6초가 지나도 arm busy | `_released`가 동작·capture·done을 발행하지 않음 | 별도 직접 handler 대조. busy 상태를 실제 지연 경로에서 유발했다는 증거는 아니다. |

실제 endpoint는 controller 앞뒤에 image/pose/geometry 검사를 수행한다. 따라서 위 정상 branch가 전체 실행에서 반드시 통과한다는 보장은 없다. 특히 collision guard의 `bounded_retreat` 정책은 **release 뒤 원래 sweep 검사에 걸린 reverse 요청을 hold로 처리**할 수 있다. 그러므로 done은 최소 후진 거리의 보장도 아니다. 이 정책의 guard를 낮추거나, 물리 성공을 만들기 위해 frame/receipt 기준을 완화하라는 제안은 하지 않는다.

## 다음 계층으로 넘기는 증거

Controller done 이후의 양쪽 done/status/own-job 종료는 별도 `done-endpoint-repro.py` (Mac 전달본 증거)과 `done-endpoint-result.json` (Mac 전달본 증거)이 다룬다. 그 재현의 선언된 controller-done prefix와 여기의 upper command sequence는 서로 다른 fixture 경계이며 하나의 물리 E2E 실행이라고 합치지 않는다. [R15 성공 증거 계약](../round15/research.md)의 절차 완료(C), 정책이 읽을 수 있는 증거(K), 평가 성공(Y) 구분을 유지한다.

현재 추가로 필요한 것은 새 success flag가 아니라 해석의 일치다. controller `done`, fixed-enum `PAIR_SEQUENCE_DONE`, own-job `unconfirmed`, referee task verdict를 별도 필드·별도 근거로 읽고, 실패한 최종 구간을 진단할 때에는 마지막 lower transit reason → open barrier → issued grip-open → upper arm idle → retreat guard 결과 순서로 판별하면 된다. 기존 trace 필드의 실제 저장 범위는 [R17 producer 표](trace.md)가 정리한다.

## 원본 위치

- [HIGH runtime](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_runtime.py): `_wait_lower`, `_lower`, `_wait_open`, `held_by_command`, `_transit_abort`.
- [HIGH pose](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose.py), [transit monitor](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_grip.py): queued lower path와 issued command/peer/sample 조건.
- [PairStudent](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/scripts/study_owncam_pair_beam.py), [M2 controller](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/scripts/run_m2_pair.py): final open queue와 released-phase 6 s 창.
- [ArmSequence](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/scripts/zone_teacher.py): queue와 issued pulse 생성. [PairGraspRelook](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_grasp.py): receipt property와 issued-open 무효화.
- [PairCommandGuard](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_guards.py): `before_control`, `_bounded_retreat`. 이 guard는 본 fixture에서 실행하지 않고 범위 한계를 위해 소스를 읽었다.
