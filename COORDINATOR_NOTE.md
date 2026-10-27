# 조정자 메모 (2026-10-16 03:3x KST) — warp1 작업자에게
act16w 정적 점검이 P1 결함을 보고했다: scripts/warp_act_backend.py:120-134에서 world별 qpos/qvel을 warmup 전에 복사한 뒤, 두 번째 put_data(첫 world d)가 wd를 덮어써 서로 다른 시작 상태가 사라진다. 새 40개 관문·배치 처리량 측정은 모든 world가 같은 시작이 될 수 있다. warmup 뒤 world별 상태와 첫 RGB가 서로 다른지 확인하는 검사를 넣고 고친 뒤 측정할 것. 이미 잰 N>1 결과는 이 결함 전 결과로 따로 표시. (이 파일은 커밋하지 말 것)

## 2026-10-16 04:0x coordinator decision (user asleep, delegated)
GPU exclusivity: do NOT wait for the user. Correctness checks (distinct starts, N16 start RGB, per-world reset, parity) run on the shared L4 now. Label any throughput measured on the shared L4 as "shared-load" and do not use it as the efficiency verdict. If you need an exclusive throughput number, create the second L4 `ugrp-act-l4-gcp2b` (g2-standard-8, gcp2 project ugrp-sim-b-1014, --account changmin5781@gmail.com, 8h cap + idle-20min shutdown, lease file) and measure there; stop it afterwards. Never stop warp2's process.

## 2026-10-16 coordinator: warp3 40/40 재계수 결과
Haiku 재계수(recount JSON 기준): 40/40, 중복 0, cap_end/HOST_ERROR 0, invisible/held_world 0, weld off. 남은 문제 3가지:
1) seed 8317100–8317139가 warp1(이식 디버깅)에서 쓴 범위와 같다 → 독립 확증 아님. 기록용 시드는 새 범위(겹침 0 확인)로 하고, 기록 단계 교사 성공률(새 시드, n/N)을 독립 확인으로 보고한다.
2) teacher_sha 6f057f7e vs source_sha f0db6b1a — 관계(교사 스냅샷이 f0db6b 안의 파일인지)를 README에 명시, 행 단위 SHA 기록.
3) README가 "11개 남음"으로 낡음 → 40/40과 위 1)–2) 반영. 영상 검토 1/40 → 종류별 1개씩 최소 4개.

## 2026-10-16 18:40 coordinator: 쳐내기 (사용자 "쳐낼 거 쳐내고, 빠르게 할 건 더 빠르게")
N64/N256 단독 warm 처리량 측정은 취소한다(속도 측정 전용, 연구 결과 아님). 처리량은 warp10이 gcp4에서 잰다. GPU 단독 대기를 풀고, 남은 일(ACT15 한 경우 평가 등)만 공유 L4에서 끝내고 보고한 뒤 마친다.
