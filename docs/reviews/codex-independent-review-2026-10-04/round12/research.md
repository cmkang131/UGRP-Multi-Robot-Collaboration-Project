# R12 — 관측 실패를 해석하기 전에 view 명령의 의미를 맞추기

**relook가 끝났다는 시간 판정과, 그 영상의 camera-command 모델이 실제 발행 명령 이력에 맞는다는 판정은 다르다.** 원본 함수로 재현한 반복 hold/pan 반례는 이 차이를 별도 센서 없이 조사할 수 있게 한다. 이 문서는 제어 반례의 연구 해석과 최소 판별만 다룬다. 현재 공개 r2 SELF_UNCERTAIN 또는 loaded POSE_UNCERTAIN의 원인을 확정하지 않는다.

source는 PR #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`이며 이전672와 해당 source는 동일하다. 제어 담당의 초기 반례(Mac 증거), `relook-ranking-results.json` (Mac 전달본 증거), `relook-ranked-sequence-result.json` (Mac 전달본 증거)와 `relook-host-phase-result.json` (Mac 전달본 증거)를 연결한다. authored own estimate와 no-fix 응답을 사용하는 source fixture이며 raw trajectory나 physical execution은 아니다. ranking→세 view→원본 guard/endpoint 연결 실행, [ranked sequence QA](validation.md), [host/substep 순서 독립 QA](validation.md)가 완료됐다. 직접 읽은8개 source의 Git blob/SHA256/범위는 `view-command-sources.json` (Mac 전달본 증거)에 고정했다.

## 같은 ‘own command’ 안에도 세 시점이 있다

| 상태 | 원본 의미 | 이것만으로 알 수 없는 것 |
|---|---|---|
| `ArmSequence.commanded` | queue를 작성하자마자 저장하는 **미래 끝점**. smoothstep events는 이후 각 시각에 발행 | 현재 port까지 전달된 pulse, interpolation 완료 |
| `own.servo` / provider `self.servo` | on_command가 받은 **upstream arm/look target**. hold에서 servo 값을 갱신하는 분기는 없음 | port의 slew limiter가 현재 어떤 setpoint까지 발행했는지, hold에 따른 queue 취소 결과 |
| `CameraRobotPort._servo_applied`와 hardware setpoint 호출 | port가2000PWM/s 한도와 시간에 따라 보간해 **발행한 setpoint**. 내부 누산기는 분수, hardware 호출은 정수 | 실제 joint angle·기계적 settling·접촉 상태 |

근거는 `scripts/zone_teacher.py:218–244`, `harness/zone_own_executor.py:197–216`, `harness/vision_pose_source_p03.py:195–206`, `sim/camera_robot_port.py:211–267`이다. port hold는 wheel stop과 함께 `_servo_targets`를 비우고 마지막 발행 setpoint를 유지한다. 취소 뒤 추가 target이 오지 않으면 시간이 더 지난다는 이유만으로 이전 목적지로 재개하지 않는다. 이 동작을 순간적인 physical stop으로 번역하지 않는다.

current relook는 첫 view 이후의 추가 pan을 duration0.4/settle0.6으로 queue하면서 relook 동안 control tick마다 hold를 내보낸다(`zone_pair_align.py:217–246,265–288`). source의 idle 판정은 예정 until과 ArmSequence events 유무이며 port의 잔여 interpolation 상태를 읽지 않는다. 실행 루프도 control의 발행 이후 arm events를 발행한다(`scripts/run_pair_highpose.py:225–242`).

이 때문에 원본 source fixture에서 큰 pan의 upstream target과 port의 발행 setpoint가 다르고 queue는 비어 있는 상태가 만들어진다. 이는 **known commanded-state 사이의 불일치**이며 아직 알 수 없는 physical tracking error와 다른 사실이다. 이를 바로잡는 데 measured joint feedback이 필수라는 결론은 나오지 않는다.

실제 ranked sequence는 authored own estimate `(0.2m, 0m, πrad; σxy=0.01m, σyaw=0.005rad)`와 허용된 calibration/static map에서 나온 top3 `[1500,2300,1230]`를 그대로 사용했다. 현재 첫 queue0.8s/settle0.6s, 이후0.4s/settle0.6s, 원본 PairExecution·PairCommandGuard의103개 batch 허용을 연결한 결과다. fresh gate/lease/peer와 no-fix perception은 명시한 collaborator 입력이다. 이것을 실제 로봇이 그 추정 상태에 도달한 episode라고 부르지 않는다.

| capture 시각 | view / upstream target | port가 발행한 setpoint | 남은 target / ArmSequence event |
|---:|---:|---:|---|
| 1.4s | 1500 | 1500 | 없음 / 0 |
| 2.4s | 2300 | 2300 | 없음 / 0 |
| 3.4s | 1230 | **1470** | 없음 / 0 |

표는 source의0.002s substep과 원본 `PhysicsBackend.advance_to`의 tick-before-substep 순서를 보존한 command-only 대조(반올림 clock)다. 마지막 view에서는 예정 시각과 event 소진 조건이 만족되어도 명령 값 차이240PWM이 남는다. physics callback은 시각 증가 대역이며 실제 물리 적분은 없다. plain float clock과 `backend.now`를 사용하는 추가 대조에서는 마지막 capture가 약3.6s로 달라져도1230/1470 불일치가 유지됐다. 이전0.005s/pre-control fixture의1454/224는 그 별도 순서에만 해당한다. 발행 명령 단위의 차이를 실제 camera angle이나 pixel error로 환산하지도 않는다. wheel-only 동작으로 치환한 **fixture 내부 원인 대조**는3.4s에1230, 후속 queue duration1.2s 대조는5.0s에1230을 발행했다. production 수정·새 duration 권고는 아니다. 두 대조에서도 no-fix collaborator는 그대로라 실제 관측 성공을 만든 실험이 아니다.

## likelihood가 조건으로 삼는 값과 연결

현재 HighPoseSource는 `column_model_for(servo)`의 camera record와 pan yaw, frame observer, relative edge에 provider의 `self.servo`를 사용한다(`vision_pose_source_highpose.py:50–53,85,100–102`). 추정식을 간단히 `p(image | pose, camera_command, calibration)`이라고 쓰면, 이 제어 경계의 질문은 다음과 같다.

이 provider 연결은 source를 읽어 확인한 경로다. 위 command fixture가 실제 observer/PF를 구동해 잘못된 image likelihood를 측정한 것은 아니다.

> image 시점의 camera_command로 넣은 값이, 모델이 가정한 명령 계층과 취소/보간 이력을 가리키는가?

이번 ranked 증인처럼 조건값이 upstream target1230을 가리키는데 port의 발행 setpoint 이력은1470에서 취소됐다면, 그 차이를 확인하지 않고 residual/support 실패를 “이 view에는 geometry 정보가 없다”로 분류하면 가설을 섞는다. 반대로 조건값이 맞더라도 실제 actuator의 tracking, 캘리브레이션, segmentation, 장면 ambiguity는 남는다. 명령 일치만으로 좋은 영상·정확한 pose를 인증할 수 없다.

이 결과는 R10의 frame→worker→scan→fix 구별 앞에 **의도한 view 동작이 명령 단계에서 어떻게 끝났는지**를 추가한다. frame이 계속 오고 scan이 수치적으로 적용돼도, 그 frame과 모델이 같은 command 상태를 뜻하는지는 별도 문제다. 모델의 covariance가 커졌다는 사실만으로 어느 층의 원인인지 정할 수 없다.

## 세 경쟁 설명과 가장 작은 반증

| 설명 | 기존 own-command/허용 frame에서 확인할 증거 | 반박·약화 대조 | 남는 unknown |
|---|---|---|---|
| A. hold가 진행 중 pan을 취소하고 camera-command 모델은 목적지를 유지했다 | frame capture 직전 upstream target, 보간 issued setpoint, cancel 시각/빈 target queue, 모델에 쓰인 servo 값의 불일치 | 같은 tick에 intended endpoint와 issued endpoint가 일치하고 이후 취소도 없다면 이 특정 설명 약화 | 실제 joint가 어떤 pose였는지는 이 검사로 측정하지 않음 |
| B. 명령은 일치하지만 실제 camera 관측이 모델에 충분한 기하를 주지 못했다 | command 일치 이후의 usable columns/current quality/지원 축·curvature; partial scan인지 full fix인지 | 실제 current informative fix와 support가 확인되면 “관측이 전혀 없다”는 설명 반박. 단, gate recovery와 동일하지 않음 | local support만으로 global 식별성/실제 error 보장 불가 |
| C. 명령 일치 이후에도 calibration 또는 physical response와 모델이 다르다 | 허용 RGB의 일관된 residual 패턴, issued command/load 전환과 timing. measured joints나 GT 없이 가능한 좁은 가설만 | 지목한 특정 timing/잔차 패턴이 나타나지 않으면 그 가설 약화 | 자기 영상만으로 모든 model bias와 실제 joint tracking을 완전히 분리할 수 없음 |

실제 frame/command 기록이 없으면 A부터 확인할 수 없다고 적는다. 표A의 내부 queue/setpoint는 source/repro 런타임에서 확인한 상태이며, 기존 실험의 saved trace가 이를 모두 보존한다고 가정하지 않는다. 기존 writer에서 확인된 필드와 추가 private audit 제안을 구분한다. fixture의 중간 PWM을 과거 raw의 실제 값으로 채우지 않는다. B의 weak geometry를 A의 증거로 쓰거나, A가 가능하다는 사실만으로 모든 uncertain look을 같은 결함으로 분류하지 않는다.

## repair가 검증해야 할 의미

최소 구분은 **controller가 바퀴만 멈추려는 의도**와 **arm motion까지 취소하는 revocation 의미**다. 현재 CameraRobotPort.hold의 실제 계약은 이미 wheel stop+arm 취소이며, 기존 API가 wheel-only였다고 주장하지 않는다. repair에서 의도를 분리한다면 필요한 wheel-stop과 명시적 arm revocation의 기존 안전 의미를 모두 보존해야 한다. 실제 취소 시 own-command state와 sequence completion이 그 취소를 반영하는지도 확인할 수 있다. 이 문서는 구현을 고치거나 새 controller 정책을 선택하지 않는다.

정상적인 작은 pan, 큰 양방향 pan, 의도적 abort, 같은 tick의 hold/arm 발행 순서, capture와 모델의 command 시각이 의미 있는 대조다. 시간이 충분히 길면 정상이라는 대조는 취소 원인을 분리하는 증거이지 특정 duration 상수를 정당화하는 새 calibration 결과가 아니다.

원본 queue의 연속 smoothstep `e(u)=u²(3−2u)`에서 최대 target 속도는 `1.5 × pulse_gap / duration`이다. source의 duration 미지정 기본값 `max(0.2, gap/600)`이면 이 target 속도 상한은900PWM/s다. 그러나 이번 분기의 명시0.4s와1070PWM 간격은4012.5PWM/s의 peak target 변화를 계획하며 port의2000PWM/s 보간 한도와 다르다. 이 비교는 왜 distance-dependent 기본 schedule과 hardcoded fast pan을 같은 완료 보장으로 읽을 수 없는지 설명한다. 연속 target 곡선의 식만으로 discrete tick·hold 순서의 최종 setpoint1470이나 실제 기계 오차를 계산한 것은 아니며, 새 duration이나 안전 threshold를 정하지 않는다.

진단 기록은 private controller audit에 남길 수 있다. LLM의 closed input schema에 port 내부 상태나 측정 joint 값을 추가하자는 제안이 아니다. 허용된 own issued command를 어느 계층/시각의 것으로 쓰는지 고정하는 문제이며, 연구의 정보 조건을 바꾸지 않고도 확인할 수 있는 경계다.

이 문서는 source 의미 검토다. integration은 전체 ranked sequence의31개 exact source hash 및 host-phase의39개 source hash와 각각의 재실행 JSON 동일성을 확인했고, geometry는 camera-model command 연결과 명령/physical-state 구분을 교차 검토했다. 최신 PUBLIC_DEV blocker의 causation, 무태그 vision의 전체 한계, 새로운 센서 필요성, 재관측 성공률 개선 수치로 확대하지 않는다.
