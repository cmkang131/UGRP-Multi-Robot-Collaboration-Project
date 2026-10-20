# pairact P1 cand-2: peer_yield 이식 여부 확인 결과와 대체 후보 제안 (코드 없음)

## 1. 확인 결과: `beampair_peer_yield_v1`은 이미 MJWarp r13 스택에서 켜져 있습니다

이식할 것이 없으므로 이 브랜치에는 코드 변경이 없습니다. 근거는 다음과 같습니다(모두 git 객체에서 직접 확인).

- 정의 위치: `origin/claude/beampair7:harness/beampair_peer_yield.py`(`MODE='beampair_peer_yield_v1'`). 기본값은 `scripts/run_beampair1.py`의 `run(..., peer_yield='off')`입니다.
- r13 adapter `d354468a`는 `835ccef2`(beampair7 CPU 40/40 소스)의 후손입니다. `835ccef2..d354468a` 사이 diff는 `harness/beampair_teacher.py`와 `scripts/run_beampair1.py` 두 파일뿐입니다. 따라서 `harness/beampair_peer_yield.py`는 그대로 있고, `run_beampair1.py`가 `PeerYieldMixin`을 teacher에 붙입니다.
- r13 root `05046e9d:scripts/warp_flow_episode.py`(약 330행)의 beampair flow 호출이 `peer_yield='beampair_peer_yield_v1'`을 하드코딩합니다. `rendezvous='peer_rendezvous_v2'`, `approach_repair='beampair_approach_v2'`, `wall_layer='beampair_wall_clear_v1'`도 같은 방식입니다.
- 그래서 r13 관문(37/40)은 peer_yield가 켜진 상태의 결과입니다. 다만 stack manifest(`teacher-gate-stack-manifest-r13.json`)의 `stack_values`에는 이 값이 기록되지 않습니다. 기록 누락이므로 P1 사전 등록에서 명시해야 합니다.
- teacher 브랜치(`claude/beamact5-r2-t`, `fe6858ec`)에는 peer_yield 코드가 없습니다. adapter와 root 쪽 기능이기 때문입니다.
- 증상도 맞지 않습니다. peer_yield는 두 로봇이 0.15–0.20 m에서 서로를 막는 *접근 교착*을 고친 기능입니다. MJWarp r13에 남은 실패는 world 27(정렬 단계)과 world 37(정적 여유 부족)이라 교착과 관련이 없습니다.

## 2. 대체 후보 제안 (구현하지 않음, 오너 결정 사항)

### cand-2' `search26_align_refresh_v2`: r14 정렬 refresh의 발동 조건 수정
- **근거**
  - r13diag world 27 FAIL에서는 17.6 s부터 `alignment_axes_blocked`가 91회 기록되고, stale red_1 여유 때문에 pulse가 hold로 바뀝니다.
  - r14(`origin/claude/beamact5-flake2`, teacher `f1cf1926`)는 단독 실행에서 2/3을 통과했지만, 실패한 회차에서 `align_refresh_begin`이 0회였습니다. 훅이 한 번도 발동하지 않았습니다.
- **발동하지 않은 원인 가설 (코드 근거, 실행 확인은 안 함)**
  - r14 훅은 `remembered_blockers(truth, rid, goal_set_log[-1]['candidates'], …)`를 부릅니다.
  - 이 함수는 후보 중 `reason=='blocked_goal'`인 *목표 자세*만 보고 stale 장애물을 찾습니다(`sim/grasp_act_reobserve.py:17-36`).
  - 그런데 정렬 단계에서는 선택된 stance가 feasible이라 이미 정렬 중입니다. 정렬을 막는 것은 목표 자세가 아니라 *pulse 경로*입니다. 그래서 목표 자세 기준으로는 막는 장애물이 없다고 나오고, blockers가 비었을 가능성이 있습니다.
  - r14 문서는 다른 원인을 추정했습니다("관측이 memory에서 만료"). 두 가설 중 어느 쪽이 맞는지는 [확인 필요]입니다. r14diag rep3 원본의 `recovery_log`와 `search20_log`를 보면 가릴 수 있습니다.
- **제안 내용** (default off, 새 상수 없음)
  - 정렬 pulse가 거부된 tick에, 현재 pose 기준으로 pulse를 막은 stale 관측을 고릅니다. 조건은 `seen_t < t`이면서, 패딩된 원이 `radius` 안에 들어오는 cargo와 wall입니다.
  - 이것을 targets로 삼아 기존의 bounded reobserve를 시작합니다(`VIEW_S`, `RETREAT_S`, `MAX_ENCOUNTERS`를 그대로 씁니다).
  - 판정식은 `remembered_blockers`와 같습니다. 바뀌는 것은 입력뿐입니다: 목표 자세 대신 현재 pose와 pulse 끝점을 넣습니다.
- **cand-1과의 관계**
  - cand-1(직사각형 가드)은 같은 증상의 *형상 쪽* 원인을 다룹니다.
  - cand-2'는 *기억 여유 쪽* 원인을 다룹니다.
  - tournament에서 둘을 분리해서 측정할 수 있습니다.
- **기반**: r14 teacher `f1cf1926`(r13 + align refresh v1) 위에 올려야 하므로 r13 단독 기반이 아닙니다. tournament에 넣을지는 오너가 결정합니다.

### 다른 선택지 (참고)
- **cand-2'' world 15 재포함 arm**: r13에 `search26_log_ring_v1`(P0 브랜치)을 켜고, world 15를 분모에 넣은 채로 실행합니다. 목적은 처리량과 stall만 보는 것이고, 정책 개선 후보는 아닙니다. 91자세 재계산 비용은 그대로라 planning wall cap에 다시 걸릴 위험이 있습니다.
