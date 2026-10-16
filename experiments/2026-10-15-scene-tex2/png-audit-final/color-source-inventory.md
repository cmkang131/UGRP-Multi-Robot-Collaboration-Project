# 색 소스 전수 탐색 목록

HSV/hsv/inRange 포함 Python을 AST로 검색. 직접 비교와 동적 범위는 별도 고정 목록 및 문맥 검사로 보충한다.

## harness/active_wall_vision.py

SHA256 `ae123d46fec6863c11449c0c031ba40841d72e236fe971ac41fe3c528380b6c3`


## harness/camera_beam_features.py

SHA256 `fc1c94bbdd7adc4abcc87e6e39bf3f202b1e58256e6c74b851e2bfeb7d5585bc`

- L60 dynamic_or_shared_definition: `cv2.inRange(hsv, low, np.array((hue_upper, 255, 255), np.uint8))`

## harness/camera_goal_transport.py

SHA256 `012f0f2064e6ee2d67a39ef35a010c70692e45f284785b209eddf81b58804c5d`

- L31 measured_literal: `cv2.inRange(hsv, np.array((20, 70, 50), np.uint8), np.array((40, 255, 255), np.uint8))`
- L135 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array((3, 105, 45), np.uint8), np.array((hue_upper, 255, 255), np.uint8))`
- L164 measured_literal: `cv2.inRange(hsv, np.array((40, 60, 30), np.uint8), np.array((90, 255, 255), np.uint8))`

## harness/camera_short_transport_student.py

SHA256 `196c70b9a39766371b5f1ccc9539f6acadf0e694cffdb3daca16a3ce41e48725`

- L47 measured_literal: `cv2.inRange(own_hsv, np.array((3, 105, 45), np.uint8), np.array((24, 255, 255), np.uint8))`
- L50 measured_literal: `cv2.inRange(top_hsv, np.array((20, 70, 50), np.uint8), np.array((40, 255, 255), np.uint8))`

## harness/camera_varied_start_geometry.py

SHA256 `a4cef5ffcac3f738c683f1e898565ec26607eb48cb33b5b3ac0eb2612042845d`


## harness/camera_varied_start_heading.py

SHA256 `dafa6a3b44027e97e530aa8f214fc1b193cc8d9b0aee1515ae94dcb843add025`


## harness/dispatch_box_identity.py

SHA256 `b6a113813b885d753b646cff4822cedaa2dc4e82b85536ebcbf4648731733627`

- L16 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 35), np.uint8), np.array((102, 255, 255), np.uint8))`

## harness/dispatch_navigation_map.py

SHA256 `6d898733d5745435bb64a9739073fbb775bb97bb2c968a46fce2f0dbdcd79235`

- L16 measured_literal: `cv2.inRange(hsv, np.array([3, 170, 45], np.uint8), np.array([35, 255, 255], np.uint8))`
- L119 measured_literal: `cv2.inRange(hsv, np.array([80, 125, 35], np.uint8), np.array([102, 255, 255], np.uint8))`

## harness/dispatch_pair_navigation.py

SHA256 `b748270b83bc21616aa317fa44d331c6d9fa2023806805d1ca6656dbb2e38f7e`

- L384 measured_literal: `cv2.inRange(hsv, np.array([16, 80, 55], np.uint8), np.array([40, 255, 255], np.uint8))`

## harness/dispatch_skill_binding.py

SHA256 `8918dbc6c3854be995a1e33d9b0eff962d208b681e62287a00cf4d1e8f0f469a`

- L477 measured_literal: `cv2.inRange(old_hsv, np.array((4, 95, 40), np.uint8), np.array((25, 255, 255), np.uint8))`
- L502 measured_literal: `cv2.inRange(old_hsv, np.array((4, 95, 40), np.uint8), np.array((25, 255, 255), np.uint8))`
- L523 measured_literal: `cv2.inRange(current_hsv, np.array((4, 95, 40), np.uint8), np.array((25, 255, 255), np.uint8))`
- L667 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 35), np.uint8), np.array((102, 255, 255), np.uint8))`
- L790 measured_literal: `cv2.inRange(hsv, np.array((4, 95, 40), np.uint8), np.array((25, 255, 255), np.uint8))`
- L904 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 35), np.uint8), np.array((102, 255, 255), np.uint8))`
- L1037 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array((80, saturation, 35), np.uint8), np.array((102, 255, 255), np.uint8))`
- L1406 measured_literal: `cv2.inRange(hsv, np.array((20, 70, 50), np.uint8), np.array((40, 255, 255), np.uint8))`

## harness/dispatch_translation_skew.py

SHA256 `5193f2cc77d9814a6f0d56354cb27ded952c011e45ae9df5d2fe9eabfd97535c`

- L25 dynamic_or_shared_definition: `cv2.inRange(hsv[y0:y1, x0:x1], np.array([3, saturation, 45], np.uint8), np.array([35, 255, 255], np.uint8))`

## harness/e2e_b_partial.py

SHA256 `469baf6b69ed9140b0fc0b3a6bdc01937ead851add8053b46ba070db47cd5efd`


## harness/e2e_b_quad.py

SHA256 `70c5406ebf4f4611c7009456ee37b1c02702793312e5144fb629fdb283f08bfd`

- L22 measured_literal: `cv2.inRange(hsv, FLOOR_BLUE_V2[0], FLOOR_BLUE_V2[1])`

## harness/e2e_rgb_gate.py

SHA256 `8d9fa2cfdd65b8d55cb2061eabd85ceffd564c331c7ddeeadbd8f1c840406ad2`

- L135 measured_literal: `cv2.inRange(hsv, (90, 70, 35), (135, 255, 255))`

## harness/e2e_rgb_vo.py

SHA256 `62d34bf4a45a59f92456bd0ffa2113ccaea394dd160f56a4db250cf777f781bf`


## harness/e2e_stall_odometry.py

SHA256 `52948e3cbe66651f10941e9c5b55aa89d1312f55535541ca96b86f2d2a56b360`


## harness/floor_goal.py

SHA256 `0c5190fd739978ea6b49b4e569bf67b1c29ae67327a0b5e9ff82fdd3800c543d`


## harness/floor_goal_v2.py

SHA256 `74ddb66142b01c5443036dd3868c014e06eda962f845c15bd2944721795e4cbc`


## harness/heading_map_navigation.py

SHA256 `a03553a909a1f4d33cac5b2833a8a47b53770bcfdb3c09d889f40fd0bae46f09`

- L99 measured_literal: `cv2.inRange(hsv, np.array([12, 60, 30], np.uint8), np.array([42, 255, 255], np.uint8))`

## harness/jev_motion.py

SHA256 `b68eb05467a336f5c9190221e73130b7d234557b6a1094c48b671296e5008d6a`

- L50 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 35), np.uint8), np.array((100, 255, 255), np.uint8))`
- L58 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 125), np.uint8), np.array((100, 255, 255), np.uint8))`
- L146 measured_literal: `cv2.inRange(hsv, np.array((80, 125, 35), np.uint8), np.array((100, 255, 255), np.uint8))`

## harness/jev_skill_motion.py

SHA256 `536951f5afd46f00ca69626016a68cc5aa8f9a798758360d7bcdbe0a92a147af`

- L149 measured_literal: `cv2.inRange(hsv, np.array([5, 140, 65], np.uint8), np.array([15, 255, 255], np.uint8))`

## harness/known_map_navigation.py

SHA256 `484a176a3dbd632fec094d612137e448100f07c1180c2f6abeb490bc5a18fc0b`

- L241 measured_literal: `cv2.inRange(hsv, np.array([12, 60, 30], np.uint8), np.array([42, 255, 255], np.uint8))`

## harness/m1_color_perception.py

SHA256 `b1fc07aaef3866d066a4542dabafc14c974fe68229458257e5daae163000a9ba`

- L42 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array((lo, MIN_SATURATION, value_range[0]), np.uint8), np.array((hi, 255, value_range[1]), np.uint8))`

## harness/markerless_box.py

SHA256 `f1bc74126d91b17dbe7527c5444e5dff7c3a2ce469a1a90834f85dbae57bd46c`

- L42 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray((73, min_saturation, 45)), np.asarray((104, 255, 245)))`
- L76 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray((75, 70, value_floor)), np.asarray((105, 255, 255)))`

## harness/multi_object_tracking.py

SHA256 `30df7f34b065984f863a983bfe996c4fb57fab19d6808c890093e1b3fab256c0`

- L30 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))`

## harness/navigation_evidence.py

SHA256 `fdcf79d5873a7672d191f82babdd9c3d01ccf0912b4cb810a415bdf7d4ce6e87`

- L34 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(limits[0], np.uint8), np.asarray(limits[1], np.uint8))`

## harness/opencv_wall_observation.py

SHA256 `ef8d9bcab34afe9bc52b3987e226b8efef237a6d587444750009d2663f1dae79`

- L34 dynamic_or_shared_definition: `cv2.inRange(hsv, (0, int(gates['wall_band_saturation_max']), 30), (179, 255, 255))`

## harness/opencv_wall_observation_robot_mask.py

SHA256 `7068f5097441afc89e4644b5e79c9b52a3b8f91b60374835b1106ecf7a36317f`

- L32 dynamic_or_shared_definition: `cv2.inRange(hsv, tuple(cfg['hsv_lower']), tuple(cfg['hsv_upper']))`

## harness/own_beam_edge.py

SHA256 `f72118c5c1faeb91094347469dd15fa6059dd99bd6acede4760eec96411f3e8d`


## harness/own_map_amcl_vendor/landmark_color.py

SHA256 `6c7f355831a03c0cd40e44862c7f68f9d13acd8e978eb2696da062f32ad54702`


## harness/own_map_amcl_vendor/landmarks.py

SHA256 `7c7ad9230d3a0415da6d96924663254cbf59e85a66198924e796ec00d4ea54d9`


## harness/own_route_zone_arrival.py

SHA256 `36608edcc19a94b9a84f09c58e75c546d2964bbbc6e3ec459360035e206b4144`


## harness/owncam_pair_beam.py

SHA256 `6bc959a766676ba62fe9126e2d90fcfa62c7353ee79f83fa1ac8caeb4eae82d6`

- L81 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(LIME_LO), np.asarray(LIME_HI))`
- L152 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(LIME_LO), np.asarray(LIME_HI))`

## harness/owncam_pair_beam_v2.py

SHA256 `b4dad971e241542460a9f7ae259356039033d18c9d4f16c940b2370ced388f97`


## harness/owncam_pair_beam_v6d.py

SHA256 `cfa4eb80fd0c9402f0effe5e3f9125a488438f03143ffd495b51f4d8787faa12`

- L42 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(lo), np.asarray(v1.LIME_HI))`

## harness/owncam_pair_hold_v3.py

SHA256 `1af3eeb8351ebefcfd2eca0a24f6e3d1876b288f40ef857f708eca1e78cc5bd2`


## harness/owncam_pair_lift_v3.py

SHA256 `faf725e3b1b1ee1e387c0f8c593b7508b6e170387d010debb551df7bd05d087d`


## harness/pair_navigation.py

SHA256 `354cd47f115574d33a5ae81f1afae41dc78d2e3bc97203f63aaa8316012e3d19`

- L218 measured_literal: `cv2.inRange(hsv, np.array([10, 100, 70], np.uint8), np.array([16, 255, 255], np.uint8))`
- L254 measured_literal: `cv2.inRange(hsv, np.array([16, 80, 55], np.uint8), np.array([38, 255, 255], np.uint8))`
- L341 measured_literal: `cv2.inRange(hsv, np.array([10, 100, 70], np.uint8), np.array([16, 255, 255], np.uint8))`

## harness/pair_transport_vision.py

SHA256 `01a5b96d54e8e4be7a2227428df2cd3a21c5f157924bbb17575e1f4646ec5b23`

- L43 measured_literal: `cv2.inRange(hsv, (5, 90, 45), (22, 255, 255))`
- L62 non_hsv_or_indirect: `cv2.inRange(central, (5, 90, 45), (22, 255, 255))`
- L139 measured_literal: `cv2.inRange(hsv, (8, 100, 70), (19, 255, 255))`
- L183 measured_literal: `cv2.inRange(hsv, (18, 80, 55), (38, 255, 255))`

## harness/s4_grip_r3.py

SHA256 `92eac216e1b5169780bf5fa35aa4ff8a86fed9664431234a544bdc2650753afe`


## harness/s4_grip_visual.py

SHA256 `094ff01d3727068b0de0798585076690e2fd8ab2db9bc1931d0ee0b020b65512`


## harness/scene_tex2_perception.py

SHA256 `83b38e811516e1ba6e89cf47a9a000c4048ee9329cea126b1daa8a47a1908b0f`


## harness/solo_box_transport.py

SHA256 `901df915d0f12f81be035cb8e777c5a059970150aa3e9b9f0c7f7eda0fcf1d43`

- L50 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))`

## harness/tile_own_vision.py

SHA256 `63813b165f73c1c40829e388dddcd5b7760745f42e49a2bdf21cc36e8fe1878a`

- L37 measured_literal: `cv2.inRange(hsv, (150, 110, 55), (168, 255, 255))`

## harness/visual_attachment.py

SHA256 `3f7378be87807f2b044ad8ec62956518e2d6b39c7172b10e427d38894aab280e`

- L32 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray((80, min_saturation, 45)), np.asarray((104, 255, 255)))`
- L38 measured_literal: `cv2.inRange(hsv, np.asarray((80, 120, 200)), np.asarray((98, 255, 255)))`

## harness/visual_box_surface.py

SHA256 `bbc04aa79388acfb617145a3b642992bdce08fca0b55fc028cef52635944fbbc`

- L28 measured_literal: `cv2.inRange(hsv, np.asarray((75, 70, 152)), np.asarray((105, 255, 220)))`

## harness/visual_drive_guard.py

SHA256 `174893ce29f13de820ea20d009e4ff5347255f6ee730fa28da058f83e7b1aa88`

- L73 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(limits[0], np.uint8), np.asarray(limits[1], np.uint8))`

## harness/visual_floor.py

SHA256 `2415658edcd03df6347136c9b3f17a32d16b950d4365a237d547dcd3a9d42e26`

- L32 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(low), np.array(high))`

## harness/visual_navigation.py

SHA256 `f7c803466f5a3b7432bb666f7115a0a39c4c2d5a76d62e201e4c5ce06fc823c9`

- L41 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(limits[0], np.uint8), np.asarray(limits[1], np.uint8))`

## harness/visual_placement.py

SHA256 `7faead9db079136c8bfa2137129789dbea03d2fd91a690b1a004d7f11f2ca8a1`

- L100 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8))`

## harness/wall_floor_boundary.py

SHA256 `eaed7cacc997b799e830e6f4c3c96265d543c1e79811f637f73cf0ba56ebd5e8`


## harness/wall_floor_lorigo.py

SHA256 `e0979d4196efa6a7a4157c70571472b13c1615f60ab5c90573accf55e83654e9`


## harness/wrist_can.py

SHA256 `d6614b99fcf68137becf6e591548c7c0ba2198b152f467ab64d4c228670307f2`

- L77 dynamic_or_shared_definition: `cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), np.array(HUE_LOW, np.uint8), np.array(HUE_HIGH, np.uint8))`

## harness/wrist_zone_skill_v4.py

SHA256 `2864710c767fdf43b77f7662ecda8ad042830a072ab8437d315f3d901b419d22`

- L68 measured_literal: `cv2.inRange(hsv, np.asarray(HELD_HUE_LO), np.asarray(HELD_HUE_HI))`

## harness/wrist_zone_skill_v6.py

SHA256 `47ec5cd0c36d59c9226d283ce062e6e6b133bd68a06c0cde4b30c7d830ca0234`

- L137 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(CYAN_HSV_LO), np.array(CYAN_HSV_HI))`

## harness/wrist_zone_skill_v8.py

SHA256 `5c2b27e06eeeaf2b51eff585182739afde0597025d7c5f868b7ea7f128a4b12e`


## harness/zone_cargo_perception.py

SHA256 `57335d615209f68658cb272360735404b2321c48dbd03b7eae27045733794290`

- L150 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8))`

## harness/zone_cargo_perception_v2.py

SHA256 `958499c313cdfcdd68355f0cfbebe17475c8086522e763e194ef8beab5d7f30b`


## harness/zone_color_box_delivery.py

SHA256 `640442dbb8de6d5bc43bceb1e8faf9e55b2f2a43ff801ce63c2ea760ed9cbb76`

- L34 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8))`

## harness/zone_color_boxes.py

SHA256 `9b38265c27f86a735333b25326a10177ed073cc6c3e0f945ee5c318398813966`

- L106 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8))`

## harness/zone_own_deliver.py

SHA256 `0f347000d39642b24630bccc86d70433ce96329e959867ce0b09ce3d409e2bab`

- L59 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8))`

## harness/zone_own_perception.py

SHA256 `07f8cbf959555bd49f12b3f8a5f93ef14ee5bb559d9385e236d7e8ecd0d694ff`

- L257 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray((low, min_sat, min_val), np.uint8), np.asarray((high, 255, 255), np.uint8))`

## harness/zone_own_perception_v2.py

SHA256 `ef3b1bc2215666c248d259176b7d1d5586cdf1e09f2e615cb85ad7ef9d3fb2b8`

- L473 dynamic_or_shared_definition: `cv2.inRange(hsv, low, high)`

## harness/zone_own_perception_v3.py

SHA256 `fbc29b63ed04446b53a27e4e87cb4d2e0a3f0bd648106c2675a1356d82f6f936`


## harness/zone_own_perception_v3_1.py

SHA256 `b7c8d99d3cbcf120be850fc4068cb4a78150ebe1eeb1c231c3ea8670f907d7a0`


## harness/zone_pair_highpose_edge.py

SHA256 `bf48e417c5b5a7b3b71586120a24e33e888a8dc5bff1d27c93337899b5bdcfd2`


## harness/zone_pair_highpose_frame_gate.py

SHA256 `e23c943be1fed2361941d8c6610d8c62d154855bf5d9fcffbfb0537267644513`


## harness/zone_pair_obstruction.py

SHA256 `f40bd166ec152436a7d30938f16aee4acfb21b5ead569cc660769143e963a0dd`

- L79 measured_literal: `cv2.inRange(hsv, np.array([27, 60, 40]), np.array([54, 255, 255]))`

## harness/zone_pair_vision.py

SHA256 `cce72504edf01d119aafbefc8cb4ea1aa5a407196f9809f6cb5b8ec0bfecc9fc`


## harness/zone_perception.py

SHA256 `c612f2360649c25ace00e7a4fa14d1c845ca2fd870bb9edc7ae424c1d4e1571d`

- L55 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))`

## harness/zone_s3_checkpoint_visual.py

SHA256 `acc7d289b2d4f615835c12aea5e69c45c1867d7e1c253a00771760e7ea3cb47f`


## harness/zone_solo_cyan_landmarks.py

SHA256 `41bad45345b1b58b9688ef077088a5cb36b91024e0750b1b35a6d63133fe5286`


## harness/zone_solo_cyan_look_before_move.py

SHA256 `1fe8eb8b816bcf4575ccbc9de33e807e40748ae83b92f0ef29715ccedf4bf572`

- L53 measured_literal: `cv2.inRange(hsv, (5, 100, 60), (25, 255, 255))`

## harness/zone_solo_cyan_scene_change.py

SHA256 `8efbab9881b5ca4a7c5f62ab72301af3999abcf886bba9cd8094da6a894bcc54`


## harness/zone_solo_cyan_side_scan.py

SHA256 `0eebc3efbf070aa9be0a5418b57c972e99dac486dd538596e0dc60073a47926a`

- L25 dynamic_or_shared_definition: `cv2.inRange(hsv, tuple(APPEARANCE['hsv_lower']), tuple(APPEARANCE['hsv_upper']))`

## harness/zone_solo_cyan_staged_approach.py

SHA256 `702ce5135f33ed18b469d951eaa75f4a44cf4b453974d6279c6933faaec12989`

- L31 dynamic_or_shared_definition: `cv2.inRange(hsv, tuple(APPEARANCE['hsv_lower']), tuple(APPEARANCE['hsv_upper']))`

## harness/zone_solo_cyan_vision_v106.py

SHA256 `4e162749a90a19fc55d2b155a2f9ade2fafd3b82d2aec8a081d0e12d08314490`


## harness/zone_solo_cyan_visual_fix.py

SHA256 `e7eb767cf5f1b862e0bd168245f36cee76230b85aa5c2078f9e4ed4a8fcad63d`


## sim/zone_cargo.py

SHA256 `84cc956c22ca0d1b0d76fabcb4da61c33c73fcf77600d3079bced5658aa04a6b`


## scripts/analyze_render_profile_ab.py

SHA256 `c90f1c0cdaf2b357478b623d26645365bfad93f928f5b56f54a5aef0f6da7ae0`


## scripts/audit_scene_tex2.py

SHA256 `20777bc87b61e70bdfbdc5a12d3f4d6f7e089b9d530b60a4396e2855c47bae30`

- L31 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))`

## scripts/calibrate_own_image_gates.py

SHA256 `bb651f5d94dfdbcd98fb2f74108370b07f47a63bbbfc698269ff20229030534e`


## scripts/eval_zone_own_perception_v2.py

SHA256 `612c089d5d1dafa74e57a63b9ceb78e5f3e43ac8f40a420772a7bc55547c1c79`


## scripts/generate_scene_tex2.py

SHA256 `347a3c084e96e2ef903b4b25ccc9d98fdc92e46149fa303ebbd3e598068d936e`


## scripts/probe_owncam_carry_view.py

SHA256 `28f9fa02f71d18711013ef59c0b1ee47020c026884ba3bc47b096e126a88f162`

- L231 measured_literal: `cv2.inRange(hsv, np.array((80, 90, 30)), np.array((100, 255, 255)))`
- L352 measured_literal: `cv2.inRange(hsv, np.array((125, 40, 20)), np.array((165, 255, 255)))`

## scripts/probe_scene_tex2.py

SHA256 `1088b86809a62cd8dbe9868bb208a63d4a2168d87fd22ff4acdb61af3451ef2c`

- L226 dynamic_or_shared_definition: `cv2.inRange(hsv, np.asarray(lo, np.uint8), np.asarray(hi, np.uint8))`

## scripts/red_block/camera.py

SHA256 `d805560e183b52c48eee1fdb7fb637ba2da244e24ebfe3113793d5c5cdb2f837`

- L340 non_hsv_or_indirect: `cv2.inRange(lab, np.array(RED_LAB_MIN, np.uint8), np.array(RED_LAB_MAX, np.uint8))`
- L426 non_hsv_or_indirect: `cv2.inRange(lab, np.array(RED_LAB_MIN, np.uint8), np.array(RED_LAB_MAX, np.uint8))`

## scripts/render_zone_cargo_catalogue.py

SHA256 `0566a163174f5e99dee807b18c6efac1a5fbdbad35fba09fc9a2a718e37fb04a`

- L55 dynamic_or_shared_definition: `cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))`

## scripts/replay_b_marker_detect.py

SHA256 `06822c723736449e90258f2fbfe17dce8d2319a2184a38c5f2edb7a1b1d3971f`

- L50 measured_literal: `cv2.inRange(hsv, (90, 70, 35), (135, 255, 255))`

## scripts/review_masterpi_camera.py

SHA256 `715f11c0c67e0a064564052dcc922471b332b076aee660076dfefe0a1239786e`


## scripts/review_masterpi_camera_v2.py

SHA256 `03d5db6111c7c7ccb088c2a8f6be7fbae013b854a037fd201b3db7c839f73268`


## scripts/review_masterpi_camera_v3.py

SHA256 `c1ce18f6eb08e62c7dff686b1e5a980cc123061d02e665a8bf47c1abf976df52`


## scripts/run_m2_pair.py

SHA256 `3432df1fbefd4779921dc89a20f60fb67299fcdd02aa4568c6ecd14e27978783`
