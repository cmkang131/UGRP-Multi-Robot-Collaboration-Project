# nav v230-r4 prereg amendment — pre-run bugfix (2026-10-19, before any episode)

## 무엇을 바꾸지 않았나
`experiments/2026-10-17-act18/PREREG_V230_R4.md`의 동결 내용은 **그대로**다: ①/②/③ 절차,
수용표(`GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0`), FP 정의(새 SHA 재렌더 0/10 +
최종 GT 밖 claim 0), 슬롯 정의(r1=left, r2=right, 가시 성분 절반 중앙), 0.52/1.0 claim 정의 불변,
접촉의 지위(INVALID 아님, 실패 원인), pooling 금지, seed/예산/호스트/금지 입력. 결과를 본 뒤
고친 것이 아니다 — **어떤 에피소드도 시작되지 않았다**.

## 왜 추가 커밋이 필요한가 (Step B source 변경)
- prereg 커밋/push SHA: `82603017c7ce96617ad22f3ad6746f700f4f573f`
- 그 SHA로 gcp6에서 solo r1 실행을 3번 시도했으나 **모두 admission/build 단계에서 실패**했고
  **SIM tick 0**(물리 step 0, 결정 0, 모델 호출 0)이었다. 세 실패 디렉터리는 지우지 않고 보존했다:
  `runs/e2ewarp-nav-v230-r4-solo-r1-admission-error-20261019T2310Z/`(e2e-warp-batch flag 누락),
  `…-admission-error2-20261019T2313Z/`(--condition peer_en 누락), `…-solo-r1/`(아래 버그, 이어서
  `…-pre-fix-82603017`으로 보존).
- 마지막 실패 원인: `scripts/run_e2e_warp.py`의 `build_context(..., nav_spawns={r: LANE_Y[r]})`가
  레인 y(실수)를 스폰 자세로 넘겨 `TypeError: 'float' object is not subscriptable`. 이 인자는
  단독 진단에서만 쓰이는 배선이며, `build_context`는 이미 `nav_keep`으로 스폰을 필터링하므로
  **`nav_spawns` 인자를 제거**하는 1줄 수정이면 된다. 페어 run·슬롯·claim·수용표와 무관하다.
- 수정 커밋의 SHA가 **Step B source**(queue/RUN_META/result/VM HEAD 일치 대상)가 된다. 이
  amendment는 그 사실과 무수정 범위를 기록한다.

## 수정 범위 (diff)
- `scripts/run_e2e_warp.py`: `build_context(..., nav_scene=nav, nav_keep=robots)`만 전달
  (`nav_spawns` 제거, 사용하지 않게 된 `LANE_Y` import 제거) + 주석.
- 그 외 파일·상수·queue marker·시험은 `82603017`과 동일하다.

## 검증
- `tests/test_e2ewarp_nav_v230_r4.py` 외 nav gate/mode/selfnav/e2e_warp 시험 **140 passed** (수정 후).
- 단독/페어 episode는 이 SHA에서 처음 시작한다. 이전 세 실패는 수용표·n/N에 넣지 않는다.
