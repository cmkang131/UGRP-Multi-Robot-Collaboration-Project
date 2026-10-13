OpenCV HSV inRange 공식 구현: https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html
공개 코드: https://github.com/opencv/opencv/blob/4.x/samples/python/tutorial_code/imgProc/threshold_inRange/threshold_inRange.py
기존 보정 ray-plane 투영·빔 PCA를 재사용하고, 검은 띠 근접 선택 대신 주문 색 mask와 긴 빔 방향 증거를 적용. 색 단독 픽셀은 파지 판정이 아님.
기존 색표: sim/zone_cargo.py CATALOGUE 및 sim/zone_arena.py COLORS/zone_rgba. 색상 구간과 채도185 이상으로 기존 화물·바닥·벽색 배제 단위 시험. 실제 조명/가림의 분리 성능은 단계 게이트에서 별도 측정.

Recovery follow-up: Nav2 Spin uses an angle target and a separate timeout, not a repeating short wall-time slot. https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/bt_plugins/actions/Spin/ ; source https://github.com/ros-navigation/navigation2/blob/main/nav2_behaviors/src/plugins/spin.cpp . Reuse harness/e2e_pregrasp_acquire.py settled-image scans and bounded RPP heading completion; retained old beam center is only a search hypothesis, not colored grip identity.
