# T04 can 단독 접근·파지·방출 후보

can 전용 registry·자기 RGB 판정·명령 상태 전이를 추가했다. **오프라인 구현이며 완료된 물리
실행은 0회**다. 기존 색 상자 M1 API·원본 지도/시나리오·봉인 소스·CI 설정은 수정하지 않았다.
등록된 can factory는 독립 opt-in 진입점이며 기존 executor에 can 배송을 자동 허용하지 않는다.

## 변경

- `harness/can_skill_registry.py`: can .038 m × .050 m / .080 kg / grasp z=.024 m / role `any`.
  네 통신 조건은 같은 class·profile·상태 enum을 쓴다. T03의 red/green 구현을 가져오지 않는다.
- `harness/wrist_can.py`: 해시 검증한 자기 robot_cam JPEG를 직접 판독한다. 자기 발행 PWM과
  v3 카메라/팔 계산으로 바닥 원통 중심을 맞추고, 같은 색 상자·누운 can·바닥·가림·복수 후보를
  구분하지 못하면 `unknown`으로 둔다. box의 색/팔 threshold로 can 성공을 간주하지 않는다.
- `harness/zone_can_skill.py`: 상대 접근→낮추기→닫기→서로 다른 두 높이에서 들기 확인→holding→
  C 안 자기 위치 확인→낮추고 열기→새 바닥 RGB 확인. 실제 `arm/mecanum/hold` 명령을 출력한다.
  외부 pose 입력은 없으며 등록된 자기 RGB provider에 같은 JPEG와 자기 명령을 전달한다.
  입력/위치 불확실·정적 충돌·명령 중 이동·timeout에서는 정지한다.
- `tests/test_zone_own_executor_can.py`: 실제 판정과 전이를 호출하는 합성 JPEG 검사.
  독립적으로 그린 원통/반례의 알려진 좌표를 라벨로 쓴다. MuJoCo 렌더/동역학 결과가 아니다.
  기존 glob으로 CI에 자동 포함되므로 CI 파일 변경은 없다.

최종 v3 command IK는 catalogue 교사의 기존 .155 m 반경을 거절한다. 이 후보는 .200 m,
grasp .024 m, lift .080/.100 m를 명시한다. 이는 명령 계산이며 **실제 파지 보정은 미검증**이다.
기존 box carry view에는 can 전체가 보이지 않아, 보이는 아래 rim을 두 들기 높이에서 확인하는
보수적 가설을 쓴다. 손가락 가림·tilt/slip·조명에 대한 실제 판별 성능은 별도 인수 대상이다.

`released_visual`은 자기 영상의 방출 후보이고 `delivery_success`는 항상 `None`이다.
실제 navigation·접촉·C 착지/배송 심판을 이 모듈의 fake 결과로 대신하지 않는다.
색은 개체 ID가 아니므로 s6 specific item/타 물건 사이 접근·서쪽 의무·pivot 순서를 지원한다고
표시하지 않는다. role `any`의 동서남북 world heading을 같은 로컬 제어로 검사했다.

## 검증과 재현

정확한 명령·결과·소스 해시는 `verification.json`, `dependencies.json`을 따른다.
로컬 pytest는 #328에 따라 **호스트 잠금 없이** 실행했다. 처리량/실시간 성능 측정이 아니다.
최종 묶음은 **234 passed, 1 skipped, 107 subtests passed**이며 can 검사는 50개다.
skip은 명시적으로 제외한 기존 물리 host 검사 1개다. guard의 물리 step/실제 모델 worker/네트워크
시도는 모두 0이다. 변이 4/4가 assertion으로 검출됐다. 제출 전 main `26545c24`를 fast-forward로
받았고 can 의존 소스/입력 해시가 모두 같았다. 변경된 CI 수집기의 can glob도 1개 검사로 재확인했다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m pytest -q tests/test_zone_own_executor_can.py
"$PY" -m pytest -q -p tests.pose_provider_no_physics \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_boundaries.py tests/test_zone_own_executor_guards.py
"$PY" -m pytest -q tests/test_m1_owncam.py tests/test_zone_own_perception.py
"$PY" experiments/2026-09-30-cap-t04-can/mutation_check.py \
  --output /Users/changmin/projects/ugrp/outputs/cap-t04-can/mutation-NEW-ID
```

변이는 별도 Python 프로세스 안에서만 적용한다. 원통 검출 제거, 들기 증거 무시, 방출 증거 무시,
다른 카메라 허용의 네 경우가 각각 assertion으로 실패해야 한다. import/collection 오류는
검출로 세지 않는다. 원본 소스와 기존 결과를 변이로 덮어쓰지 않는다.

개발 중 같은 보라색 직육면체·누운 can의 잘못된 통과를 실제 반례로 발견했고 경쟁 모양 투영을
추가해 거절했다. 최종 결과와 구분되는 초기 44/48/49개 검사도 `verification.json`에 이력으로 남긴다.
첫 기존 회귀 묶음에서 `test_team_host_feeds_each_executor_only_its_own_camera`가 포함된 것을
놓쳐 MuJoCo 모델/데이터 및 렌더 초기화를 시도했다. `invalid CoreGraphics connection`으로
constructor가 실패해 `host.run(3.)`에는 도달하지 않았다(143 passed, 1 failed).
이 범위 선택 실수를 보존하고 이후에는 저장소의 `tests.pose_provider_no_physics` 플러그인으로
해당 물리 검사를 제외하고 물리 step/실제 모델 worker/네트워크를 차단했다.
최종 물리 후보의 인수 재생은 수행하지 않았다.

## 인계와 남은 일

[PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)에 정상 1 + 부재 실패 1, **2×900=1,800 SIM초**,
staging 포함 시계·입력/소스 고정·공용 잠금·raw·판정·TensorBoard 검사를 적었다.
현재 CLI에는 can E2E 어댑터가 없다. 코디네이터의 새 opt-in workflow/번들 연결, 실제 spawn부터의
자기 RGB 위치 추정, can 하중 navigation, rim 가시성·파지·방출·심판 검증이 남았다.
학습/보정 반복과 추가 실패 셀 비용은 미산정이다. 단위검사를 새 물리 TensorBoard 성과로 변환하지 않았다.

GitHub에는 코드/소형 기록을 보존한다. primary outputs의 검사 로그는 로컬 보관이며 원격 백업이 아니다.
Google Drive는 사용하지 않는다. 이 PR은 draft로 제출하고 병합하지 않는다.

## 참고 자료

- [요구 감사 #302](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302),
  병합 `09081b3c46f0d51e02ef625e4be8c7d6f6e67963`: 정적 요구/거리와 미실행 task 배정.
- [로컬 offline 잠금 분리 #328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/328),
  병합 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`: 이 작업의 시작 main.
- [CI #300](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/300),
  병합 `e6cc2a8850f35dd8e29cb20a7615c7e0901f795f`: CI 설정 소유 범위, 이 PR에서 수정 없음.
- [T03 #325 조율 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/325#issuecomment-5913422877):
  미병합 형제 PR이며 의존/성과 합산 없음; 공통 색 상자 파일/registry는 변경하지 않음.
- [T04 요구](../2026-09-30-scenario-capabilities/TASKS.md#t04--can-단독-접근파지방출),
  [원본 요구/정적 거리](../2026-09-30-scenario-capabilities/REQUIREMENTS.md).
