# E2E18 정렬→파지 지연: 접근 거리 하한 (v310–v311, `--approach-floor`)

## 진단 (읽기 전용, 시드 61006 한 줄기라 일반화 불가)
- v273 r52 r2 `ownmap.jsonl`: 207.6 s에 빔 밴드가 잘림(BAND_CLIPPED, end_visible=false)이고 가장 가까운 보이는 점이 전방 0.33 m. 그런데 navigate_pregrasp는 기억된 station으로 계속 전진해 222.8 s 0.12 m → 226 s 0.08 m(빔이 화면을 채우고 잘려 사라짐). 이후 turn/scan/explore 재탐색이 수백 SIM s. 즉 **잘린 관측이 이미 "너무 가깝다"를 말하는데 전진을 멈추는 규칙이 없다**.
- v302 r59(s61006): standoff는 r2가 아니라 r1에 133 s 발동(r1은 마지막 본 빔까지 ≤0.35 m 조건만으로 오발동, 133→261 s acquire_turn/scan/explore). 앞부분 결정적 궤적이 바뀌어 517.5 s 첫 파지 재현도 사라짐. 그 뒤 r1은 318 s부터 visual_servo(+0.35 전진)와 clip_recovery(−0.35 후진)가 0.8 s 주기로 번갈아 ~200 s 극한 순환(commands.jsonl 380–400 s 확인; 위치 -2.03→-2.02 m, 1 cm). r2는 arm_clearance backup/turn/verify ~170회. 어느 쪽도 standoff가 직접 막은 것은 아니고, 놓친 뒤 회복(standoff)은 근본 해법이 아니다. (다른 시드 r60 등은 미확인)
- 미수정 별도 위험: clip_recovery는 `end_visible`이 깜빡일 때마다 시도 예산(3펄스)을 pop해 초기화한다. servo 전진과 1펄스씩 상쇄.

## 토글 (기본 off)
`--approach-floor v1|v2` → v310(하한 0.30 m)·v311(0.22 m), 부모 v303(= v280 + relook_giveup)만 허용.
- 입력: 자기 RGB 최신 관측(0.45 s 이내)의 BAND_CLIPPED·가장 가까운 보이는 점 x, 자기 명령 이력. 정답 좌표·접촉·관절 측정 사용 안 함.
- 규칙: 밴드가 잘리고 x<하한이면 navigate_pregrasp의 계획 명령에서 전진 성분을 제거(hold). x<하한−0.04이면 보정된 후진 0.1 s 펄스(새 정착 프레임마다 1회, 최대 8). 20 SIM s 연속 차단되면 풀어 통과시키고 `approach_floor_released` 기록(DEV-light는 멈추지 않음).
- 기록: `own_approach_floor` 이벤트(x, 하한, 동작, rgb sha).
- 한계: visual_servo 단계의 전진(r1 순환)에는 적용하지 않음. 하한이 station 도달을 막으면 20 s 차단+해제 반복. v310은 r2 225–238 s 접근을 바꾸므로 517.5 s 첫 파지 재현은 포기. 판정: r2 own_beam_age가 207–300 s에 낮게 유지되는지, align 진입 시각.
- 효과는 시뮬레이션 미실행(확인 안 됨).

## 참고 자료 (미확인 표시)
- 시각 서보의 시야 유지: Chaumette & Hutchinson, "Visual servo control Part I/II", IEEE RAM 2006 — 기억 기반, 이번에 원문 미확인.
- 도킹 staging pose(표적에서 떨어진 접근 자세): Nav2 opennav_docking — 문서 내용 미확인.
- 구현 규칙 자체는 우리 제약(자기 RGB·명령만)에 맞춘 것이며 위 문헌을 그대로 따른 것이 아님.
