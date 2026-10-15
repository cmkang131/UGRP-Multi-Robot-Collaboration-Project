# reloc16 거부·관문 표

모든 수는 같은 실행의 순서 있는 프레임/컬럼/이벤트 수다. 실행 성공률로 합산하지 않는다. 정적56자세 자격 외32자세는 unknown이다.

|인코딩|자세→카메라자격|컬럼→색/계량지지→직선→연결|첫 거부(색/계량·직선·연결)|
|---|---:|---:|---:|
|png|88→56|5376→4853→4772→4691|523/81/81|
|jpeg90|88→56|5376→4756→4700→4588|620/56/112|
|pil82|88→56|5376→4680→4622→4537|696/58/85|

|라운드·실행|누적 통과|첫 거부 사유:수|
|---|---|---|
|R1 reloc16-r1-selfmap-93584-v5-93635d6e|frames:0|HOST_ERROR:1|
|R1 reloc16-r1-selfmap-93583-v5-93635d6e|frames:0|HOST_ERROR:1|
|R1 reloc16-r1-carry-93266-v5-93635d6e|exposures:750 → accepted:66 → scorable:66 → correct:66|unknown_servo_settle:116; unknown_yaw_observability:279; unknown_static_support:205; unknown_spatial_revalidation:78; pending_next_rgb:6|
|R1 reloc16-r1-carry-93315-v5-93635d6e|exposures:605 → accepted:20 → scorable:20 → correct:20|unknown_servo_settle:114; unknown_yaw_observability:121; unknown_static_support:341; pending_next_rgb:2; unknown_spatial_revalidation:7; route:1|
|R1 reloc16-r1-selfmap-93584-v1-93635d6e|frames:0|HOST_ERROR:1|
|R1 reloc16-r1-selfmap-93583-v1-93635d6e|frames:0|HOST_ERROR:1|
|R1 reloc16-r1-selfmap-93584-v5-93635d6e-hostretry1|frames:301 → sensor_update:134 → pf_resolved:97 → dominant_mode:97 → raw_covariance:97 → independent_axes:87 → global_unique:2 → three_views:0 → registered:0|sensor_update:167; global_unique:85; pf_resolved:37; independent_axes:10; three_views:2|
|R1 reloc16-r1-selfmap-93583-v5-93635d6e-hostretry1|frames:301 → sensor_update:142 → pf_resolved:83 → dominant_mode:83 → raw_covariance:83 → independent_axes:64 → global_unique:1 → three_views:0 → registered:0|sensor_update:159; global_unique:63; pf_resolved:59; independent_axes:19; three_views:1|
|R1 reloc16-r1-selfmap-93584-v1-93635d6e-hostretry1|frames:90 → sensor_update:43 → pf_resolved:34 → dominant_mode:34 → raw_covariance:34 → independent_axes:34 → global_unique:29 → three_views:2 → registered:2|sensor_update:47; three_views:27; pf_resolved:9; global_unique:5|
|R1 reloc16-r1-selfmap-93583-v1-93635d6e-hostretry1|frames:144 → sensor_update:72 → pf_resolved:55 → dominant_mode:55 → raw_covariance:55 → independent_axes:55 → global_unique:30 → three_views:2 → registered:2|sensor_update:72; three_views:28; global_unique:25; pf_resolved:17|
|R2 reloc16-r2-selfmap-93584-v5-5f8b3eb2|frames:156 → sensor_update:52 → pf_resolved:35 → dominant_mode:35 → raw_covariance:35 → independent_axes:34 → global_unique:26 → three_views:2 → registered:2|sensor_update:104; three_views:24; pf_resolved:17; global_unique:8; independent_axes:1|
|R2 reloc16-r2-selfmap-93583-v5-5f8b3eb2|frames:116 → sensor_update:50 → pf_resolved:44 → dominant_mode:44 → raw_covariance:44 → independent_axes:43 → global_unique:30 → three_views:3 → registered:3|sensor_update:66; three_views:27; global_unique:13; pf_resolved:6; independent_axes:1|
|R2 reloc16-r2-carry-93266-v5-5f8b3eb2|exposures:750 → accepted:58 → scorable:58 → correct:58|unknown_servo_settle:162; unknown_yaw_observability:113; unknown_static_support:358; unknown_spatial_revalidation:52; pending_next_rgb:6; unknown_repeated_rgb:1|
|R2 reloc16-r2-carry-93315-v5-5f8b3eb2|exposures:750 → accepted:39 → scorable:39 → correct:39|unknown_servo_settle:204; unknown_yaw_observability:313; unknown_static_support:164; pending_next_rgb:4; unknown_spatial_revalidation:26|
|R3 reloc16-r3-selfmap-93584-v5-df8115a5|frames:301 → sensor_update:124 → pf_resolved:0 → dominant_mode:0 → raw_covariance:0 → independent_axes:0 → global_unique:0 → three_views:0 → registered:0|sensor_update:177; pf_resolved:124|
|R3 reloc16-r3-selfmap-93583-v5-df8115a5|frames:301 → sensor_update:108 → pf_resolved:0 → dominant_mode:0 → raw_covariance:0 → independent_axes:0 → global_unique:0 → three_views:0 → registered:0|sensor_update:193; pf_resolved:108|
|R3 reloc16-r3-carry-93266-v5-df8115a5|exposures:750 → accepted:8 → scorable:8 → correct:8|unknown_servo_settle:108; unknown_yaw_observability:349; unknown_static_support:182; unknown_spatial_revalidation:100; pending_next_rgb:3|
|R3 reloc16-r3-carry-93315-v5-df8115a5|exposures:750 → accepted:28 → scorable:28 → correct:28|unknown_servo_settle:89; unknown_yaw_observability:389; unknown_static_support:190; pending_next_rgb:8; unknown_spatial_revalidation:46|

막은 물체·최소 틈은 JSON의 각 거부 항목에 있다. 위치 추정/호스트/이미지 관문은 물리 틈이 아니므로 null과 명시적 not_applicable 사유를 기록한다. 물리 envelope 거부는 실제 원본의 blocker/minimum_gap을 유지한다.

원본 경로·원본 manifest/result SHA256: [inventory.json](inventory.json). 순차 누적·원본 경로·재현 명령: [rejection-table.json](rejection-table.json). 초기 분포: [rejection-before.json](rejection-before.json).
