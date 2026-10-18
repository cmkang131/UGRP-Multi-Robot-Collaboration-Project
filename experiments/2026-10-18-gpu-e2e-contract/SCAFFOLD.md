# GPU E2E 계약 v1 구현 스캐폴드 (default OFF)

계약: [README.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/597) (PR #597, draft).
사용자 결정을 코드 경계로 옮긴 **첫 스캐폴드**다. 물리 실행·GPU 없음, POST/모델 호출 없음.

## 구성
- `harness/e2ewarp_selfnav.py` — `navigation_factory` ABI 스캐폴드(기본 OFF fail-closed)
  - **정적 지도 금지**: `static`은 주문서 메타데이터만 허용(`order_sheet`), 지도 키가 오면 예외.
  - **자기중심 기억**: 로봇 위치 (0,0) 고정, landmark(상대 거리·방위·불확실성) 목록, 재관측 시 갱신·시간에 따라 불확실성 증가. 전역 좌표 없음.
  - **자기 입력만**: `observe(OwnFrame)` 자기 JPEG, `command(now)`는 자기 발행 명령(hold PWM만), `on_messages`는 조건 채널로 전달된 것만.
  - detector(자기 RGB landmark 검출)·motion_model(자기 명령 기반 변위)은 **owner 주입식**이며 이번 스캐폴드에는 없음 → `ready=false`.
  - `accept_release_fix`는 own-memory 기반(`relocalized`+`memory_registered`, truth/held 0)만; 정적 지도 등록 요구 없음.
- `configs/e2ewarp/contract_v1_two_robot_scenario.json` — **2로봇**(r1/r2) west pickup→divider→zone B, `static_map_input=false`, English 4조건, MJWarp/noslip0, scaffold label.
- `tests/test_e2ewarp_selfnav.py` — 8 tests: default-off fail-closed, 정적 지도 키 거부, 기억 갱신·감쇠, 도착 evidence, ABI·채널, r3 거부, 시뮬레이터/GT import·access 부재, 2로봇 시나리오 스키마.

## 검증 범위
- Mac 비물리 pytest 8 passed. GPU·물리·모델 호출 0. 연구 결과 아님.
- 기존 e2ewarp(PR #570)와 합산하지 않는다. `map_correction_active` 의미는 계약 v1에서 **자기중심 기억 보정 활성**으로 재정의 제안(기존 코드는 정적 지도 보정 전제 — 통합 시 별도 수정 필요).

## 다음 (계약 승인 후)
1. owner motion model·자기 RGB landmark detector 주입(egonav/visgoal 자산 재사용, SHA 보존).
2. runner 2로봇 lane·영어 4조건·자기중심 입력 계약 연결, static map gate 제거(별도 PR).
3. MJWarp 물리 소규모 관문: west→door→zone B 실제 주행·자기 RGB 확인 → loaded FK/release/evaluator.
