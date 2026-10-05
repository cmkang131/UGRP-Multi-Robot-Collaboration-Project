# R12 제어 검토 — 실제 선택된 세 번째 pan이 취소되어도 view 완료로 진행

**P2: 현재 `align_relook`에서 실제 ranker가 고른 합법적인 pan 순서를 실행하면, 세 번째 view의 목표1230과 port가 마지막 발행한1470PWM이 어긋난 채 완료 시각에 도달한다.** controller·명령 guard·static geometry·endpoint·port·현행 host substep 순서를 연결한 결정론적 증인이다. 실제 joint pose, 실제 영상 오류, 발생 빈도, 공개 `SELF_UNCERTAIN`/`POSE_UNCERTAIN`의 원인은 측정하지 않았다.

고정 코드: PR #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`. 최신 여부는 `control-currentness.json` (Mac 전달본 증거), 읽거나 실행한39개 source/config SHA256은 `relook-host-phase-result.json` (Mac 전달본 증거)에 있다. 672→de03 변경은 README뿐이다. 이전의 700↔2300 초기 기전 후보(Mac 증거)는 역사적 가설/음성 대조로 보존하고, 현재 실행 가능성 판정에는 아래 actual-ranked 순서를 쓴다.

## 실제 caller와 선택 가능성

`zone_final_pair_skill.Execution`은 `b-v6g`를 선택한다. `posterior_relook=True`, `beam_relative=False`이며 RoutedM2→PairGraspRelook→PairAlignRelook의 `align_relook` 경로를 사용한다. HIGH의 controller/hover/V3 mixin은 이 `tick` 또는 `_align_relook`을 다른 동작으로 대체하지 않는다. `PairGraspRelook.tick`은 해당 상태를 `super().tick`으로 넘긴다. HIGH command guard의 추가 motion 검사는 적재 mecanum 이동 대상이며 이 열린 집게 stationary pan을 다른 target으로 바꾸지 않는다.

공개 정적 map `zone_wide_door_geometry_v3`와 현재 승인된 calibration `experiments/2026-10-03-v92-dev-pilot/calibration_dev_pilot.json`(SHA256 `398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5`)을 사용했다. raw/영상/held-out은 읽지 않았다. 합성 own estimate `(x=.2m,y=0,yaw=π,σxy=.01m,σyaw=.005rad)`와 열린 `LOOK_P20`, 초기pan1500에서 실제 `expected_observability`와 `ranked_look_pans`는 다음을 낸다.

| 순서 | pan | 현재 식의 점수 | 직전 선택으로부터 간격 |
|---|---:|---:|---:|
| 첫 view | 1500 | 96 | 0 |
| 두 번째 | 2300 | 63.461538 | 800PWM |
| 세 번째 | 1230 | 62.337662 | 1070PWM |

점수는 예상 보이는 열/경계 수와 이동 비용에 기반한 후보 점수이며 실제 정보량·accepted fix·영상 성공률이 아니다. 초기pan1500에서 만든 목록을 그대로 순차 pop한다. guard가 pan을 취소한 경우에만 재계산한다. 증인에서는 모든 guard 검사가 허용하여 목록이 바뀌지 않는다. 실제 관측에서 fix를 두 번 못 얻는 것을 명시적인 fixture 입력으로 둔다. 실제 해당 pose의 도달 기록을 확인했다는 뜻은 아니다.

## 원본 순서 전체 재현

`relook-ranked-sequence-repro.py` (Mac 전달본 증거)는 `_align_relook_stop`부터 세 view를 모두 실행한다. original `PairAlignRelook.tick/_align_relook_stop/_align_relook`, `ArmSequence`, `PairExecution.step/arm_step`, `PairCommandGuard.before_control/check`, stationary reobserve/sweep 검사, 실제 `PairGeometry`, `ZoneOwnExecutor.on_command`, 전체 `CameraRobotPort`를 사용한다. `relook-host-phase-repro.py` (Mac 전달본 증거)은 여기에 원본 `sim/final_environment_checks.PhysicsBackend.advance_to`를 연결한다. v3의 non-calibration 경로가 상속하는 loop이며 각 substep 직전에 port.tick을 부르고 clock을 다음 시각으로 옮긴다. 모델 XML의 timestep 선언0.002초를 읽었고 host0.05초, control0.1초, arm0.05초 순서를 사용했다. 물리 callback은 시간만 증가시키는 fake로 대체해 실제 physics를 실행하지 않았다.

controller 상태 전이의 일반 `set`, 유효 lease/STATUS/frame, fresh low own estimate, accepted-fix 없음은 명시한 collaborator 입력이다. renderer·plant·LLM은 없으며 robot spy는 명령 발행만 받고 측정 상태 접근을 거부한다. HIGH trace/relief wrapper와 provider/PF는 전체 실행하지 않았고, 해당 arm 경로의 비대체와 command/model 연결은 source로 대조했다.

아래 시각은0.002초 clock을9자리로 반올림한 command-only 증인이다. 실제 float 누적을 보존한 추가 대조의 시각 차이는 아래에 별도 적었다.

| view | 원본 queue 시작 / duration / settle | 첫 완료 look 시각 | `ArmSequence.commanded` / `own.servo` | port 최종 발행 setpoint |
|---|---|---:|---:|---:|
| 첫1500 | 0 / .8 / .6초 | 1.4 | 1500 /1500 | 1500 |
| 두 번째2300 | 1.4 / .4 / .6초 | 2.4 | 2300 /2300 | 2300 |
| 세 번째1230 | 2.4 / .4 / .6초 | 3.4 | 1230 /1230 | **1470** |

모든 controller/arm guard batch는 원래 명령 그대로 허용됐다. 마지막 look에서 `arm.events=[]`, `arm.until=3.4`, port pending target도 비어 있다. `frame_after_arm`은 통과하지만 합성 fix 없음 조건이 남아 `ALIGN_RELOOK_NO_FIX`로 끝난다. **이 NO_FIX 결과를 실제 vision 실패나 불일치 때문에 발생한 실패라고 주장하지 않는다.** 증명한 결함은 look 완료 때 의도한 view 명령이 실행 완료되지 않았고, 상위 command 상태와 하위 issued setpoint가 이미 달라졌다는 것이다.

## 취소가 일어나는 이유와 대조

`PairAlignRelook.tick`은 relook 상태에서 control0.1초마다 hold를 발행한다. host는 controller 명령을 먼저, arm0.05초 명령을 다음에 발행한다. ArmSequence의 .4초 smoothstep 목표들을 port가2000PWM/s로 다시 보간한다. 세 번째 pan의 마지막 target1230은 t2.8에 상위로 발행되지만 아직 하위 port에서 다 발행되지 않았다. t2.9 hold는1470에서 pending target을 삭제한다. 이후 새 pan 명령이 없어 더 기다려도1230으로 재개하지 않는다.

`CameraRobotPort.hold`의 현행 계약은 wheel stop과 **arm 보간 취소**다. 잘못된 것은 hold 자체가 아니라, 그 취소를 반복하는 relook의 예정 완료/상위 명령 상태가 취소 결과와 일치하지 않는 조합이다. `ArmSequence.commanded`는 queue 작성 순간의 미래 끝점, own/provider servo는 발행한 upstream target, port setpoint는 속도 제한 후 발행한 값이다. 어느 값도 measured joint pose는 아니다.

| 대조 | 세 번째 완료 시각 | 상위/port 명령 |
|---|---:|---|
| 현행 substep 순서의 전체3view | 3.4초 | 1230 /1470 |
| fixture에서 hold를 wheel stop만으로 치환 | 3.4초 | 1230 /1230 |
| fixture에서 추가 view duration만1.2초로 치환 | 5.0초 | 1230 /1230 |

대조는 원인 분리이며 production patch나 새 duration 권고가 아니다. 앞선800PWM 단계가 실제로2300까지 도달한 것도 내부 음성 대조라서 세 번째 단계의 시작값을 임의로 잘 맞춘 가정만은 아니다. 기존 baseline의 작은pan/양방향 큰pan 대조는 별도 보존했다.

**정밀도 정정:** 먼저 만든 `relook-ranked-sequence-result.json` (Mac 전달본 증거)는0.005초마다 port를 먼저 갱신한 뒤 control을 호출하여1454를 냈다. 실제 backend는 다음 host 시각 직전 substep까지만 port를 갱신하며 capture/hold는 보간을 먼저 전진시키지 않는다. 최종 증인은 이 source 순서와0.002초 timestep을 연결하여1470을 낸다. 같은0.005초라도 host-phase 순서를 적용하면1494가 되어 숫자의 phase 의존성을 확인했다. 독립 reviewer가 clock의 반올림을 제거하고 실제처럼 `backend.now`를 controller/command에 넘긴 `relook-floating-clock-repro.py` (Mac 전달본 증거)와 `relook-floating-clock-result.json` (Mac 전달본 증거)에서도1500/2300/1470과 두 음성 대조1230은 같았다. 다만 `arm.until` 경계의 float 비교로 완료look 시각은 약1.4/2.5/3.6초였다. 따라서3.4초를 실제 모든 실행의 고정 시각으로 인용하지 않는다. 이전 결과를 조용히 덮어쓰지 않았으며,1454를 현행 host의 정확한 값으로 인용하지 않는다. 이들은 모두 authored 입력의 command-only 수치이지 실제 run에서 측정한 관절/영상 값이 아니다.

## 영향의 경계와 수정 수용 기준

`ZoneOwnExecutor.on_command`와 provider `vision_pose_source_p03.on_command`는 look/arm target을 servo에 반영하지만 hold 때 하위 보간 취소 값을 받지 않는다. `HighPoseSource`의 observer camera callback은 `column_model_for(self.servo)`를 쓴다. 따라서 모델이 조건으로 삼는 상위 target과 실제 발행 command 계층이 어긋날 수 있다는 source 근거는 있다. 허용 RGB에서 어떤 잔차·PF 오차가 생겼는지는 실행하지 않았다. capture actuator metadata는 command 값이며 measured pose를 제공하지 않는다. 이 결과를 정상 HIGH1.2초 이동이나 현재 공개 dock/loaded-carry 실패에 그대로 확대하지 않는다.

수정은 필요한 wheel stop과 명시적 emergency hold/revoke의 arm 취소 의미를 보존해야 한다. 가능한 수용 기준은 실제 port 제한을 고려한 충분한 명령 시간, 의도적 wheel stop과 arm 취소의 명확한 분리, 또는 취소 시 command state와 completion을 함께 갱신하는 것이다. 특정 구현을 선택하거나 guard/covariance threshold를 완화하지 않았다. 같은 actual-ranked3view, 작은pan, 명시적 abort, 취소 이후 재개, 완료look의 command 일치를 구분해 확인하면 된다. 추가 measured joint feedback이나 센서를 요구하지 않는다.

중단 경로를 source로 별도 확인했다. `ZoneOwnExecutor.abort/cancel/expire_if_due`는 active pair의 `PairExecution.abort`로 연결되고, `_clear`는 상위 arm events/until, controller schedule, 아직 발행하지 않은 port command buffer를 지운다. terminal `step`은 hold를, terminal `arm_step`은 빈 목록을 반환한다. port hold는 그 아래 보간 queue를 취소한다. 이 두 층을 모두 닫는 의미가 필요하므로 wheel-only 음성 대조를 모든 abort/hold에 그대로 적용하는 수정을 제안하지 않는다. 이전에 보고한 같은-tick peer abort dispatch 문제는 별개이며 이 source 경로 확인으로 해결됐다고 주장하지 않는다.

다음 허용된 기록의 판별값은 view 선택 목록과 시작pan, queue의 duration/until, 실제 발행된 상위 arm/look, hold/cancel 시각, 완료look에서의 port command 상태다. 기존 trace가 내부 pending queue까지 모두 저장한다고 가정하지 않는다. source 증인과 saved-trace 필드를 구분한 연구 해석은 [view command provenance](research.md)에 있다.

```bash
python relook-host-phase-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project
```

이 파일은 인접한 `relook-ranked-sequence-repro.py`, `relook-hold-interpolation-repro.py`, `relook-ranking-repro.py`, `relook-pan-guard-repro.py`를 필요로 한다. exact pin이 clone에 있어야 한다. 원본 코드·정적 config만 읽으며 JSON을 stdout으로 출력한다.
