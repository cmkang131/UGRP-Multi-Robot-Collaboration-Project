# R16 — inspect 전환 중 재관측 정지가 미등록 camera 자세를 남기는 경우

**최신 source에서 공개 보고와 같은 명령·camera 계약의 연결을 재현했다.** `p45→inspect`의 첫 발행 step 뒤 `fix_gap` 재관측이 upper arm queue를 취소하면 자기 issued tuple은 `765,1991,1865,1500`에 남는다. 이 tuple은 현재 admitted camera 표에 없다. 마지막 arm 명령 뒤0.2초가 지나면 provider가 frame의 camera identity를 검사하다 fail-closed하며, 새 fix receipt를 요구하는 reset이나 알려진 camera 자세로 돌아가는 명령만으로는 이 실패가 해제되지 않는다.

R12와 같은 명령 취소 계열의 **현재 caller·실패/복구 의미 후속 검증**이다. 단순히 새 버그 수를 늘리지 않는다. R12는 upstream known target과 lower-port issued setpoint의 불일치였고, 이번에는 **upper queue가 중간에서 취소되어 upstream issued key 자체가 미등록 상태가 되는 경로**다. 새 결함이 아닌 strict camera lookup 자체를 느슨하게 만들라는 결론도 아니다.

Source는 #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`; `control-currentness.json` (Mac 전달본 증거)에서 동일했다. `interrupted-posture-result.json` (Mac 전달본 증거), `interrupted-posture-repro.py` (Mac 전달본 증거), [독립 camera 계약 검토](validation.md#posture)를 남겼다. 실제 RGB, PF likelihood/roughening, physics, lower-port interpolation, 측정 관절, raw/held-out 결과는 실행·열람하지 않았다.

## 공개 보고와 source 증거를 구분한다

[R15 최신 공개 요약](../round15/currentness.md)의 작성자 보고는 af2f7c2a 단계 실행에서 r2의 inspect 전환 중 재관측 stop, 위 중간 PWM, `UNMEASURED_V3_CAMERA_POSTURE`, 이후 `ALIGN_RELOOK_NO_FIX`를 설명한다. 이번 작업은 그 raw trace를 재생하지 않았다. 같은 tuple이 **현재 원본 함수의 합성 명령 시퀀스에서 계산된다**는 독립 연결을 확인했다. 실제 실행의 시작 시각·오차·발생 빈도나 다른 잠재 원인을 새로 측정한 것은 아니다.

## 원본 호출과 가장 작은 증인

`PairStudent._set_look('inspect')`는 알려진 p45에서0.6초 arm queue를 만든다. `ArmSequence.queue`는0.05초 간격의 ease interpolation target을 정수로 발행한다. 한편 `PairAlignRelook.tick`은 state가 align이면 arm queue 완료를 확인하기 전에 `relook_reason`을 검사한다. fix gap이면 `_begin_align_relook`이 wheel/arm hold를 요청하고 남은 upper events를 지우며 `arm.commanded`를 **이미 발행된 자기 PWM**으로 되돌린다.

합성 시각10.0에 inspect 전환을 요청하고, arm clock10.05에서 첫 target을 발행한다. control clock10.1에 fresh·initialized·low-sigma 자기 report이지만 last fix가4.0인 상황을 준다. `fix_gap`은 실제 predicate가 계산한다. Controller→arm 순서의 이 경계는 현행 host의 control-before-arm 구조와 맞지만, 이번 파일에서 host와 delayed facade 전체를 실행한 것은 아니다.

| 시점/층 | 원본 실행 결과 |
|---|---|
| 시작 p45 | issued `(3,4,5,6)=(770,1982,1876,1500)`; admitted unloaded camera key |
| inspect 예정 endpoint | `(508,2432,1320,1500)`; admitted unloaded camera key |
| 첫 arm step10.05 | `(765,1991,1865,1500)`; 서로 다른 endpoint의 실제 ease interpolation 값 |
| 재관측 trigger10.1 | `fix_gap`; 남은55개 servo event 취소, state=`align_relook_stop`, upper arm.until은10.7→10.1 |
| frame10.2 | 마지막 arm command 이후0.15초라 unsettled. camera precheck와 worker를 보류; provider failure 없음 |
| frame10.25 | 원본 settle0.2초 충족. 미등록 key→`CalibrationError`→`_fail`, worker 호출0·close1회 |
| receipt reset10.3 | last scan receipt만 무효화. 기존 provider/loc failure 유지, initialized=False |
| known inspect command10.4, frame10.65 | key 자체는 표에서 조회 가능하지만 provider가 이미 failed라 새 observation 적용 안 함 |

이 표의 값은 합성 clock과 원본 명령/lookup의 결과다. 미등록 자세에서 나온 실제 image나 카메라의 물리 위치가 아니다. 더 빠른 새 arm command가 해당 settle window 이전에 발행되는 다른 schedule까지 모두 실패한다고 일반화하지 않는다. 실제 delayed facade는 command와 capture를 capture-time 순서로 늦게 처리하므로, late delivery가 camera 의미를 새 frame으로 바꾸지 않는다는 기존 source 계약은 유지하지만 그 facade의 전체 조합 실행은 이번 재현에서 제외했다.

## 정상 대조와 실패가 지속되는 이유

- 취소 없이 같은 p45→inspect queue를 끝까지 발행하는 대조에서는12개의 중간 frame이 모두 unsettled로 보류된다. 마지막 명령 뒤 충분히 지난 known inspect frame은 camera identity 검사를 통과한다. 이는 detector/fix 성공을 뜻하지 않는다. Worker는 명시적인 대역이고 새 informative fix는 만들지 않는다.
- 이미 알려진 p45에서 hold한 뒤 fresh frame을 주는 대조도 camera identity를 통과한다. Hold 명령 자체가 항상 오류를 만든다는 설명은 기각된다.
- 같은 unknown tuple에서도0.2초 이전에는 failure가 없다. 따라서 interpolation 중 모든 frame을 즉시 오류 처리하는 설계라고 표현하면 틀린다.
- 실패 후 `begin_relocalization`과 known posture 복귀는 recovery 대조다. 원본 P03 `_fail`은 `provider.failure`와 `loc.failure`를 쓰고 worker를 닫는다. `FailClosedLoc.estimate`는 그 failure가 있는 동안 initialized=False다. P03 `on_frame`도 `after_failure` 분기에서 prediction만 하므로 단순 receipt reset은 failed worker/provider의 재초기화가 아니다.

기록의 오류 접두사는 `vision worker failed…`지만 이 증인의 `worker_calls=0`이다. 이는 카메라 표의 identity precheck에서 발생한 오류이므로, worker count0을 “아무 frame도 안 왔다” 또는 “OpenCV 추론이 crash했다”로 해석해서는 안 된다. 먼저 failure reason의 `UNMEASURED_V3_CAMERA_POSTURE`와 issued key를 연결해야 한다.

현재 camera key는 servo3/4/5/6을 `int`로 만든 exact tuple이다. ArmSequence와 P03 on_command는 이미 정수 PWM을 발행·저장하므로 fractional rounding 문제가 아니다. ±1PWM tolerance, nearest-camera 선택, 보간 fallback은 없다. Loaded 경로는 정확한 HIGH와8초의 추가 settle를 요구하므로, 이번 **unloaded inspect** 경계를 loaded transit 전체에 그대로 적용하지 않는다.

## 수정 검토의 수용 조건

목표는 재관측을 시작하면서 camera 계약이 정의되지 않은 정지 상태를 영구 provider failure로 만드는 조합을 피하는 것이다. 적절한 방법은 controller/명령/관측 수명에 따라 선택해야 하며 이번 검토에서 구현하지 않았다.

1. 재관측 예약과 팔 자세 전환 완료·취소를 함께 고려하되, 즉시 필요한 wheel stop과 emergency abort/arm 취소 의미를 보존한다. 유효하지 않은 pose에서 무조건 arm을 계속 움직이라고 제안하지 않는다.
2. 중간 자세를 임의의 known model에 끼워 맞추거나 관측을 잘못된 model로 처리해서는 안 된다. 지원된 command posture로의 guarded 전이와 fresh frame이 실제로 완료되었는지를 구분해야 한다.
3. 이미 failed provider의 회복을 지원하려면 worker ownership, failure lifecycle, clock/receipt를 갖춘 명시적인 재생성 계약이 필요하다. `failure=None`만 넣거나 `begin_relocalization`을 호출했다는 사실만으로 복구가 됐다고 보고하지 않는다.
4. 정상 transition, unsettled intermediate, known stationary hold, emergency stop, missing-key 실패, reset 후 상태를 회귀 대조로 유지한다. 통과해도 실제 camera accuracy나 carry 성공까지 증명된 것은 아니다.

최신 공개 단계가 다시 진행되는지와 새 camera identity 조합이 안정적인지는 별도 실제 증거가 필요한 후속 질문이다. 이 source 검토는 threshold를 낮추거나 GT/새 센서를 제어 입력에 넣는 근거가 아니다.

```bash
python interrupted-posture-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project
```

표준 Python과 NumPy, pinned Git object만 필요하다. 인접 helper 파일은 필요 없다. Source 함수 본문은 변경하지 않았고 selected AST로 필요한 메서드만 실행한다. PF prediction/worker·상대 status·fresh report는 명시한 collaborator이며 결과는 stdout JSON이다.
