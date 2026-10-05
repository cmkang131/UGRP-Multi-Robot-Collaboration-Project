현재 DEV의 다음 판별 — #363 고정 `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`의 source와 [17:01:31Z 공개 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971355260)만 연결했습니다. 공개 실행은 접근/align `3358372e`, HIGH staged `b37c9270`입니다. raw·영상·replay artifact·TensorBoard·결과 원본은 열지 않았고 새 물리·모델·구현도 없습니다.

**staged loaded 이력 복원과 opening look/합류 통과를 인정합니다.** 과거 rendezvous를 현재 첫 blocker로 반복하지 않습니다. 가장 깊이 간 wait_close의 현재 영상 증거, approach guard의 첫 거절 후보, HIGH staged의 입장 전 관측 공급을 각각 구분하는 것이 다음 작은 진단입니다.

| 공개 보고 | 지금 알 수 있는 것 | 아직 알 수 없는 것 |
|---|---|---|
| raise_high: 양쪽 absolute SIM7.8초 LOOKED/합류, 이후 PAIR_COLLISION_GUARD | 과거 opening/rendezvous 단계를 넘어감 | 첫 거절 branch·candidate·wall·raw/reserve clearance |
| align: wait_close absolute SIM54.1초, BEAM_UNCERTAIN→PREGRASP_NOT_READY; 현재 점0/필요60, 직전 standoff9911 | 현재 partial-support 부재가 source와 구체적으로 연결됨 | 모든 허용 pose/오차에서 영구적으로 관측 불가능함 |
| HIGH: loaded 오류 해소, 명령/accepted measurement0, gatefalse1200/3000 | 입장 전 미도달 | worker 미호출·frame 거절·scan 비정보성 중 어디인지 |

이는 저자 보고이며 독립 물리 재현이 아닙니다. 아래 관측은 기존 합법 입력/소유자가 가진 private audit의 한 경계 요약 제안이며 새 센서·GT·실험 실행 지시가 아닙니다.

## 1. 작은 beam sigma와 현재 RGB의 점0은 양립합니다

v98 [wait_close88–100](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L88-L100)는 grip view를 log-only로 두면서 preclose_check를 유지합니다. [final preclose126–145](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_guards.py#L126-L145)는 pose freshness/gate/sigma·settle·valid frame·issued camera 일치를 검사한 뒤 beam estimate가 None이면 BEAM_UNCERTAIN으로 끝내고, estimate가 있어야 stationary wall clearance를 계산합니다.

**공개 reason이 이 event를 가리킨다면** 그 순간 직접 거절은 stationary wall clearance 음수가 아닙니다. 상위 PREGRASP_NOT_READY나 `pregrasp_fix_rejected` 이름만으로 pose-fix 실패라고 분류할 수 없습니다. [RestingBeamTrack169–193](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_beam_track.py#L169-L193)는 기억한 track의 age/sigma가 유효해도 **현재 frame**의 최소 점·footprint support를 요구하고, [GraspRangeBeamTrack129–139](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_grasp_entry_v6c.py#L129-L139)는 cross-section/연속 band를 확인합니다. 직전9911점은 현재0점을 대신하지 못합니다.

| 같은 robot/segment의 마지막 standoff→첫 wait_close에서 요약할 것 | 판별할 가설 |
|---|---|
| frame id/hash/time, anchor epoch, own issued PWM, frame의 camera PWM, 마지막 arm command/settle 시각 | 다른 epoch·명령의 frame을 비교한 bookkeeping 문제인가? |
| 색 mask→valid sampled ray→downward ray→positive plane intersection→range→footprint→cross-section 단계별 count | 공개0점이 색/시야 앞단인가, projection/calibration 단계인가, track consistency 단계인가? |
| accepted beam estimate와 불확실성, 고정 calibration·자기 명령으로 예상한 각 descent pose의 visible support, 같은 시점 RGB count | nominal view도 못 보는가, 예상으로는 보이는데 extraction이 잃는가? 예상치는 실제 visibility 측정이 아님 |

두 view의 지원 범위가 겹치지 않는다면 설계자는 어느 **합법 view의 stationary-beam 증거를 어느 시간·명령·불확실성 범위까지** close-clearance에 쓸지 명시해야 합니다. 현재 patch를 요구하는 계약을 유지한다면 그 patch를 실제로 얻을 시점/허용 자세가 있어야 합니다. 이 관찰은 점0을 통과시키거나 grip monitor를 강제 gate로 되돌리거나 contact/joint GT를 추가하라는 제안이 아닙니다. sigma/timeout/wall margin만 바꿔0점을60점으로 만들 수는 없습니다.

## 2. PAIR_COLLISION_GUARD 한 이름으로 실제 접촉이나 과도한 sigma를 확정하지 않습니다

[PairCommandGuard756–794](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_guards.py#L756-L794)는 arm/look recheck 대기 소진, arm transition/plan 거절, base motion_clear 실패에 같은 reason을 씁니다. 공개 명령200/199·측정53/27은 이 분기를 알려주지 않습니다.

새 obstacle-normal sigma hint는 [own sweep151–164](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_lookaround.py#L151-L164) 동안만 적용되고 지워집니다. pair의 [별도 geometry118–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_guards.py#L118-L119)는 같은 검사가 아닙니다. 초기 look 통과가 접근 guard 통과를 보장하지 않으며, 이를 즉시 margin 버그로 부르거나 전 phase에 확장할 근거도 없습니다.

첫 거절 한 건에서 다음만 가르면 됩니다.

- 실제 guard class/policy, controller state, step/arm_step, **발행 전 candidate**, prior own PWM, loaded/reobserving, first failed branch.
- arm이면 limiting intermediate PWM/body part/wall, raw clearance와 base/residual·position/yaw reserve의 분해. 시작/끝만 clear여도 중간 경로는 다를 수 있습니다.
- base면 duration/gain/turn-sign sample과 chassis/arm 각각의 limiting clearance·interval reserve. nominal-sigma 대조는 원인 분류용이며 실행 허가나 실제 안전성 증거가 아닙니다.
- recheck이면 같은 target/phase의 waited_s·transition 결과·pose freshness/std. 순간 기하 거절과 관측 대기예산 소진을 구분합니다.

[기존 transition_diagnostic336–366](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_own_guards.py#L336-L366)은 이런 raw/reserve 분해를 제공하지만 실제 검사한 인스턴스·branch와 같은 기하에 적용해야 합니다. published command receipt에는 이미 hold로 바뀐 거절 후보가 빠질 수 있으므로 누계가 곧 완전 후보 원장이라고 가정하지 않습니다.

## 3. HIGH의 gate retry 수는 독립 image measurement 수가 아닙니다

1200=60/.05,3000=150/.05는20Hz gate retry와 일치합니다. per-axis .15 prior의 radial std≈.212도 공개 .21과 양립합니다. raw covariance를 새로 측정한 결과는 아닙니다. HIGH staged는 opening look을 건너뛰며 [provider57–106](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/vision_pose_source_highpose.py#L57-L106)는 매 frame을 parent pipeline에 넘기며, loaded 상태의 observer 시도에는 issued HIGH/high_since·settle 요건도 적용됩니다.

| 최소 분모/전환 | 어디서0이 되었는가 |
|---|---|
| frames, unsettled/uninitialized, worker_calls, failure/after_failure, command/high_since/settled 최초 전환 | worker0이면 detector 성능보다 startup/settle/calibration/failure 관문부터 확인 |
| worker 호출 뒤 frame rejection·informative column 수·candidate scan | 유효 frame이 없는가, frame은 유효하지만 특징이 없는가 |
| attempted scan support/curvature/accepted·informative, last_fix/last_valid_obs/delivery 시각 | scan이 fix로 인정되지 않았는가, 인정됐으나 전달되지 않았는가 |

[provider record294–307](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/vision_pose_source_p03.py#L294-L307)의 counts와 [scan wrapper35–47](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_scan.py#L35-L47)의 informative 판정을 분리합니다. last_fix_quality가 모든 실패 scan의 rejection을 저장한다고 가정하지 않습니다. 입장 전 진단을 carry controller 실패로 세거나 gate를 통과시키려 prior sigma를 좁히지 않습니다.

이 세 표는 현 소유자가 가진 audit에서 처음 소실된 한 경계를 요약하기 위한 것입니다. 없는 receipt는 없음으로 표시하고 필요한 항목만 다음 허가된 DEV에서 정하면 됩니다. 전체 과거 문제를 다시 열거나 새 대규모 실행을 선행조건으로 늘리지 않습니다.
