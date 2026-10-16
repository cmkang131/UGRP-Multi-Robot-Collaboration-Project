# 색 범위 침범률 (PNG 원본)

OpenCV HSV: H 0–179, S/V 0–255. 적응형 범위는 가장 느슨한 절대 하한으로 검사.
81개 측정 범위에 대해 바닥 9,437,184 픽셀·벽 39,321,600 픽셀 전체를 집계.
무채색 256종의 빈도와 실제 cv2.inRange 결과를 곱해 계산했다. 조명/JPEG/주변 대비 검증은 미실행.

| 검출 범위 | 코드 근거 | HSV 범위 또는 RGB 식 | 바닥 침범 n/N (%) | 벽 침범 n/N (%) |
|---|---|---|---|---|
| literal:harness/camera_goal_transport.py:31 | harness/camera_goal_transport.py:31 | `[([20, 70, 50], [40, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/camera_goal_transport.py:164 | harness/camera_goal_transport.py:164 | `[([40, 60, 30], [90, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/camera_short_transport_student.py:47 | harness/camera_short_transport_student.py:47 | `[([3, 105, 45], [24, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/camera_short_transport_student.py:50 | harness/camera_short_transport_student.py:50 | `[([20, 70, 50], [40, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_box_identity.py:16 | harness/dispatch_box_identity.py:16 | `[([80, 125, 35], [102, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_navigation_map.py:16 | harness/dispatch_navigation_map.py:16 | `[([3, 170, 45], [35, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_navigation_map.py:119 | harness/dispatch_navigation_map.py:119 | `[([80, 125, 35], [102, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_pair_navigation.py:384 | harness/dispatch_pair_navigation.py:384 | `[([16, 80, 55], [40, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:477 | harness/dispatch_skill_binding.py:477 | `[([4, 95, 40], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:502 | harness/dispatch_skill_binding.py:502 | `[([4, 95, 40], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:523 | harness/dispatch_skill_binding.py:523 | `[([4, 95, 40], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:667 | harness/dispatch_skill_binding.py:667 | `[([80, 125, 35], [102, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:790 | harness/dispatch_skill_binding.py:790 | `[([4, 95, 40], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:904 | harness/dispatch_skill_binding.py:904 | `[([80, 125, 35], [102, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/dispatch_skill_binding.py:1406 | harness/dispatch_skill_binding.py:1406 | `[([20, 70, 50], [40, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/e2e_b_quad.py:22 | harness/e2e_b_quad.py:22 | `[([109, 70, 35], [135, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/e2e_rgb_gate.py:135 | harness/e2e_rgb_gate.py:135 | `[([90, 70, 35], [135, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/heading_map_navigation.py:99 | harness/heading_map_navigation.py:99 | `[([12, 60, 30], [42, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/jev_motion.py:50 | harness/jev_motion.py:50 | `[([80, 125, 35], [100, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/jev_motion.py:58 | harness/jev_motion.py:58 | `[([80, 125, 125], [100, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/jev_motion.py:146 | harness/jev_motion.py:146 | `[([80, 125, 35], [100, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/jev_skill_motion.py:149 | harness/jev_skill_motion.py:149 | `[([5, 140, 65], [15, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/known_map_navigation.py:241 | harness/known_map_navigation.py:241 | `[([12, 60, 30], [42, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_navigation.py:218 | harness/pair_navigation.py:218 | `[([10, 100, 70], [16, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_navigation.py:254 | harness/pair_navigation.py:254 | `[([16, 80, 55], [38, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_navigation.py:341 | harness/pair_navigation.py:341 | `[([10, 100, 70], [16, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_transport_vision.py:43 | harness/pair_transport_vision.py:43 | `[([5, 90, 45], [22, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_transport_vision.py:139 | harness/pair_transport_vision.py:139 | `[([8, 100, 70], [19, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/pair_transport_vision.py:183 | harness/pair_transport_vision.py:183 | `[([18, 80, 55], [38, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/tile_own_vision.py:37 | harness/tile_own_vision.py:37 | `[([150, 110, 55], [168, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/visual_attachment.py:38 | harness/visual_attachment.py:38 | `[([80, 120, 200], [98, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/visual_box_surface.py:28 | harness/visual_box_surface.py:28 | `[([75, 70, 152], [105, 255, 220])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/wrist_zone_skill_v4.py:68 | harness/wrist_zone_skill_v4.py:68 | `[([75, 70, 40], [105, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/zone_pair_obstruction.py:79 | harness/zone_pair_obstruction.py:79 | `[([27, 60, 40], [54, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:harness/zone_solo_cyan_look_before_move.py:53 | harness/zone_solo_cyan_look_before_move.py:53 | `[([5, 100, 60], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:scripts/probe_owncam_carry_view.py:231 | scripts/probe_owncam_carry_view.py:231 | `[([80, 90, 30], [100, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:scripts/probe_owncam_carry_view.py:352 | scripts/probe_owncam_carry_view.py:352 | `[([125, 40, 20], [165, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| literal:scripts/replay_b_marker_detect.py:50 | scripts/replay_b_marker_detect.py:50 | `[([90, 70, 35], [135, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| OWN_HSV:red | harness/zone_color_boxes.py:OWN_HSV | `(((0, 150, 35), (6, 255, 255)), ((172, 150, 35), (179, 255, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| OWN_HSV:green | harness/zone_color_boxes.py:OWN_HSV | `(((56, 140, 30), (70, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| OWN_HSV:yellow | harness/zone_color_boxes.py:OWN_HSV | `(((23, 170, 50), (33, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| TOP_ZONE_HSV:cyan | harness/zone_color_boxes.py:TOP_ZONE_HSV | `(((84, 90, 40), (96, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| TOP_ZONE_HSV:red | harness/zone_color_boxes.py:TOP_ZONE_HSV | `(((0, 120, 50), (6, 255, 255)), ((172, 120, 50), (179, 255, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| TOP_ZONE_HSV:green | harness/zone_color_boxes.py:TOP_ZONE_HSV | `(((55, 100, 40), (72, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| TOP_ZONE_HSV:yellow | harness/zone_color_boxes.py:TOP_ZONE_HSV | `(((22, 140, 80), (33, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| HSV_RANGES:cyan | harness/zone_perception.py:HSV_RANGES | `[((80, 110, 60), (100, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| HSV_RANGES:red | harness/zone_perception.py:HSV_RANGES | `[((0, 150, 70), (6, 255, 255)), ((172, 150, 70), (179, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| HSV_RANGES:green | harness/zone_perception.py:HSV_RANGES | `[((45, 120, 50), (75, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| HSV_RANGES:yellow | harness/zone_perception.py:HSV_RANGES | `[((22, 150, 120), (32, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| CARGO_HSV:can | harness/zone_cargo_perception.py:CARGO_HSV | `(((122, 110, 60), (139, 255, 255)), ((136, 100, 210), (148, 255, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| CARGO_HSV:tile | harness/zone_cargo_perception.py:CARGO_HSV | `(((153, 130, 60), (168, 255, 255)), ((149, 105, 205), (158, 255, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| CARGO_HSV:heavy_crate | harness/zone_cargo_perception.py:CARGO_HSV | `(((145, 20, 110), (176, 135, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| CARGO_HSV:long_beam | harness/zone_cargo_perception.py:CARGO_HSV | `(((34, 90, 50), (54, 255, 255)), ((29, 70, 120), (33, 255, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| CARGO_HSV:tri_frame | harness/zone_cargo_perception.py:CARGO_HSV | `(((15, 35, 120), (30, 130, 255)), ((0, 0, 225), (60, 45, 255)), ((0, 0, 235), (179, 40, 255)))` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| own_zone:cyan | harness/zone_color_boxes.py:OWN_ZONE_CYAN_HSV | `(((85, 120, 40), (98, 255, 255)),)` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:cyan | harness/zone_own_perception.py:hue_mask | `[((84, 45, 28), (100, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:green | harness/zone_own_perception.py:hue_mask | `[((54, 45, 28), (72, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:red | harness/zone_own_perception.py:hue_mask | `[((0, 45, 28), (8, 255, 255)), ((170, 45, 28), (179, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:yellow | harness/zone_own_perception.py:hue_mask | `[((21, 45, 28), (34, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:can | harness/zone_own_perception.py:hue_mask | `[((124, 45, 28), (139, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:tile | harness/zone_own_perception.py:hue_mask | `[((150, 45, 28), (170, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:long_beam | harness/zone_own_perception.py:hue_mask | `[((36, 45, 28), (54, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:heavy_crate | harness/zone_own_perception.py:hue_mask | `[((160, 45, 28), (176, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_own:tri_frame | harness/zone_own_perception.py:hue_mask | `[((14, 45, 28), (26, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_team:long_beam | harness/zone_own_perception_v2.py:team_mask | `[((28, 150, 40), (58, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_team:heavy_crate | harness/zone_own_perception_v2.py:team_mask | `[((156, 45, 60), (178, 210, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| adaptive_team:tri_frame | harness/zone_own_perception_v2.py:team_mask | `[((12, 22, 80), (32, 140, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| legacy_goal:A | harness/visual_navigation.py:_GOAL_HSV | `[((100, 105, 35), (132, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| legacy_goal:B | harness/visual_navigation.py:_GOAL_HSV | `[((40, 85, 30), (84, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| legacy_goal:C | harness/visual_navigation.py:_GOAL_HSV | `[((22, 105, 55), (38, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| robot_orange | harness/opencv_wall_observation_robot_mask.py:ROBOT_MASK_CONFIG | `[([5, 100, 60], [25, 255, 255])]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| floor_goal_B | harness/floor_goal.py:FloorGoalOptions | `[((100, 35, 30), (130, 255, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| AMCL_all_paint_hues | harness/zone_solo_cyan_landmarks.py:PARAMS | `[((0, 20, 35), (179, 150, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| production_cyan | harness/markerless_box.py:_cyan_components | `[((73, 65, 45), (104, 255, 245))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| legacy_dark_bands | harness/owncam_pair_beam_v2.py:BAND_V_MAX/BAND_S_MAX | `[((0, 0, 0), (179, 89, 60))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| washed_white | harness/zone_cargo_perception.py:WHITE_HSV | `[((0, 0, 225), (179, 45, 255))]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| beam_band:teal | 870c0c59f3c2eae556abaa809ac1eddf33dce5ca:scripts/probe_carry_lookaround.py:48 | `[[[70, 120, 90], [90, 255, 255]]]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| beam_band:blue | 870c0c59f3c2eae556abaa809ac1eddf33dce5ca:scripts/probe_carry_lookaround.py:48 | `[[[110, 120, 60], [130, 255, 255]]]` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| crate_blue | 727de2af0e5ec10dda0b954e757c2fe42e694766:sim/crate_rgb_lift.py:25-33 | `B>140 and R<90 and G<90` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| crate_teal | 727de2af0e5ec10dda0b954e757c2fe42e694766:sim/crate_rgb_lift.py:25-33 | `G>140 and B>60 and B<G and R<90` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
| crate_pink | 727de2af0e5ec10dda0b954e757c2fe42e694766:sim/crate_rgb_lift.py:25-33 | `R>90 and R>G+25 and B>G-5 and R>B and not lug` | 0/9437184 (0.0000%) | 0/39321600 (0.0000%) |
