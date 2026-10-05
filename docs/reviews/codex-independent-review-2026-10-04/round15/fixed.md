# R15 · same-tick peer-abort dispatch 수정 확인

**`66ff0978a817caa949d2d738b51d7ae89dd17e71`은 기존 R8의 same-tick dispatch 반례를 차단한다.** 나중에 처리한 actor가 abort하여 앞 actor까지 terminal이 된 경우, 새 runtime은 이미 모아 둔 앞 actor의 motion/arm 명령을 같은 tick의 hold로 바꾼다. 과거 finding과 원본 재현은 보존하고, 이 문서는 확인한 source 수정 범위를 추가한다.

이 결과는 offline fake-boundary 회귀 검증이다. 모델·physics·렌더·하드웨어·실제 episode를 실행하지 않았다. source pin은 old `de03fe87d08879abefaa7dac67c7ff313df5df89`, new `66ff0978a817caa949d2d738b51d7ae89dd17e71`이다.

## 실제 연결한 코드

R8 `frontier-peer-abort-repro.py`와 `frontier-peer-abort-dispatch-repro.py`의 원래 witness 구조를 사용했다. 각 pin의 Git object에서 원본 runtime collection, own executor step/termination/command receipt, endpoint step/check/abort/clear, status channel/endpoint, team.poll method를 가져온다. 새 경로에는 `Runtime._vetoed/step/arm_step`, `final_veto` 전체와 idle 상태의 실제 `LookRecovery`를 연결했다.

반환 목록은 원본 `sim.final_pair_v3.PhysicsBackend.issue → BaseBackend.issue`와 전체 `CameraRobotPort`를 통해 command spy까지 보냈다. non-calibration collection interlock, controller 동작, geometry/frame/초기 bootstrap은 명시적 boundary collaborator다. geometry가 거절하는 이유나 영상을 판정한 것이 아니라, **거절이 발생한 후 실제 scheduler와 dispatch 경계의 순서**를 검증한다. 모터/서보 출력은 commanded setpoint이며 실제 이동·정지를 뜻하지 않는다.

arm clock도 같은 supported endpoint의 원본 `arm_step`을 사용했다. 이 경우 old runtime에는 collection 이후 `team.poll`이 없고, new runtime은 poll 후 final veto를 한다. 별도 scheduler를 새로 구현한 결과가 아니다.

## old/new 대조

| 입력 경계 | de03 | 66ff0978 |
|---|---|---|
| control: r1 motion 수집 후 r2 local failure | 둘 다 terminal인데 r1 `.1` forward command가 dispatch됨 | r1/r2 모두 hold만 dispatch |
| arm: r1 arm command 수집 후 r2 arm-guard failure | r1은 아직 nonterminal이고 arm target 1600이 dispatch됨 | 같은 tick poll로 r1도 terminal, 둘 다 hold만 dispatch |
| control/arm: abort 없음 | 원래 motion/arm command | old와 동일한 command 목록; 무조건 hold로 바꾸지 않음 |
| 실패 actor를 먼저 처리 | control은 이미 hold; arm은 앞서 실패를 본 r1이 아무 명령도 반환하지 않음 | control은 hold 보존; arm은 새 terminal r1에 필요한 hold를 추가 |

총 **2 source pins × 2 caller clocks × 3 조건 = 12개의 bounded scenario**를 실행했다. old control witness에서 실제 port의 마지막 모터 setpoint는 `[.1, .1, .1, .1]`이며, 새 later-abort 두 경우에는 nonzero motor command·pending servo target·servo update가 없었다. no-abort positive controls는 motion/arm 명령을 유지했다. fixture는 0.049초 port tick도 실행하지만 physics callback은 없으므로 물리 이동량이나 잔류 속도를 추론하지 않는다.

새 final veto는 endpoint의 terminal 상태를 읽고, 이미 있던 own/status propagation을 끝낸 뒤 적용한다. peer controller의 pose를 새로 참조해 판정하거나 한 actor를 무조건 따라 종료시키는 독립 정책은 아니다. `LookRecovery`는 이 fixture에서 pair job이 이미 시작된 정상 idle 상태이며, 새 admission/relook 회복 기능까지 검증한 것은 아니다.

이 증거로 이전 문서의 “현재도 same-tick queued command가 남는다”는 주장은 **이 head의 확인한 두 caller에서는 수정됨**으로 갱신할 수 있다. 과거 run의 성공/실패를 재해석하거나 모든 terminal·retry·wire failure·world cleanup 조합이 해결됐다고 확대하지 않는다. receipt/loaded geometry와 HIGH checkpoint timeout은 별도 계약이다.

증거 파일: `final-veto-fix-verification-repro.py`, `final-veto-fix-verification-result.json` (Git pin·source SHA256·각 dispatch/terminal/port receipt/veto log 포함).

독립 검토자가 재실행하여 12개 scenario의 JSON 전체 일치, 18개 old/new source hash와 실제 runner dispatch 연결을 확인했다. [독립 QA](validation.md#fixed)의 PASS 역시 위의 두 caller와 명령 계층 범위에 한정한다.

소스: [새 runtime 순서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_runtime.py), [final veto](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_final_veto.py), [원래 collection](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_final_pair_runtime.py#L56-L83), [backend issue](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/sim/final_pair_v3.py#L78-L85).
