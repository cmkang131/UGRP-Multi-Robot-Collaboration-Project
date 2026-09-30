# 정식 v2 6시나리오 원본 요구와 정적 거리

원본에서 추출한 23주문행·26물건. 자세는 world `(x m, y m, yaw rad)`. `order_id`와 `item_id`는 다른 식별자다. `kind_fungible`은 개수 충족, `specific_item`은 지정 개체 충족을 요구한다. 이 표의 역할은 cargo catalogue의 grasp 역할이며 특정 로봇 배정이 아니다. 모든 학생/물리 측정은 미측정이다.

공통: `robot_spawns=arena_default`, `contact_profile=cargo_noslip_v1`, weld OFF, landmark_detail none, 3 robots. 후보 base XYyaw는 (−.85,−2.25,0), (−.85,−.85,0), (−.85,.55,0); 로봇별 할당은 episode의 layout_seed/화물 생성 뒤 shuffle에 달려 있고 현재 시나리오에 고정되지 않았다. 기존 `zone_arena.episode:357`의 base z는 .032355118817659255 m이나 최종v3 reset 검증값은 아니다.

모든 지도 zone 중심/half extent: A=(4.60,.40)/(.30,.70), B=(4.60,−2.10)/(.30,.70), C=(3.00,−.85)/(.30,.70). landing 검사 목표는 구역 내부 착지이며 구역 중심이나 특정 slot 도달을 요구하는 controller와 같지 않다.

공통 원본 예산: 1,800 SIM초, HTTP trial90/actor30, output tokens/call768. 이번 작업은 이 예산을 사용하지 않았고 모델 호출은0이다.

## s1_normal_mixed_v2

지도 `zone_wide_door_geometry_v2`, seeds `[601, 602, 603]`, 주문행 6, 물건 7.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s1_normal_mixed_v2.json:13](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L13) `order-1` | cyan×2 | kind_fungible / 지정 없음 | 1 / west | P1:P1-1 | A | R6 identity/count 경계 | 미측정 |
| [s1_normal_mixed_v2.json:25](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L25) `order-2` | red×1 | kind_fungible / 지정 없음 | 1 / west | P2:P2-1 | B | R2 색상 | 미측정 |
| [s1_normal_mixed_v2.json:37](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L37) `order-3` | can×1 | kind_fungible / 지정 없음 | 1 / any | P1:P1-2 | C | R1/R2 can | 미측정 |
| [s1_normal_mixed_v2.json:49](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L49) `order-4` | tile×1 | kind_fungible / 지정 없음 | 1 / west | P2:P2-2 | B | R1/R2 tile | 미측정 |
| [s1_normal_mixed_v2.json:61](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L61) `order-5` | long_beam×1 | specific_item / beam_1 | 2 / end_neg/end_pos | P2:P2-3 | A | R1/R3/R4 혼합·짝·자세 | 미측정 |
| [s1_normal_mixed_v2.json:76](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L76) `order-6` | green×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-3 | C | R2 색상 | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s1_normal_mixed_v2.json:101](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L101) `cyan_1` | order-1 / cyan | (-0.2, -2.45, 0) | P1-1→A | west: (-0.355, -2.45, 0) | 미측정 |
| [s1_normal_mixed_v2.json:112](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L112) `cyan_2` | order-1 / cyan | (0.4, -2.45, 0) | P1-1→A | west: (0.245, -2.45, 0) | 미측정 |
| [s1_normal_mixed_v2.json:123](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L123) `red_1` | order-2 / red | (1, -2.45, 0) | P2-1→B | west: (0.845, -2.45, 0) | 미측정 |
| [s1_normal_mixed_v2.json:134](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L134) `can_1` | order-3 / can | (0.4, -0.85, 0) | P1-2→C | any: (0.245, -0.85, 0) | 미측정 |
| [s1_normal_mixed_v2.json:145](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L145) `tile_1` | order-4 / tile | (1, -0.85, 0) | P2-2→B | west: (0.845, -0.85, 0) | 미측정 |
| [s1_normal_mixed_v2.json:156](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L156) `beam_1` | order-5 / long_beam | (1.275, 0.45, 1.5708) | P2-3→A | end_neg: (1.275002, 0.025, 1.5708); end_pos: (1.274998, 0.875, -1.570793) | 미측정 |
| [s1_normal_mixed_v2.json:168](../../configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json#L168) `green_1` | order-6 / green | (-0.2, 0.75, 0) | P1-3→C | west: (-0.355, 0.75, 0) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| door_1 (door) | (2.2, 0.05) / (0.025, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |

사건:

- 없음. 동료 교통/양보는 숨은 사건으로 주입되지 않는다.

## s2_unmapped_blockage_v2

지도 `zone_wide_two_doors_final_v1`, seeds `[611, 612, 613]`, 주문행 3, 물건 4.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s2_unmapped_blockage_v2.json:13](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L13) `order-1` | cyan×2 | kind_fungible / 지정 없음 | 1 / west | P1:P1-3 | A | R6 identity/count 경계 | 미측정 |
| [s2_unmapped_blockage_v2.json:25](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L25) `order-2` | green×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-2 | C | R2 색상 | 미측정 |
| [s2_unmapped_blockage_v2.json:37](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L37) `order-3` | heavy_crate×1 | specific_item / crate_1 | 2 / west/east | P2:P2-1 | B | R1/R3 crate | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s2_unmapped_blockage_v2.json:65](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L65) `cyan_1` | order-1 / cyan | (-0.2, 0.75, 0) | P1-3→A | west: (-0.355, 0.75, 0) | 미측정 |
| [s2_unmapped_blockage_v2.json:76](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L76) `cyan_2` | order-1 / cyan | (0.4, 0.75, 0) | P1-3→A | west: (0.245, 0.75, 0) | 미측정 |
| [s2_unmapped_blockage_v2.json:87](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L87) `green_1` | order-2 / green | (0.4, -0.85, 0) | P1-2→C | west: (0.245, -0.85, 0) | 미측정 |
| [s2_unmapped_blockage_v2.json:98](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L98) `crate_1` | order-3 / heavy_crate | (1.275, -2.15, 0) | P2-1→B | west: (1.02, -2.15, 0); east: (1.53, -2.15, -3.141593) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| door_narrow (door) | (2.2, 0.05) / (0.025, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |
| door_wide (door) | (2.2, -2.625) / (0.025, 0.5) | 1.0 m / x / 2 | 서→동 출하, 동→서 복귀 별도 | 미측정 |

사건:

- [s2_unmapped_blockage_v2.json:113](../../configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json#L113) `door_narrow_blocked` / `passage_blocked` / **45.0 SIM초**.
  - target: `{"passage":"door_narrow","obstacle":{"obstacle_id":"fallen_pallet_1","center_m":[2.2,0.05],"half_extents_m":[0.15,0.22],"height_m":0.12}}`.
  - discovery(비공개 설계): `{"kind":"own_camera_near_anchor","anchor":"door_narrow","radius_m":1.2}`. 실제 시야·발견은 미측정.

## s3_late_rendezvous_v2

지도 `zone_wide_door_geometry_v2`, seeds `[621, 622, 623]`, 주문행 4, 물건 4.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s3_late_rendezvous_v2.json:13](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L13) `order-1` | long_beam×1 | specific_item / beam_1 | 2 / end_neg/end_pos | P1:P1-3 | A | R1/R3/R4 혼합·짝·자세 | 미측정 |
| [s3_late_rendezvous_v2.json:28](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L28) `order-2` | cyan×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-1 | B | R6 identity/count 경계 | 미측정 |
| [s3_late_rendezvous_v2.json:40](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L40) `order-3` | tile×1 | kind_fungible / 지정 없음 | 1 / west | P2:P2-2 | C | R1/R2 tile | 미측정 |
| [s3_late_rendezvous_v2.json:52](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L52) `order-4` | red×1 | kind_fungible / 지정 없음 | 1 / west | P2:P2-1 | B | R2 색상 | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s3_late_rendezvous_v2.json:77](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L77) `beam_1` | order-1 / long_beam | (0.125, 0.45, 1.5708) | P1-3→A | end_neg: (0.125002, 0.025, 1.5708); end_pos: (0.124998, 0.875, -1.570793) | 미측정 |
| [s3_late_rendezvous_v2.json:88](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L88) `cyan_1` | order-2 / cyan | (0.4, -2.45, 0) | P1-1→B | west: (0.245, -2.45, 0) | 미측정 |
| [s3_late_rendezvous_v2.json:99](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L99) `tile_1` | order-3 / tile | (1, -0.85, 0) | P2-2→C | west: (0.845, -0.85, 0) | 미측정 |
| [s3_late_rendezvous_v2.json:110](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L110) `red_1` | order-4 / red | (1, -2.45, 0) | P2-1→B | west: (0.845, -2.45, 0) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| door_1 (door) | (2.2, 0.05) / (0.025, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |

사건:

- [s3_late_rendezvous_v2.json:124](../../configs/zone_study_scenarios_v2/s3_late_rendezvous_v2.json#L124) `r3_hold_late` / `robot_hold` / **12.0 SIM초**.
  - target: `{"robot_id":"r3","duration_s":40.0}`.
  - discovery(비공개 설계): `{"kind":"own_camera_self"}`. 실제 시야·발견은 미측정.
  - r3 정지 예정 구간 [12,52]초. 실제 정지·집결 지연·own 관측은 미측정.

## s4_narrow_door_standoff_v2

지도 `zone_wide_corridor_final_v1`, seeds `[631, 632, 633]`, 주문행 4, 물건 4.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s4_narrow_door_standoff_v2.json:13](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L13) `order-1` | cyan×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-1 | A | R6 identity/count 경계 | 미측정 |
| [s4_narrow_door_standoff_v2.json:25](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L25) `order-2` | red×1 | kind_fungible / 지정 없음 | 1 / west | P2:P2-1 | B | R2 색상 | 미측정 |
| [s4_narrow_door_standoff_v2.json:37](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L37) `order-3` | green×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-2 | C | R2 색상 | 미측정 |
| [s4_narrow_door_standoff_v2.json:49](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L49) `order-4` | long_beam×1 | specific_item / beam_1 | 2 / end_neg/end_pos | P2:P2-3 | A | R1/R3/R4 혼합·짝·자세 | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s4_narrow_door_standoff_v2.json:77](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L77) `cyan_1` | order-1 / cyan | (0.4, -2.45, 0) | P1-1→A | west: (0.245, -2.45, 0) | 미측정 |
| [s4_narrow_door_standoff_v2.json:88](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L88) `red_1` | order-2 / red | (1, -2.45, 0) | P2-1→B | west: (0.845, -2.45, 0) | 미측정 |
| [s4_narrow_door_standoff_v2.json:99](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L99) `green_1` | order-3 / green | (0.4, -0.85, 0) | P1-2→C | west: (0.245, -0.85, 0) | 미측정 |
| [s4_narrow_door_standoff_v2.json:110](../../configs/zone_study_scenarios_v2/s4_narrow_door_standoff_v2.json#L110) `beam_1` | order-4 / long_beam | (1.275, 0.45, 1.5708) | P2-3→A | end_neg: (1.275002, 0.025, 1.5708); end_pos: (1.274998, 0.875, -1.570793) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| corridor_1 (corridor) | (3.0625, 1.175) / (0.8625, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |
| bay_1 (passing_bay) | (3.1, 0.625) / (0.275, 0.25) | — m / y / — | bay 대피/복귀 | 미측정 |

사건:

- 없음. 동료 교통/양보는 숨은 사건으로 주입되지 않는다.

## s5_moved_dropped_item_v2

지도 `zone_wide_door_geometry_v2`, seeds `[641, 642, 643]`, 주문행 3, 물건 4.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s5_moved_dropped_item_v2.json:13](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L13) `order-1` | cyan×1 | specific_item / cyan_1 | 1 / west | P1:P1-1 | A | R6 identity/count 경계 | 미측정 |
| [s5_moved_dropped_item_v2.json:28](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L28) `order-2` | red×2 | kind_fungible / 지정 없음 | 1 / west | P2:P2-1 | B | R2 색상 | 미측정 |
| [s5_moved_dropped_item_v2.json:40](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L40) `order-3` | can×1 | kind_fungible / 지정 없음 | 1 / any | P1:P1-2 | C | R1/R2 can | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s5_moved_dropped_item_v2.json:65](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L65) `cyan_1` | order-1 / cyan | (0.4, -2.45, 0) | P1-1→A | west: (0.245, -2.45, 0) | 미측정 |
| [s5_moved_dropped_item_v2.json:76](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L76) `red_1` | order-2 / red | (1, -2.45, 0) | P2-1→B | west: (0.845, -2.45, 0) | 미측정 |
| [s5_moved_dropped_item_v2.json:87](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L87) `red_2` | order-2 / red | (1.6, -2.45, 0) | P2-1→B | west: (1.445, -2.45, 0) | 미측정 |
| [s5_moved_dropped_item_v2.json:98](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L98) `can_1` | order-3 / can | (0.4, -0.85, 0) | P1-2→C | any: (0.245, -0.85, 0) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| door_1 (door) | (2.2, 0.05) / (0.025, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |

사건:

- [s5_moved_dropped_item_v2.json:112](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L112) `cyan_1_moved` / `item_moved` / **30.0 SIM초**.
  - target: `{"item_id":"cyan_1","to_pose_m":[-0.2,0.75,0.0]}`.
  - discovery(비공개 설계): `{"kind":"own_camera_near_anchor","anchor":"P1-1","radius_m":1.0}`. 실제 시야·발견은 미측정.
  - 이미 파지 중이면 host 구현은 `none_item_held`. 원본 initial_location은 갱신하지 않는다.

- [s5_moved_dropped_item_v2.json:134](../../configs/zone_study_scenarios_v2/s5_moved_dropped_item_v2.json#L134) `red_1_dropped` / `item_dropped` / **62.5 SIM초**.
  - target: `{"item_id":"red_1"}`.
  - discovery(비공개 설계): `{"kind":"own_camera_self"}`. 실제 시야·발견은 미측정.
  - 미파지면 `none_item_not_held`, 효과 있는 낙하와 분모 분리. 그 시점 낙하 위치는 미산정.

## s6_novel_relation_v2

지도 `zone_wide_two_doors_final_v1`, seeds `[651, 652, 653]`, 주문행 3, 물건 3.

| 원본 주문 | 종류×개수 | identity / 지정 ID | 필요 인원·역할 | pickup | 목적지 | 실행 지원 차이 | 물리 |
|---|---|---|---|---|---|---|---|
| [s6_novel_relation_v2.json:13](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L13) `order-1` | can×1 | specific_item / can_1 | 1 / any | P2:P2-2 | C | R1/R2 can | 미측정 |
| [s6_novel_relation_v2.json:28](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L28) `order-2` | long_beam×1 | specific_item / beam_1 | 2 / end_neg/end_pos | P2:P2-2 | A | R1/R3/R4 혼합·짝·자세 | 미측정 |
| [s6_novel_relation_v2.json:43](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L43) `order-3` | cyan×1 | kind_fungible / 지정 없음 | 1 / west | P1:P1-1 | B | R6 identity/count 경계 | 미측정 |

| 원본 placement | order / kind | 시작 pose | slot→목적지 | catalogue base 정류장(역할: pose) | 물리 |
|---|---|---|---|---|---|
| [s6_novel_relation_v2.json:68](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L68) `beam_1` | order-2 / long_beam | (1.1, -0.85, 1.5708) | P2-2→A | end_neg: (1.100002, -1.275, 1.5708); end_pos: (1.099998, -0.425, -1.570793) | 미측정 |
| [s6_novel_relation_v2.json:80](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L80) `can_1` | order-1 / can | (1.45, -0.85, 0) | P2-2→C | any: (1.295, -0.85, 0) | 미측정 |
| [s6_novel_relation_v2.json:92](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json#L92) `cyan_1` | order-3 / cyan | (0.4, -2.45, 0) | P1-1→B | west: (0.245, -2.45, 0) | 미측정 |

| 통로 | 중심 / half extent | 폭·축·차선 | 방향 요구 | 물리 |
|---|---|---|---|---|
| door_narrow (door) | (2.2, 0.05) / (0.025, 0.25) | 0.5 m / x / 1 | 서→동 출하, 동→서 복귀 별도 | 미측정 |
| door_wide (door) | (2.2, -2.625) / (0.025, 0.5) | 1.0 m / x / 2 | 서→동 출하, 동→서 복귀 별도 | 미측정 |

사건:

- 없음. s6의 회전/후퇴 순서는 시간 사건이 아닌 설계 의도다.

## 경로 길이와 방향

아래는 evaluator의 **벽만 있는 운반 자세 경로**다. m는 병진 누적 길이, °는 yaw 누적 변화이며 최소 시간/물리 관절 회전이 아니다. 정류장까지의 실제 접근, 파지/해제, 대기, 여러 물건 배송 순서와 내려놓은 물건 간 간섭, 동료 회피는 포함하지 않는다. `blocking` 검사는 다른 초기 물건을 넣어 별도로 PASS했지만 그 자세열은 이 길이와 동일하다고 가정하지 않는다. 모든 정방향 기본 경로와 역순 sweep이 통과했고, 이는 동시 양방향 교행/양보의 증명이 아니다.

| 시나리오/물건 | 정적 길이 m | 누적 yaw ° | 기록된 목표 pose | 문 중심선 교차 | 실제 통과/SIM초 |
|---|---:|---:|---|---|---|
| s1/cyan_1 | 6.95 | 0.0 | (4.35, -0.05, 0) | door_1:west_to_east | 미측정 |
| s1/cyan_2 | 6.35 | 0.0 | (4.35, -0.05, 0) | door_1:west_to_east | 미측정 |
| s1/red_1 | 7.15 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s1/can_1 | 3.30 | 0.0 | (2.75, -0.2, 0) | door_1:west_to_east | 미측정 |
| s1/tile_1 | 5.55 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s1/beam_1 | 3.35 | 180.0 | (4.35, 0.2, -1.5708) | door_1:west_to_east | 미측정 |
| s1/green_1 | 3.90 | 0.0 | (2.75, -0.2, 0) | door_1:west_to_east | 미측정 |
| s2/cyan_1 | 5.15 | 0.0 | (4.35, 0.15, 0) | door_narrow:west_to_east | 미측정 |
| s2/cyan_2 | 4.55 | 0.0 | (4.35, 0.15, 0) | door_narrow:west_to_east | 미측정 |
| s2/green_1 | 3.30 | 0.0 | (2.75, -0.2, 0) | door_narrow:west_to_east | 미측정 |
| s2/crate_1 | 3.35 | 0.0 | (4.45, -2.3, 0) | door_wide:west_to_east | 미측정 |
| s3/beam_1 | 4.45 | 180.0 | (4.35, 0.2, -1.5708) | door_1:west_to_east | 미측정 |
| s3/cyan_1 | 7.75 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s3/tile_1 | 2.70 | 0.0 | (2.75, -0.2, 0) | door_1:west_to_east | 미측정 |
| s3/red_1 | 7.15 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s4/cyan_1 | 7.45 | 30.0 | (4.35, 1.05, -0.5236) | corridor_1:west_to_east | 미측정 |
| s4/red_1 | 9.35 | 30.0 | (4.35, -1.45, -0.5236) | corridor_1:west_to_east | 미측정 |
| s4/green_1 | 7.50 | 120.0 | (3.25, -0.2, -2.0944) | corridor_1:west_to_east | 미측정 |
| s4/beam_1 | 4.05 | 90.0 | (4.6, 1.05, -3.1416) | corridor_1:west_to_east | 미측정 |
| s5/cyan_1 | 6.35 | 0.0 | (4.35, -0.05, 0) | door_1:west_to_east | 미측정 |
| s5/red_1 | 7.15 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s5/red_2 | 6.55 | 0.0 | (4.35, -1.45, 0) | door_1:west_to_east | 미측정 |
| s5/can_1 | 3.30 | 0.0 | (2.75, -0.2, 0) | door_1:west_to_east | 미측정 |
| s6/beam_1 | 4.10 | 180.0 | (4.35, 0, -1.5708) | door_narrow:west_to_east | 미측정 |
| s6/can_1 | 2.25 | 0.0 | (2.75, -0.2, 0) | door_narrow:west_to_east | 미측정 |
| s6/cyan_1 | 3.95 | 0.0 | (4.35, -2.45, 0) | door_wide:west_to_east | 미측정 |

| 사건 후 정적 경로 | 물건 | 길이 m | 중심선 교차 | 물리 효과/발견/통과 |
|---|---|---:|---|---|
| s2/door_narrow_blocked | cyan_1 | 9.55 | door_wide:west_to_east | 미측정 |
| s2/door_narrow_blocked | cyan_2 | 8.95 | door_wide:west_to_east | 미측정 |
| s2/door_narrow_blocked | green_1 | 4.50 | door_wide:west_to_east | 미측정 |
| s2/door_narrow_blocked | crate_1 | 3.35 | door_wide:west_to_east | 미측정 |
| s5/cyan_1_moved | cyan_1 | 5.15 | door_1:west_to_east | 미측정 |
| s5/cyan_1_moved | red_1 | 7.15 | door_1:west_to_east | 미측정 |
| s5/cyan_1_moved | red_2 | 6.55 | door_1:west_to_east | 미측정 |
| s5/cyan_1_moved | can_1 | 3.30 | door_1:west_to_east | 미측정 |

## 정류장과 staging 비용의 알려진 부분

아래 거리는 세 후보 spawn에서 각 grasp base까지의 직선 하한 범위다. 장애물 우회/실제 actor 배정을 포함하지 않고, 실제 접근 경로가 존재한다고 증명하지 않는다. 역할별 모든 후보 값은 inventory JSON에 있다. 실제 robot spawn→prestation→station→정렬 경로와 SIM초는 미측정이다.

| 배치/역할 | 실제 설정에서 계산한 base XYyaw | spawn 직선 하한 m (min–max) | 접근/정렬/파지/staging SIM초 |
|---|---|---:|---|
| s1/beam_1/end_neg | (1.275002, 0.025, 1.5708) | 2.189–3.113 | 미측정 |
| s1/beam_1/end_pos | (1.274998, 0.875, -1.570793) | 2.150–3.779 | 미측정 |
| s2/crate_1/west | (1.02, -2.15, 0) | 1.873–3.284 | 미측정 |
| s2/crate_1/east | (1.53, -2.15, -3.141593) | 2.382–3.599 | 미측정 |
| s3/beam_1/end_neg | (0.125002, 0.025, 1.5708) | 1.107–2.475 | 미측정 |
| s3/beam_1/end_pos | (0.124998, 0.875, -1.570793) | 1.028–3.274 | 미측정 |
| s4/beam_1/end_neg | (1.275002, 0.025, 1.5708) | 2.189–3.113 | 미측정 |
| s4/beam_1/end_pos | (1.274998, 0.875, -1.570793) | 2.150–3.779 | 미측정 |
| s6/beam_1/end_neg | (1.100002, -1.275, 1.5708) | 1.996–2.671 | 미측정 |
| s6/beam_1/end_pos | (1.099998, -0.425, -1.570793) | 1.996–2.671 | 미측정 |
| s6/can_1/any | (1.295, -0.85, 0) | 2.145–2.561 | 미측정 |
| s6/cyan_1/west | (0.245, -2.45, 0) | 1.113–3.194 | 미측정 |

정적0.05 m 격자의 출발점을 원본 pose로 착각하지 않도록 data에 `authored_start_pose_m`, `path_m_rad[0]`, `authored_start_to_lattice_swept`를 함께 보존했다. 경로 길이에는 최초 원본→격자 오프셋이 포함되지 않는다. 이 오프셋과 최종 zone slot 정렬도 실제 cap 산정 때 별도 항이다.

s1의 원본 설명은 “5인분 단독 작업”, s3는 “단독 작업2건”이라고 쓰지만 주문/placement는 각각 **단독6물건**, **단독3물건**이다. 이번 표/분모는 원본 배열을 사용했으며 주석을 수정하지 않았다.
