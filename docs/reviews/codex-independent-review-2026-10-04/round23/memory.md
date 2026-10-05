# R23 · #217 기억 비교의 조건 선택과 실제 provider 경계

**새 버그 0개다. 현재 지원된 v3 비교는 전체 기억 ON/OFF가 아니라 기억을 이용한 재관측 결정의 비교다.** main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 workflow → CLI → 제어기 선택 → 공통 safety → provider 생성 경로를 source로 읽었다. 등록 문서·구현의 이 범위에서 서로 다른 안전 제어기를 matched 조건으로 잘못 선택하는 불일치는 찾지 못했다. 코드나 합성 fixture를 실행하지 않았고, 실제 코호트·점수·영상·원자료도 열지 않았다.

## 왜 이 경로를 읽었는가

공식 [#217](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/217)은 같은 seed의 기억 ON/OFF 비교와 baseline 분리를 요구한다. R19에서 본문이 R1과 같았고 당시 open임을 확인했다. R2 제어 검토 (Mac: `evidence/review-notes/round2-control.md`)는 memory 기반 단일 물체 배달을 아직 깊게 읽지 않은 클러스터로 남겼다. R12의 현재 pair 재관측 명령, R17의 HIGH trace 저장과 이번 optional M1 memory 비교는 서로 다른 caller다. R1의 과거 v2 보고나 v3 미확인 상태를 새 실험 결과로 다시 인용하지 않는다.

등록된 `zone-m1-owncam-memory-v3-run`은 `configs/simulation_workflows.json:660–670`에서 `scripts/run_m1_owncam_memory_v3.py`로 연결된다. 설명은 여전히 DRAFT/coordinator 등록 필요다. 실제 CLI도 `REGISTERED`가 아니면 거부하고, matched 두 조건에는 `ugrp.owncam_safety.v3` 계약을 요구한다. test split은 추가 source freeze 검사를 거친다. 이 검사를 source로 읽었다는 뜻이며, 현재 등록 파일이 존재하거나 실제 실행이 승인·완료됐는지는 검사하지 않았다.

## selector에서 소비자까지

| 경계 | 확인한 source 계약 | 읽을 수 있는 의미 |
|---|---|---|
| 조건 → 클래스 | runner `CONDITIONS`, `controller_class`, `run_episode`는 `off`를 `M1OwnCamDeliveryOffV3`, `memory_v3`를 `M1OwnCamDeliveryMemV3`로 고른다. 원래 `base.M1OwnCamDelivery`를 임시 교체하고 `finally`에서 복원한다. frozen M1 runner는 `run()` 안에서 해당 이름을 import한다. | 공식 단일 episode 호출 경로에서 선택 클래스가 실제 constructor 이름에 연결된다. 동시 호출·thread 안전성이나 예외 실행을 시험한 것은 아니다. |
| OFF → 공통 제어기 | `M1OwnCamDeliveryOffV3`의 유일한 자체 설정은 `memory_look_enabled=False`다. 같은 v3 constructor, memory factory, 목표/조작/slot 확인 및 공통 mixin을 상속한다. | OFF에도 추적·회피·안전용 기억이 있다. 전체 기억 제거 조건으로 해석하지 않는다. |
| flag → 달라지는 결정 | v3 controller는 flag를 leg에 넘긴다. OFF는 coverage에 따른 관측점·pan 생략을 하지 않으며, `LookPolicyV3`는 고정 재관측 trigger/full look 경로를 고른다. ON은 memory look policy와 계획된 관측 선택을 사용한다. | 재관측 선택이 달라지면 이후 입력·상태·행동도 달라질 수 있다. 같은 초기 seed를 모든 시각의 동일 관측·궤적으로 확대하지 않는다. |
| 공통 safety → look policy | `LegDriverMemV3(LegSafetyV3, LookPolicyV3, ...)`에서 현재 불확실성/일관성 검사가 선택 policy보다 앞선다. look 시작·명령의 정적 충돌 검사, fix와 도착의 새 관측 요구는 두 조건에 공통이다. controller의 초기화 제한도 공통 mixin이다. | OFF가 flag 하나로 공통 안전 검사를 제거하는 코드 경로는 이 범위에 없다. 물리 안전성·공분산 보정·실제 도착 성공을 입증한 것은 아니다. |
| episode → 기본 provider | frozen `run_m1_owncam.run()`의 constructor는 map/params/seed/skill 등을 넘기지만 `pose_source`나 `landmark_provider`를 주입하지 않는다. v3의 기본 `memory_inputs`는 `OwnCamPoseSourceV3`와 `TagLandmarkProvider`를 만든다. | 이 공식 CLI의 matched 두 조건은 기본 임시 태그 경로다. runner의 `interim, tag provider` 라벨과 일치한다. 현재 markerless HIGH에 자동 연결되지 않는다. |
| 별도 provider 주입 | 직접 constructor의 `pose_source` 인자에 provider를 주면 `GuardedPoseProviderV3`가 감싸고, 부모의 `memory_inputs`는 새 기본 pose를 만들지 않는다. `SharedPoseDelivery`는 own-camera provider 계약을 확인하고 같은 객체를 보유한다. accepted/settled 및 consistency 진단이 guard 입력이다. | 주입 가능한 API와 공식 CLI가 해당 provider를 선택하는 것은 다르다. 기존 provider 테스트는 가짜 비전/지연 입력의 테스트 source로만 읽었으며 실행하지 않았다. 실제 markerless 성능·전체 provider 적합성은 미검증이다. |

## 비교와 인수의 남은 경계

`docs/design/2026-09-27-owncam-memory-v3.md:7–17`도 같은 구분을 명시한다. `off_legacy`와 `memory_v2`는 과거 reference이고 matched 효과 추정에서 제외한다. 각 CLI 호출은 선택한 prereg의 같은 split/episode 구조와 student 설정을 읽고, episode의 `seed`를 world와 controller로 전달한다. 두 matched 조건의 time contract도 같다. 다만 서로 다른 두 호출이 실제로 같은 prereg/episode를 사용했는지 교차 검사하는 대조군 실행기는 아니다. 초기 입력 alignment는 같은 등록 입력을 선택하는 계약으로 읽으며, 두 조건의 실제 완료·짝 맞음·시간/둘러보기/오판 집계를 이번에 확인한 것은 아니다. 같은 safety/tracking 구현을 유지해도 look policy는 이후 관측, receipt/history와 행동을 바꿀 수 있으므로, 동일 exposure 아래의 고립된 직접 효과 비교라고 부르지 않는다. 그런 실제 경로 변화나 효과 크기도 측정하지 않았다. `comparison_role`, `memory_look_enabled`, `safety_contract`의 기록은 의도한 조건을 설명하며 효과 측정 결과를 대신하지 않는다.

#217의 표식 없는 최종 입력 요구를 수용하려면 선택된 provider가 실제 비교 caller로 들어갔다는 source/설정 연결과 그 provider에 맞는 공통 비교 계약이 필요하다. 이 메모는 새로운 코호트 실행이나 provider 교체를 요구·승인하지 않는다. 이미 등록된 연구의 완료 여부도 판단하지 않는다. 기존 v3 문서가 명시한 제한을 새 결함으로 세지 않고, R19의 ‘설계 전체 미검증’에 이번 좁은 source 연결만 추가한다.

## 증거 범위

- **source-only:** workflow 항목, CLI admission/selector/복원, M1 constructor call, v3 class/flag, 관련 shared adapter·safety·provider. 파일별 hash와 읽은 구간은 `memory-comparison-source-manifest.json` (Mac 전달본 증거)에 남겼다.
- **실행 없음:** import, fixture, pytest, 실제 등록 파일 admission, 물리·render·모델 호출, 코호트 비교와 과거 결과 재채점을 하지 않았다. 읽은 테스트가 통과한다고 주장하지 않는다.
- **기존 coverage:** R1 issue 상태·R2 미검토 목록·R12/R17와 caller 차이를 확인했다. 전체 저장소의 memory 관련 모든 호출자를 읽었다는 주장은 아니다.
