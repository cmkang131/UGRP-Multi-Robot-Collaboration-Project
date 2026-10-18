# 2026-10-18 nav gate 1 — 2로봇 wide-door navigation 물리 관문: **FAIL (acquisition)**

계약 v1 §4-2 첫 물리 관문. 결론: **배관은 물리에서 작동했지만, 목적지 획득(acquisition)에서 실패**했다.
E2E/운반 성공 주장 아님(research_result=false). 원본·SHA는 `summary.json`/`raw/`.

## 실행

- 소스 `d182b679f390eed4a7add825c6345ba538f2092d`(branch dsh/nav-gate-scene), 호스트 gcp6
  (`ugrp-act-l4-gcp6`, `ugrp-sim-f-1016`, `kcm5781kcm5781@gmail.com`), 종료 후 TERMINATED 확인.
- 장면: `s7_pair_with_solo_v7` / map `zone_wide_two_doors_final_v3`(wide door 1.0 m@y−2.625),
  **2 robots(r3 XML prune), cargo 미생성**, spawn r1 y=−2.375·r2 y=−2.875,
  scene_profile `walls_floor_contrast_v5_indigo110_s80`.
- 조건: seed 601, peer_en, nworld 1, **SIM 60 s 캡**(`--nav-sim-budget-s 60`), MJWarp noslip0.
- odometry: 같은 소스에서 측정한 캘리브레이션
  (`forward 0.0040242 m/pct-s`, `yaw 1.72804 deg/pct-s`, measured_n 60, spread<0.05%).
- 원본: VM `/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-run-4`,
  캘리브레이션 `/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h`,
  패키지 `outputs/e2e18-admin/nav-gate/evidence-run4.tar.gz`(sha256 81e8130b…).

## 결과 funnel (원본 재계수)

| 단계 | n | 거부 |
|---|---:|---:|
| world 시도 | 1 | 0 |
| nav 의존성(manifest navigation ready) | 2 | 0 |
| phase NAVIGATE(주문 선택) | 2 | 0 |
| **목적지 검출(zone_B)** | **0** | 2 |
| **wheel pulse 발행(비영)** | **0 / 1200 행** | 2 |
| **GT zone B 도착** | **0 / 2** | 2 |

- status **cap_end**(SIM 60.0 s), wall 369.1 s, 601 tick × 2 robots = 1202 관측.
- `drive_reason=no_destination` **1202/1202**, 자기중심 기억 항목 **0**.
- 이동거리 r1 0.0039 m, r2 0.0033 m(정착분), own arrival claim 0/2(GT와 mismatch 0).
- LLM: 모델 호출 2(로봇당 1), 메시지 envelope 위반 2건(`raw/message-drops.json`).
- 경계 감사: `held_world_reads=0`, top camera 0, static map 입력 없음, E2E_success=false.

## 원인 (프레임 실측)

첫 프레임(`raw/r1-tick5.jpg`)에서:
- `rgb_to_hsv`(degrees 0–360) 기준 hue 110–115 픽셀 **0**, hue 200–240 **172,245 px**
  (indigo 바닥이 화면 대부분).
- 같은 프레임을 **OpenCV H(0–180)**로 재면 hue 110–114 & S≥100 & 30≤V≤110 픽셀이 **1,583 px** 존재.

즉 `gpu_calib_v1`의 hue 110–114는 **OpenCV 단위(0–180)**로 측정된 값인데 코드는 degrees와
비교하고 있다(단위 불일치). 다만 OpenCV 단위로 고쳐도 이 장면의 **어두운 indigo 바닥이
S/V 밴드 안**에 들어와(바닥 H≈105–108, V≈90) 바닥에 발화한다 — visgoal이 GPU 렌더에서
관찰한 "바닥을 zone paint로 오인"과 같은 문제다. 36프레임 캘리브레이션은 이
scene_profile에서 측정된 것이 아니므로, 단위만 바꿔 켜면 안 된다.

## 판정

- **검증된 것**: 2로봇 MJWarp 장면(r3 prune·cargo 미생성), 측정 odometry 주입, 60 s 예산 캡,
  LLM 선택→NAVIGATE 전이, eval-only GT 재계수, 기본 off·경계 위반 0.
- **실패**: 목적지 외관 검출 0회 → wheel hold. 탐색(acquisition) 정책 부재.
- **미검증**: loaded FK·release·evaluator·ACT(gate 2+), 어떤 E2E/물리 성공 주장도 없음.

## 다음 (변경 1개씩, 승인 필요)

1. **장면 전용 외관 캘리브레이션**(eval-only 알려진 자세 6–10개, 2 Hz): 바닥 vs zone B 도색의
   degrees/S/V 분포 실측 → 프로필 prereg. (단위 변환 + 문턱은 threshold 변경이므로 사용자 승인)
2. **탐색 정책**: 목적지 미검출 시 정지 대신 자기 RGB 기반 회전/전진 탐색(문 개구부 등) 설계.
3. 위 둘을 **동시에 바꾸지 않고** 각각 게이트로 판정. 새 실행은 별도 SHA·output.

## 후속 (2026-10-18, 오프라인)

- 검출기 단위(OpenCV)·최대 연결요소·도착 가드 수정과 색 분리 실측은
  `CALIBRATION_PREREG.md` + `detector-calib.json`에 사전 등록했다.
- 실측상 스폰에서 zone B는 최대 성분 91 px(<600)라, 수정 검출기로는
  `no_destination`이 정상이다. **다음 물리 gate는 탐색 정책이 선행 조건**이다
  (위 "다음" 2번). 바닥 도색은 이번 증거로는 변경하지 않는다(prereg §8).
