# E2E18 visual_servo↔clip_recovery 진동 방지 (v312–v313, `--clip-hysteresis v1`)

## 진동 집계 (읽기 전용, VM3 `~/ugrp-sim/runs/*/raw/robots/*/commands.jsonl*`)
방법: 좌우·회전 없는 mecanum 전·후진 펄스가 부호를 바꾸며 ≤1.2 s 간격으로 ≥6회 이어진 사슬(근사 판정; 다른 모듈의 번갈이도 섞일 수 있음). 시드 61006은 v270–v303, 61007–61010은 v302만 있음.
- 진동 있음(로봇별 사슬 길이 합, SIM s): v271 r1 152(+r2 12; r51/r52는 같은 원본), v272 r2 468, v274 r2 523, v278 r1 236·r2 376, v295 r1 217, **v302 s61006 r1 546·r2 3, s61007 r1 182·r2 122, s61010 r1 51**.
- 없음: v270, v273, v275–v277, v296, v298, v303(r62), v302 s61008·s61009.
- 즉 v302 5개 중 3개에서 재현(r59 r1 546 s는 사슬 길이 합이며 실제 맴돈 구간 ≈200 s 이상). v303 r62는 없음. 모든 사슬이 clip_recovery 때문인지는 확인 안 됨(사슬 안의 상태 이름은 commands.jsonl에 없음).

## 원인 (코드)
`e2e_carrier_approach.advance`: 매 프레임 clip_recovery → 아니면 `fine=True`(visual_servo, 정렬 단계가 전진). 정렬 단계 전진 → 밴드 잘림 → clip_recovery 후진(−0.35, 0.1 s) → `end_visible` 한 프레임이 보이면 clip 예산을 pop하고 즉시 서보 재진입. 예산이 깜빡임마다 초기화되어 소진되지 않는다.

## 표준 방법 (출처는 기억 기반, 원문 미확인)
모드 전환 채터링 방지: 히스테리시스·최소 체류 시간·디바운스(Liberzon, Switching in Systems and Control, 2003; Nav2 복구 행동의 제한 재시도). IBVS 시야 유지: Chaumette & Hutchinson, IEEE RAM 2006. 구체 수치는 우리 것.

## 토글 `--clip-hysteresis v1` (기본 off, 부모 v310→v312, v303→v313)
`harness/e2e_clip_hysteresis.py`. 입력은 자기 RGB 프레임·자기 명령 이력뿐.
- 진입 디바운스: 연속 2개의 새 잘림 프레임이어야 후진 펄스.
- 해제 히스테리시스·최소 체류: 펄스 뒤 서보 진입(`clip_hysteresis_hold`)을 end_visible 연속 3프레임 + 펄스 후 1.6 SIM s까지 보류. 12 s 넘으면 해제하고 `clip_hysteresis_released` 기록(DEV-light, 멈추지 않음).
- 예산: end_visible 연속 6프레임일 때만 3펄스 예산 초기화(`own_clip_recovered`). 깜빡임으로는 초기화 안 됨 → 3펄스 소진 후엔 clip_recovery가 개입하지 않고 서보가 계속 진행.
- 번들: v312 = v310(v303 + approach-floor v1) + 토글, v313 = v303 + 토글(approach-floor 없음, 517 s 파지 경로 유지 의도).
- 한계: 효과는 시뮬레이션 미실행(확인 안 됨). 서보 전진 자체는 막지 않으므로 소진 후 잘린 채 전진하는 동작은 남는다. 517 s 재현은 앞 구간이 같을 때만 기대(clip 개입 시점이 바뀌면 달라짐).
