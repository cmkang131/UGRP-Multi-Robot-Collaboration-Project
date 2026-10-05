# 추가7차 — #363 현재 guard/preclose 경계에서 다음에 가를 것

**우선순위는 깊게 도달한 `wait_close`의 현재 영상 증거가 왜 0이 되었는지, approach guard는 어떤 후보 명령의 어느 여유를 거절했는지 구분하는 것이다.** HIGH staged는 별도 입장 전 관측 경로로 관리한다. 같은 `guard`라는 단어를 쓰지만 서로 다른 분기라 한 임계값 변경으로 묶을 근거가 없다.

고정 source는 **`73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`**. [2026-10-03 17:01:31Z 공개 DEV 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971355260)을 GitHub API로 직접 읽었다. 작성자는 코드`3358372e`+기록head734라고 밝혔다. HIGH staged의 공개 실행 SHA는 그보다 앞선`b37c9270`이다. 메모는 공개 설명과734 소스의 연결이며 raw 독립 재현이 아니다. raw/blind/results 원본, 연결된 replay artifact·TensorBoard·영상을 열지 않았고 새 물리·LLM·학습 실행이나 구현·게시도 하지 않았다.

## 공개 보고가 닫은 것과 아직 닫지 못한 것

| 경로 | 작성자 공개 보고 | 이 검토의 해석 한계 |
|---|---|---|
| `raise_high` (`3358372e`) | 양쪽 opening look7.8초에 LOOKED, 합류통과. elapsed7.45초, 명령200/199, 측정53/27. r1 `PAIR_COLLISION_GUARD`8.7초, r2 `PARTNER_ABORT` | old rendezvous 실패가 현재 첫 blocker라는 설명은 철회. 명령/측정 누계는 첫 충돌 guard의 검사 branch·wall·clearance를 알려주지 않음. r2 reason은 별도 충돌 측정이 아닌 abort 전파일 수 있음 |
| `raise_high_align` (`3358372e`) | wait_close54.1초 도달, elapsed52.85초, 명령1443/1261, 측정200/147. `BEAM_UNCERTAIN → PREGRASP_NOT_READY` | 가장 깊은 합법 controller prefix. physical close/lift/carry를 검증한 것은 아님 |
| 같은 close의 공개 자체 replay | beam std0.019m/0.024rad, age2.3초. floor grasp frame의 빔색 점0(필요60), 직전standoff9911 | 해당 입력에서 현재 partial-support 요구를 충족하지 못한다는 구체적 근거. 모든 허용 alignment/pose에서 영구적으로0임을 이 숫자만으로 증명하지는 않음 |
| HIGH 두 staged (`b37c9270`) | high_hold60초/1200번, carry_leg150초/3000번 `gate_ok=false`, 명령0/0·측정0/0, std_xy≈0.21>.05. loaded 오류 해소 | 시작전 관측/입장 미도달. high carry controller나 loaded transport가 실패한 실행으로 세지 않음. gate retry 수와 실제 observer/scan 시도 수는 다름 |

734의 [staging132–157,318–333](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L132-L157)는 ordered pre-close→close→raise 이력을 넘긴다. 이전 loaded=False finding을 재개하지 않는다. floor staged 두 방식은 폐기되고 normal opening look을 보존하는 align entry로 바뀌었다. 공개 P03 미시작은 후속 실행의 상태이며, provider 내부가 P03의 fixed-delay wrapper를 재사용하는 사실과 혼동하지 않는다.

## H1 — wait_close는 기억한 beam의 작은 sigma보다 현재 partial-support 부재에서 멈췄다

이 가설은 **공개0-point 보고와 source가 구체적으로 지지한다.** v98 [HighController._wait_close88–100](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L88-L100)는 grip view를 별도로 log-only 처리하면서 `preclose_check`를 유지한다. [highpose CommandGuard330–333](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L330-L333)는 기존final guard에 v98 frame gate만 바인딩한다.

[final preclose126–145](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_guards.py#L126-L145)의 순서는 다음과 같다.

1. pose fresh·initialized/finite·gate·sigma·motion settle·valid frame·camera command 일치가 선행한다.
2. `beam_track.estimate`가 None이면 `BEAM_UNCERTAIN`을 기록하고 끝낸다.
3. beam estimate가 있을 때만 stationary whole-beam/wall clearance를 계산한다.

따라서 공개 reason이 이 source event를 가리킨다면, 그 순간의 직접 원인은 **stationary wall clearance 음수**가 아니며 앞의 pose/frame precheck도 이미 통과했다. `PREGRASP_NOT_READY`는 상위 conjunction의 공통 실패명이다. `pregrasp_fix_rejected`라는 로그 이름만 보고 fix 실패로 다시 분류하면 안 된다. beam-only 실패 때 그 로그의 `failed_checks`는 비어 있을 수 있다.

[RestingBeamTrack169–193](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_beam_track.py#L169-L193)는 track 존재/segment/age/sigma 통과 뒤에도 **현재 frame에서 MIN_POINTS 이상**을 요구한다. 그 후95% footprint support를 검사하고, [GraspRangeBeamTrack129–139](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_grasp_entry_v6c.py#L129-L139)는 cross-section≥28mm 및 연속된 색 band를 요구한다. 이전standoff의9911점은 현재frame의 점 수를 대신하지 않는다. 이 patch 검사는 새 pose/age/sigma를 갱신하지 않고 기존 가설과의 현재 일관성만 확인한다.

| 최소 판별관측 — 같은 robot/segment의 마지막 accepted standoff와 첫 wait_close를 연결 | 관측값이 배제하거나 남기는 가설 |
|---|---|
| 두 frame의 id/hash/SIM 시각, anchor time·segment, own issued PWM, frame에 붙은 issued camera PWM, 마지막 arm command와 settle 시각 | 다른 grasp epoch/카메라 명령의 frame을 비교했다는 bookkeeping 가설을 가른다. 측정 관절을 요구하지 않음 |
| point pipeline의 단계별 수: decoded beam-colour mask→calibrated valid sampled rays→downward rays→positive plane intersection→range<2.5m→footprint support→cross-section | 전체색 mask도0이면 colour/visibility 앞단. 색은 있지만 projection 뒤0이면 ray/plane/calibration 쪽. 점은 충분하고support/span에서 거절이면 identity/track consistency 쪽. 공개 “0점”이 어느 count인지 먼저 고정 |
| 기존 accepted beam estimate+불확실성, 고정calibration과 **자기 명령**으로 각 descent pose에 투영한 예상 visible support; 같은시점ownRGB count와 대조 | nominal camera posture 자체가 보지 못하는지, 예상으로는 보이는데 extraction이 잃는지 구분. 예상visible은 시뮬레이터 정답이나 실제 visibility 측정이 아니므로 uncertain support/모델오차 한계 보존 |

source docstring도 [runtime73–78](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L73-L78)에 floor pose에서0/18 beam points가 FOV 안이라고 적은 이전 기하 설명을 갖고 있다. 이는 현재 RGB0 보고와 정합적이지만 여기서 그 기하를 새로 계산하거나 전체 허용 오차범위의 불가능성을 증명하지 않았다.

**다음 결정:** 관측 범위가 겹치지 않는 것이 확인되면 설계자가 “어느 기존 합법 view에서 얻은 어떤 stationary-beam 증거를, 어느 own-command/시간/불확실성 범위까지 close-clearance에 쓸 것인지”를 명시해야 한다. 현재RGB patch가 필수라는 현 계약을 유지한다면 실제 그 patch를 획득할 수 있는 결정 시점/허용 자세가 있어야 한다. 이 메모는 zero-count를 통과시키거나 grip monitor를 다시 mandatory로 만들거나 실제 관절/접촉/GT를 넣는 구현을 제안하지 않는다. sigma/timeout/wall margin 변경만으로 현재0점이60점이 되지는 않는다.

## H2 — approach의 충돌 guard reason은 실제 기하 여유와 추정 불확실성·경로 검사 범위를 구분하지 못한다

**아직 source-consistent 가설이며 공개 누계로 원인은 미확정이다.** [PairCommandGuard756–794](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_guards.py#L756-L794)는 arm/look recheck의 bounded wait 소진, arm transition/plan rejection, base `motion_clear` 실패를 모두 `PAIR_COLLISION_GUARD`로 만든다. 첫 actor의 이 reason과 partner abort만으로 실제 접촉, 벽에 대한 nominal overlap, sigma-only tightening 또는 잘못된 threshold를 선택할 수 없다.

특히 새 obstacle-normal sigma는 [lookaround151–164](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_lookaround.py#L151-L164)의 own `_sweep_steps` 동안만 `guard.hint`에 붙고 `finally`에서 지워진다. pair command의 [sweep_guard118–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_guards.py#L118-L119)는 별도 `PairGeometry`를 만든다. **초기 look 통과가 이후 접근 명령의 동일한 clearance 검증 통과를 뜻하지 않는다.** 이것을 즉시 버그라고 부르거나 새 margin을 모든 phase에 확대하라는 권고도 하지 않는다.

| 첫 거절 한 건의 최소 판별관측 | 판별/배제할 가설 |
|---|---|
| absolute+relative time, controller/driver state, `step` vs `arm_step`, 아직 발행 전인 candidate command list, prior own issued PWM, 실제 guard class/policy·loaded/reobserving, first failed branch | arm sweep와 base move와 cumulative recheck timeout을 구분. 현재 command receipt만 보면 rejected candidate가 hold로 바뀌어 사라질 수 있음 |
| arm이면 실제 transition_samples의 limiting PWM/body part/wall, raw clearance·base/residual·position/yaw reserve·최종clearance, 필요한 경우 current/end만 아닌 중간sample | nominal shape/path가 이미 막히는지와 uncertainty reserve에서만 막히는지 구분. 시작/끝이 clear여도 중간경로가 clear라는 보장은 없음 |
| base면 command duration/gain/turn-sign sample, chassis와arm 각각의 limiting clearance, interval reserve. 같은 **진단 전용** nominal-sigma 대조 | malformed duration/command, chassis collision envelope, arm envelope, curved/straight path tightening을 구분. nominal clearance도 음수면 sigma만 원인이라는 가설 배제. nominal이 양수여도 실제 안전이나 margin 과도함은 증명되지 않음 |
| recheck이면 same target/phase 동안 `waited_s`, last_wait, full transition result, 기존 nominal query 결과, pose freshness/std와 gate change | 단순instant geometric reject와 관측 대기예산 소진을 구분. 여유시간만 늘리는 처방의 근거 여부를 결정 |

기존 [transition_diagnostic336–366](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_own_guards.py#L336-L366)는 own estimate/issued PWM/static map만으로 limiting sample·raw/margin clearance를 낸다. 다만 **실제 검사한 guard 인스턴스/branch와 같은 기하**에 적용해야 한다. 그 helper 하나로 loaded whole-beam/base-motion 검사까지 전부 설명됐다고 하지 않는다. [motion_clear103–147](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_geometry.py#L103-L147)는 command expiry까지 양쪽 turn 부호/straight 및 sample-gap reserve를 따로 검사한다.

현재 source는 pre-guard candidates를 `_OwnPort.commands`에 모았다가 guard 결과만 반환하며, collision reason에 모든 diagnostic field를 함께 남기지는 않는다. 따라서 기존 공개 요약의명령200/199를 곧 거절 후보의 재현 가능한 원장으로 부르지 않는다. 기존 owner-held audit에 값이 있으면 먼저 그 한 경계를 요약하고, 없는 값은 “없음”으로 표시해 다음 허가된 DEV의 필요한 receipt만 정한다. 이번 검토에서는 원자료를 열거나 새 실행을 요구/시작하지 않았다.

## H3 — HIGH staged의 gatefalse는 carry 실패 전에 관측 공급·선별·정보성을 나눠야 한다

**확인된 보고:** loaded 이력 복원 뒤에도 두 HIGH stage가 입장전std≈.21, accepted measurement0에서 멈췄다.1200=60/.05,3000=150/.05는20Hz gate retry와 일치하며, 독립된1200/3000번의 유효한 image measurement를 의미하지 않는다. `.15` per-axis prior의radial std는 `sqrt(.15²+.15²)≈.212`이므로 공개0.21은 그 prior와 양립한다. 이것은 raw PF covariance를 독립 측정했다는 뜻이 아니다.

[HIGH staged spec98–109,initialization306–333](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L98-L109)는 opening look을 건너뛰고 정상 admission을 유지한다. [HighPoseSource57–61,83–106](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/vision_pose_source_highpose.py#L57-L106)는 loaded이면 issued HIGH·high_since+HIGH_SETTLE까지 요구하고 parent frame pipeline을 호출한다. 그 다음 accepted scan에는 feature/residual support·prior support·curvature 등 정보성 판정이 별도로 있다.

| 최소 관측 | 0 measurements의 분기를 가르는 법 |
|---|---|
| existing provider `frames`, `unsettled_or_uninitialized`, `worker_calls`, `rejected_frames`, `after_failure`, failure reason; delivered command time/high_since/settled의 최초 전환 | worker_calls=0이면 detector 성능부터 탓하지 않는다. startup delay/settle/loaded-HIGH/calibration/failure 관문을 먼저 확인. 전체60/150초를 정상 HIGH settle 대기로 설명하려면 계속 unsettled가 되는 근거가 필요 |
| worker 호출 후 image valid/rejection, valid informative column 수, first candidate scan의 판정 | frame gate 거절과 “유효frame이나 특징 없음” 구분. aggregate measured0만으로 두 원인을 합치지 않음 |
| attempted scan의 support/curvature/accepted·informative, report last_fix_t/last_valid_obs/delayed delivery 시간 | scan 시도했지만 informative fix로 인정하지 않은 경우와 accepted fix가 전달되지 않은 경우를 구분. 좁은 posterior나 높은ESS만으로 새 절대fix를 인정하지 않음 |

기존 [provider record294–307](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/vision_pose_source_p03.py#L294-L307)는 counts/failure/worker/stats/lifecycle를 제공한다. [scan wrapper35–47](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_final_pair_scan.py#L35-L47)는 informative가 아닌 경우 measured를false로 바꾸고 이전fix time을 보존한다. `last_fix_quality`는 마지막 accepted fix용이므로 실패한 모든 scan의 상세 rejection이 자동 저장됐다고 가정하지 않는다.

이 branch는 HIGH 상태를 만들기 위한 teacher setup의 효력과 controller 입장 가능성을 분리하기 위한 진단이다. staged true-spawn prior mean/teacher-held 상태를 E2E 입력이나 성공 근거로 승격하지 않고, gate를 통과시키려 prior sigma를 좁히는 제안도 하지 않는다.

## 다음 단계 순서와 끝내는 기준

1. **기존 close 경계 한 건부터:** 마지막accepted standoff→firstwait_close의id/시간/명령과 단계별point counts를 같은robot/segment로 묶는다. 공개BEAM_UNCERTAIN·0points의 위치가 확인되면 “covariance/벽margin 문제”와 “현재 증거가 없는 readiness 계약”을 분리할 수 있다. 증거 없는 pose extrapolation을 새 성공판정으로 쓰지 않는다.
2. **guard는 병렬로 한 건:** 첫PAIR_COLLISION_GUARD의candidate·branch·limiting raw/reserve를 요약한다. nominalsigma대조는 원인 분류용으로만 쓰고 실행허가로 전환하지 않는다. 기존 source와 다르면 먼저 입력/instance/time 불일치를 고친 뒤 판단한다.
3. **HIGH는 입장 전 파이프라인만:** counts의분모를 나눠 최초 소실경계를 찾는다. 입장 가능성이 확인되기 전 cap연장/후속carry성능비교를 하지 않는다. 이 확인 없이 “HIGH carry 자체 불가능”이라고 결론내리지 않는다.

현재 진도를 막은 것이 공개 summary에 이미 세부적으로 나오는 close branch인지, 아직 큰reason으로뭉친 approach branch인지에 따라 소유 작업을 좁힐 수 있다. 순수기하 합성숫자를 추가해도 어떤 실제 branch였는지를 식별하지 못하므로 이번에는 별도 toy model/새 실험을 만들지 않았다. 후보 관측은 기존 합법 자기RGB·정적map/calibration·자기issuedcommands·실제status/message의private audit 요약에 한정한다. 다른 로봇의정답pose·측정관절·접촉·강제grip gate를 추가하지 않는다.

## 소스 보관/보고 범위

exact734 source snapshot: `review-notes/tmp/blocker734-source/harness/`의 highpose runtime/frame_gate/lookaround/staging/provider와finalguards/vision/beamtrack/grasp-entry. publication_currentness의 `review-notes/round7-pr363-734/`에는 runner와관련tests도 있다. 관련 source/검사문은 읽었지만 전체 회귀검사 통과나 공개DEV 결과를 독립 실행했다고 보고하지 않는다. root의 신규게시원고는 수정하지 않았으며 게시용 내용의 채택/통합은 publication_currentness가 담당한다.
