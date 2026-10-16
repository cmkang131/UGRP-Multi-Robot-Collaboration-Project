# R15 — HIGH 중간 checkpoint가 부착 beam의 검사 형상을 잃는 경계

**새 제어 결함:** HIGH 중간 정지는 집게를 열거나 다시 잡지 않지만, `seg`를 올리는 순간 guard가 사용하는 `beam_grasp_confirmed`가 False가 된다. 잡은 시점 receipt가 이전 segment에 남아 있기 때문이다. HIGH의 별도 `held_by_command()`는 계속 True여서 다음 운반 준비를 유지하지만, 공통 command guard는 부착 beam 전체를 제외한 형상으로 명령을 검사한다.

현재 비교 대상은 #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`이다. 원래 `de03fe87d08879abefaa7dac67c7ff313df5df89` 증거도 보존했다. `current-frontier-66ff.json` (Mac 전달본 증거), [원본 MRO 독립 확인](validation.md#currentness), [66ff 관련 메서드 동일성](validation.md#currentness), `checkpoint-attachment-66ff-result.json` (Mac 전달본 증거), [실제 geometry 소비자](validation.md#geometry)를 분리해 남겼다.

이것은 부착물 검사를 빠뜨리는 source 경계다. 실제 물리 충돌, 실제 beam 낙하, 해당 합성 위치가 현행 route에서 발생했다는 증거는 아니다. 최신 공개 단계 실행은 carry 전에 끝났으므로, 그 실패를 이 checkpoint 결함으로 설명하지 않는다.

## 두 가지 수명 기준이 갈라지는 곳

| 실제 source 경로 | 유지/검사하는 identity | checkpoint 전후 결과 |
|---|---|---|
| `PairGraspRelook._grasp` | 유효한 자기 frame과 issued close 뒤 `beam_grasp_receipt['segment']=self.seg` 생성 | 처음 receipt의 segment는0 |
| `HighController._grasp` | 위 원본 메서드를 실행한 뒤 `grip_closed_epoch=grip_epoch` 설정 | 현재 grasp epoch1에서 closed 확인 |
| `HighController._wait_lower` 중간 GO callback | `seg += 1`, 새 fix boundary/재관측 시작; open/regrasp 없음 | segment1, grasp epoch1, gripper1500 유지 |
| `HighController.held_by_command` | 같은 grip epoch에 닫았고 현재 gripper가1500 | True 유지 |
| `PairGraspRelook.beam_grasp_confirmed` | receipt 존재 **및 receipt.segment==현재 seg** 및 gripper<2000 | False로 바뀜 |
| `PairCommandGuard.carrying_beam` | 위 inherited property를 그대로 읽음 | False를 geometry에 전달 |

HIGH의 실제 `controller_class`는 이 property를 재정의하지 않는다. 사이의 `HoverConfirm`, `V3Controller`, `GraspViewLogOnly`와 frame-gate binding, blind adoption에도 checkpoint receipt를 갱신하는 hook은 없다. 독립 source 검토가 실제 base list의 C3 순서와 receipt 쓰기 위치를 확인했다. 66ff에 추가된 relook, carry-align, final-veto도 이 identity를 변경하지 않는다.

기존 낮춤/열기/재파지 방식에서는 segment별 receipt가 자연스럽다. 현재 HIGH checkpoint는 **동일한 command-held attachment를 다음 route segment로 넘기는 방식**이므로, 경로 segment 수명과 파지 epoch 수명이 달라졌다. 이 차이를 단순히 새 시각 증거가 없다는 뜻으로 읽으면 안 된다. v98의 grip 영상은 승인된 log-only 정책이고, 이번 문제는 그 정책이 보존한 명령 기반 부착 가정을 geometry 소비자까지 유지하지 못하는 것이다.

## 원본 receipt·barrier·guard의 작은 재현

`checkpoint-attachment-repro.py` (Mac 전달본 증거)는 pinned Git object에서 원본 메서드 본문을 읽는다. close command receipt → 현재 log-only grasp 경로 → `PairGraspRelook` receipt 생성 → 실제 fixed-enum `lower@0` GO → HIGH checkpoint callback을 연결한다. 다음 `lower@1`도 같은 방식으로 대조한다.

- 정상 원본 `_grasp` 뒤에는 receipt.segment=0, grip epoch1, `held_by_command=True`, `carrying_beam=True`다.
- 첫 checkpoint 뒤에는 seg1/receipt.segment0, 그 다음에는 seg2/receipt.segment0이다. 두 경우 모두 집게1500과 grip epoch1은 유지되지만 geometry attachment flag는 False다.
- 원본 HIGH `CommandGuard.check`와 공통 `PairCommandGuard.check`를 호출하면 동일한 명령의 `motion_clear(..., loaded=...)` 전달값이 True→False로 바뀐다.
- segment를 바꾸지 않은 대조는 True를 유지한다. 실제 issued open 처리 대조는 receipt를 지우고 두 holding 표현 모두 False가 된다. 새 segment에서 **별도로 승인된 새 grasp를 가정한** 원본 receipt 생성 대조는 True로 돌아온다. 마지막 대조는 원인을 분리하기 위한 것이며 재파지를 수정안으로 강제하는 것이 아니다.

fixture는 valid frame/close, 완료된 자체 HIGH 명령 경로, 각 lower-ready 보고를 명시한 합성 입력으로 준다. 실제 물리 grasp/lift/운반 prefix를 실행하지 않는다. floor PWM은 current static v3 IK로 독립 계산한1269/2052/2494/1500을 쓰고, 이후 HIGH에 도달한 issued command를 선언한다. 시각 log-only 함수와 PF reset은 collaborator다. guard의 pose 입력은 유효하다고 고정하고, geometry 함수는 전달된 flag만 기록한다. **이 파일만으로 충돌 검사 결과까지 검증했다고 주장하지 않는다.** 실제 geometry 차이는 다음 별도 증거가 담당한다.

R14 checkpoint 시간/pose-guard fixture는 `beam_grasp_confirmed=True`를 선언한 collaborator였다. 그 결과는 admission/timeout 조합에 유효하며 이번 부착 identity 경계를 검증하지 않았다. R14를 전체 HIGH checkpoint 또는 부착물 geometry 검증으로 확대하지 않는다.

## 빠진 flag가 실제 검사 결과를 바꾼다

[geometry 소비자 재현](validation.md#geometry)은 현재 static map, long_beam catalogue, v3 command FK와 실제 `PairGeometry` 및 v98 start-relief wrapper를 사용한다. 역할 end_neg, issued HIGH/closed, σxy=.01m·σyaw=.005rad에서 divider1 앞의 합성 own pose를 **정지 시 beam reserve가+21mm가 되도록 분석식으로** 정했다.

| 동일한 pose·HIGH의 raw-contract-valid 명령 | 부착 flag=False | 부착 flag=True |
|---|---|---|
| forward+.10, duration.15s | 허용 | whole-beam sphere의 reserve가−7mm여서 거부 |
| forward−.05, duration.15s | 허용 | 허용 |
| stationary, duration.15s | 허용 | 허용 |

현재 `.10` 명령이 실제 route/calibration에서 발행됐다는 주장은 아니다. 작고 합법적인 authored 명령에서 **검사 허용 여부가 달라질 수 있음**을 보여 준다. 부착 beam을 포함할 때만31개 beam sphere가 검사되고, body-only는 약566mm의 여유로 통과한다. 양 조건의 motion pad는4mm로 같아 sigma/회전 padding 변화가 아니라 beam 포함 여부가 차이를 만든다. `loaded=True`의−7mm는 보수적 reserve 위반이지 실제 접촉 측정이 아니다.

v98 start-relief는 두 flag의 차이를 복구하지 않는다. 시작 reserve가 양수여서 기존 겹침을 완화할 조건도 없다. 새66ff final-veto는 **terminal** endpoint의 dispatch를 차단하며, 정상적으로 살아 있는 checkpoint endpoint의 잘못된 attachment flag를 고치지 않는다. 정적 route planner의 whole-team envelope는 별도 방어지만, 그 존재가 모든 실제 추정 오차/issued command의 online geometry 검사를 대체한다는 증거는 없다.

**범위를 정확히 한정한다:** `PairCommandGuard.check`의 지역 변수 `loaded = not self.approach`는 attachment flag와 별개다. loaded uncertainty profile과 progress 검사는 계속 적용된다. 모든 guard가 unloaded가 되거나 모든 motion이 무검사로 허용된다는 주장이 아니다. 빠지는 것은 attached-beam 형상이며, HIGH posture requirement도 같은 attachment property에 의존한다. 이번 geometry 증인은 정확한 HIGH를 사용했으므로 별도 posture 위반을 만들지 않았다.

## 수정의 수용 기준

route segment가 바뀌어도 **같은 실제 issued-close epoch가 유지되는 동안 부착물 안전 가정이 사라지지 않아야 한다.** open/cancel/새 grasp epoch와 실제 재파지의 수명은 여전히 구분해야 한다. 과거 receipt의 frame 시각을 새것처럼 갱신하거나, 새 RGB grip gate/센서를 필수로 만들거나, geometry reserve를 낮추는 방식은 이 문제의 해결 조건이 아니다.

최소 회귀 대조는 다음과 같다: 정상 checkpoint를 연속 통과해도 beam 포함 유지, 실제 open 뒤 해제, 새 grasp epoch의 재확립, stale/failing pose와 abort/hold 규칙 보존, 같은 stationary/toward/away geometry의 허용 차이 정상 유지. 정책이 부착 여부를 보수적으로 unknown으로 분류한다면 unknown을 body-only로 자동 축소하지 않는 계약도 필요하다.

## 재현과 현재성

```bash
python checkpoint-attachment-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project --ref 66ff0978a817caa949d2d738b51d7ae89dd17e71
```

표준 Python만 필요하다. 원본 production file은 쓰지 않으며 결과는 stdout JSON이다. de03/66ff 양 결과의 행동 값은 같고 runtime의 observation-only logging 추가로 source hash만 구분된다. Geometry fixture는 NumPy와 문서에 적은 frozen helper가 따로 필요하다. Source-only staged `wait_carry` 진입 코드에도 receipt가 없지만, 현재 직접 HIGH entry는 PARKED로 명시돼 있다. 이를 활성 caller 결함으로 승격하거나 정상 grasp→checkpoint 증거와 합쳐 실제 stage 결과 원인으로 세지 않는다.
