# 18차 비교 경계

## Replay

Optional Gemini replay의 `valid`는 source predicate와 선택된 위치·명령 소비의 결합이다. 새 source 누락은 [주원고](replay.md)에 집중하고 다음 항목을 별도 버그로 늘리지 않는다.

| 실제 비교 | 확인한 대조와 해석 |
|---|---|
| Cargo 초기/최종 XYZ | 각 시점 1.1mm 차이는 거부. 그 사이 궤적·yaw·속도·안정·constraint까지 동일하다는 뜻은 아님 |
| 마지막 평가 표본의 robot XYZ | 1.1mm 차이는 거부. 평가 표본이 없으면 빈 error dict의 기본값으로 이 항은 통과. 성공 run의 실제 누락을 발견한 것은 아님 |
| 필터된 command event 소비 | Episode end 뒤 명령은 거부. 선택된 events를 모두 소비하는 것과 원본 기록의 완전성은 다른 주장 |
| 현재 writer의 stop | Actual raw drive·explicit stop·episode-end wait를 소비하고 같은 시각 inferred stop은 중복 제거. 모든 legacy 순서나 모든 내부 stop을 검증한 것은 아님 |

모든 snapshot/clock/world는 명시적 대역이다. 일치 XYZ를 두고 다른 yaw나 constraint를 넣은 대조는 predicate의 비교 항을 밝힐 뿐, 해당 물리 상태를 실제로 만들었다는 증거가 아니다.

## Geometry closure

누락된 `harness/real_geometry.py`는 dynamics가 import하는 link length와 servo 변환 상수를 담는다. Actual replay constructor→multi XML→`build_v2_xml` 연결을 source로 확인했고, exact 원본 식에서 LINK_2_CM 6.50→6.60이 collision capsule endpoint 0.065→0.066m로 바뀌는 것을 계산했다. 별도 servo deviation 대조는 joint target을 `−π/2000 rad` 바꾼다. 실제 joint나 trajectory 변화량은 측정하지 않았다.

단일 robot template의 contact 속성 2/1과 multi clone의 2/3은 구분한다. Clone은 peer affinity를 더하지만 해당 link endpoint를 덮어쓰지 않는다. Fixture는 정확한 한 XML element와 원본 target 함수를 계산했으며 전체 scene 생성·컴파일·physics를 실행하지 않았다. 따라서 물리 dependency임은 뒷받침하지만 전체 replay 판정의 물리적 우회까지 주장하지 않는다.

현재 좁은 caller에서 새 외부 XML/mesh 누락은 찾지 못했다. 선택적 warehouse tag 경로는 이 caller에서 활성화되지 않는다. 모든 optional asset과 runtime 환경의 완전한 closure를 증명한 것은 아니다.

## Reference assets

별도 communication-study / D3 reference 경로는 실제 `prepare_assets → prepare_manifest/preflight → run_trial → build_rgb_skill_backend` 중 자산 read까지 검증했다. Authored 모델/reference bytes와 임시 source/config를 쓰고 scene 생성 직전 sentinel로 멈췄다. 비자산 environment·bundle·audit·runtime-limit gates는 대역이므로 full study admission을 인증하지 않는다.

원래 catalog 13개와 backend 입력 11개는 모델/reference identity를 유지한다. 차이 2개인 training report도 catalog에서 hash/존재 검사를 받는다. 모델만 변경, 모델과 내부 manifest를 함께 변경, reference 변경, training report 삭제는 child consumer 전에 차단됐다. D3 local-assets/descriptor evidence를 제거한 경우도 preflight에서 거부됐다. 마지막 대조는 consumer 실행까지 가지 않는다.

Reference JPEG는 시작/끝 magic bytes만 둔 합성 입력이다. 실제 이미지 decoding·학습 모델의 추론 schema·scene/model 실행은 검증하지 않았다. 같은 자산 hash가 의미하는 비교 범위는 [연구 메모](research.md)로 연결한다.

## Currentness

공식 GitHub ref 읽기는 2026-10-04 09:02 UTC에 #363 `66ff0978`, #371 `a009112f`, 직접 main `b23fc087`를 확인했다. 관련 일부 파일이 main과 #363에서 같다는 사실도 optional Gemini replay가 현재 HIGH 실행 caller라는 뜻은 아니다. 각 source pin과 실행 범위는 그대로 유지한다.
