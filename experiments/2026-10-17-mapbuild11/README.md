# mapbuild11 — 긴 경로 누적 오차 진단

진행 중. PR #556, codex/mapbuild1. 기준 mapbuild10 최종 18a78adb6/7b7a2324c. 최신 main efc484ad5 지침·current_stack 적용.

1. gcp5 원본 R3 MC20 동일 사전·입자 RNG로 수정 전/후 입자 분산·ESS·가중치 분포와 수렴률을 비교한다. 계측은 resample 입력을 읽기만 하고 RNG/필터 반환값을 바꾸지 않는다. 과거 예측과 프레임별 동일성도 검사한다.
2. 별도 승인 1라운드·최대 2녹화: 기존 공개 .5m 상자/±30° 균일 무작위 시작, 서쪽 약5.65m 두 구간과 180° 회전. DEV의 위치 불확실 관문은 would_stop만 기록하고 끝까지 진행한다. 실제 물리/실행 실패는 종료한다.
3. 녹화 하나의 같은 이동량·벽 점을 OFF / nav2_defaults_v1 / nav2_rgb_field_v1으로 비교한다. 정답은 별도 예측 봉인 뒤 채점에만 쓴다. .5m 평가 구간과 끝/최대 XY·yaw·방향결합 요구표·would_stop을 보고한다.

필터 상수·문턱 변경0, 기본 동작 변경0. 시작 미수렴 진행도 명시 DEV 옵션에서만 가능하며 생산 인계/운반 자격을 부여하지 않는다. 자기 지도 관측은 기록하고 위치 보정의 정적 거리장과 분리한다. 적재/학생/LLM/실물 성공은 이번 미적재 녹화로 증명되지 않는다.

## 참고 자료

- [Nav2 likelihood_field 원본](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): p=1+sum(pz^3), 정수 stride·z_hit/z_rand 혼합. 2026-10-17 웹 원본 확인. 기존 LGPL-2.1-or-later vendor/NOTICE 유지, 새 정합기 없음.
- [Nav2 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/): 기존 σ=.2, 500–2000입자 등은 mapbuild10 고정값을 유지한다.
- [mapbuild10 최종 기록](../2026-10-17-mapbuild10/followup-results.md): 초기 R3 수렴20/20→수정5/20, 수정 XY38.78mm와 OFF43.22mm, 실제 녹화 주행2.15cm 한계.

Mac 물리/렌더/화면 앱0, gcp2 CPU0, Drive0, 모델 키 전송0. 원본 gcp5에 보존하고 Mac에는 요약/플롯/검토 프레임만 회수한다.
