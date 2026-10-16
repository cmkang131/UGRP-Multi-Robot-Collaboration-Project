# R18 — optional Gemini replay의 source 판정과 1mm 비교 범위

**조건부 P2: 실제 물리 모델 의존성인 `harness/real_geometry.py`의 변경을 source 검사에서 건너뛴다.** 정상 recorder는 이 파일의 SHA256을 보존하지만 replay는 `sim/`와 `calibration/`만 검사한다. 파일 이름이 harness 아래 있다는 이유로 제외했으나 arm collision geometry와 PWM→joint target을 구성하는 실제 의존성이다. `physical_sources_match=True`는 이 의존성의 동일성을 보장하지 않는다.

대상은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 보존된 optional `evaluate_gemini_team.py → replay_gemini_team.py`다. 현재 HIGH pair 실험, primary PAR2, cohort 분모/eligibility의 결함으로 확대하지 않는다. 실제 source drift가 있는 과거 run이나 다른 물리 궤적의 통과를 발견했다는 보고도 아니다. 구현 파일은 수정하지 않았다.

## 1. 정상 writer가 기록한 physical dependency를 reader가 누락

1. [recorder 81–83행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/evaluate_gemini_team.py#L81-L83)은 sim/harness/scripts/calibration의 `.py/.xml/.json/.png/.yaml/.yml` 파일을 기록한다. `harness/real_geometry.py`는 정상 포함 대상이다.
2. [replay 62–81행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/replay_gemini_team.py#L62-L81)의 주석은 초기 geometry와 physical integration 파일을 검사한다고 설명하지만 prefix가 sim/calibration이 아닌 파일을 건너뛴다. 결과 필드는 `physical_sources_match`다.
3. [dynamics 95–104행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L95-L104)은 harness의 link length와 servo calibration 상수를 import한다. 실제 replay constructor → multi robot XML → `build_v2_xml`이 이 문자열 geometry를 사용한다. [독립 geometry closure](boundaries.md#geometry-closure)에 구체 caller와 소스 범위를 보존했다.
4. [최종 valid 판정 258–280행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/replay_gemini_team.py#L258-L280)은 이 source predicate와 위치/명령 소비 검사를 AND로 묶고 `replay-validation.json`에 쓴다. video가 있을 때 invalid overlay도 이 valid에 달려 있다. 따라서 source gate는 단순한 사용하지 않는 metadata가 아니다.

**재현은 서로 다른 두 의무를 분리했다.** `replay-comparison-boundary-repro.py` (Mac 전달본 증거)는 원본 manifest comprehension, `record_command`, `stop_actor`, `VisualMacroExecutor`, replay의 helper와 `main()`을 실행한다. 모든 world/port/clock/snapshot은 명시적 대역이며 실제 physics·render·모델·run data는 없다. 임시 source tree에서 원본 `harness/real_geometry.py`를 기록한 뒤 `LINK_2_CM = 6.50`만 6.60으로 바꾸면 현재 파일 hash가 recorded hash와 달라지지만 checked files는 sim/calibration 2개 그대로이며 source match는 True다. 통제된 일치 snapshot의 main도 True를 내보낸다. sim 파일 변경 대조는 False다.

별도의 `replay-geometry-dependency-repro.py` (Mac 전달본 증거)는 같은 link 변경이 원본 collision capsule의 endpoint를 `.065 → .066m`로 바꾸는 것을 확인한다. 이 단일 robot template element 안의 contact 속성 contype=2/conaffinity=1은 유지된다. 실제 multi clone은 peer affinity를 추가해 2/3으로 바꾸지만 이 link endpoint를 덮어쓰지 않는다. 별도 PWM 상수 대조도 실제 joint target 식에 영향을 준다. 이는 누락된 dependency가 물리 입력임을 입증한다. **변경된 물리 모델을 실제로 실행해 다른 trajectory가 전체 valid 검사를 통과했다는 증거는 아니다.** 위치 검사가 어떤 변경을 잡을 수도 있다.

수정 방향은 recorder가 보존한 known physical dependency를 포함하는 closure를 검사하는 것이다. 최소 수정은 이 정확한 파일을 포함하고 변경 시 source predicate를 실패시키는 것, 더 보수적인 선택은 기록된 전체 source manifest를 검사하는 것이다. 후자는 reporter-only 수정도 거절하는 tradeoff가 있다. 새 코드로 재생하려는 진단 mode는 원래 source 동일성 주장과 구별해 출력해야 한다. acceptance에는 원본 geometry pass, 같은 LINK_2 변경 fail, sim 변경 fail, 그리고 정책상 제외하기로 한 reporter-only 변경의 의도된 동작을 두면 된다. 수정·과거 결과 재채점은 수행하지 않았다.

## 2. 1mm 일치가 실제로 비교하는 것

| 실제 predicate | 해석할 수 있는 범위 | 이 검사로 인증하지 않는 값 |
|---|---|---|
| cargo initial/final `position`의 Euclidean distance≤.001m | 선택된 cargo ID별 두 시점의 XYZ | yaw, 속도, stable flag, constraint state, 중간 cargo 궤적, task 성공 |
| 마지막 evaluation sample 시각의 active robot `base_xyz` distance≤.001m | 그 단일 시각의 로봇 XYZ | yaw, arm/joint 상태, 앞선 robot 궤적, 이후 passive-settle robot 상태 |
| 모든 선택된 command event 소비 | replay가 추출한 raw_action/raw_stop/explicit_stop와 보충 inferred stop의 소비 수 | 원본 로그가 완전하다는 독립 증명, 처리하지 않는 모든 event의 의미 |
| physical source subset 검사 | 현재 검사에 포함된 recorded 파일의 byte 동일성 | 위 누락된 geometry와 외부 runtime/environment 전체 동일성 |

비교 fixture의 authored final yaw/stability/speed/constraint를 바꿔도 위치를 고정하면 valid는 True다. 반대로 cargo 초기·최종 또는 robot last-sample XYZ에 1.1mm를 주면 False다. 이는 비교 함수의 coverage 대조이며 그러한 물리 상태가 실제 이 명령열에서 가능한지 검증한 것이 아니다. evaluation-only 행이 없으면 robot error dict가 비고 해당 비교는 vacuous pass다. 현재 writer의 host failure 뒤 finally가 결과를 남길 수 있어 행 존재를 일반 보장할 수 없지만, 이를 성공 run의 실제 누락이나 물리 실패라고 추정하지 않는다. `valid=True`를 task outcome의 재검증·전체 궤적의 동일성·현재 연구 trial의 admissibility로 승계하지 않아야 한다.

Cargo identity는 정상 writer가 active robot과 `small_box_01..`를 zip한 결과를 outcomes에 기록하고 replay가 같은 outcomes로 구성한다. 실제 constructor는 unknown/empty/duplicate cargo 선택을 거절하며 spec은 ID로 조회한다. 이번에 정상 writer→consumer의 identity 불일치는 찾지 못했다. arbitrary corrupted result를 넣어 새 결함으로 세지 않았다.

## 3. stop 복원은 현재 writer와 legacy를 구분

현재 runner의 `stop_actor`는 executor cancel/direct stop 뒤 raw `wait`를 항상 기록한다. 원본 writer를 실행한 fixture에서 drive raw action, explicit stop, episode-end wait가 replay에 소비되고, 같은 시각의 authored accepted-finish 후보는 기존 stop과 중복 제거되어 inferred stop 0개다. command를 끝 시각 뒤에 추가한 대조는 consumption 검사에서 실패한다.

이 결론은 모든 internal stop에 대한 포괄적 로그 완전성 주장이 아니다. 내부 guarded-drive `_interrupt`는 macro_interrupted만 남기지만, 현재 slice caller에서는 port.tick이 먼저 실행되고 이전 lease가 만료되는 경계를 별도로 읽었다. [독립 stop source challenge](boundaries.md#replay)를 참조한다. 임의 legacy event 순서나 과거 누락된 stop의 물리 영향을 이번 감사에서 재현하지 않았다. `stop()`은 wheels stop이고 `hold()`의 servo cancellation과 다르다.

## 4. 실행·보존 범위

`replay-comparison-boundary-result.json` (Mac 전달본 증거)는 10개 작은 case와 원본 writer event를 담는다. 명령은 `python replay-comparison-boundary-repro.py --repo <pin이 있는 Git 저장소>`이며 표준 라이브러리만 필요하다. script는 exact source 6개의 SHA256을 선검사하고 임시 디렉터리만 쓴다. XML 증인은 별도 script/result 및 11-source hash를 사용한다. source prefix omission은 새 finding 1개, 위치/stop/cargo 범위는 그 해석을 좁히는 대조이며 별도 결함 수로 늘리지 않는다. 실제 데이터·모델·기기·physics·렌더링·네트워크 요청은 실행하지 않았다.
