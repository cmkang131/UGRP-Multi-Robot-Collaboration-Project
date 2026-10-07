# 기존 실패10 개발 결과 (v2 → v3)

oracle 두 seed는 같은 궤적이며 독립 성공 증거가 아니다. 시작 겹침4는 성공에서 제외하되 원 표본에 보존한다.
B 0/10 → 2/10, 유효6 중2. 새32/기존22 성공과 합산하지 않는다. 모든 시간은 modeled s.

| 쌍 | 종료 v2 → v3 | 시간 s | 거리 m | coverage % | 충돌 | B 가시/검출(v3) |
|---|---|---:|---:|---:|---:|---:|
| s1-H-4701-static_map | HOST_SETUP_ERROR → HOST_SETUP_ERROR | 0.0 → 0.0 | 0.000 → 0.000 | 0.0 → 0.0 | 0 → 0 | 0/0 |
| s1-H-4702-static_map | HOST_SETUP_ERROR → HOST_SETUP_ERROR | 0.0 → 0.0 | 0.000 → 0.000 | 0.0 → 0.0 | 0 → 0 | 0/0 |
| s4-G-4701-static_map | recovery_exhausted → recovery_exhausted | 161.0 → 125.0 | 5.064 → 4.650 | 39.7 → 39.5 | 0 → 0 | 0/0 |
| s4-G-4702-static_map | recovery_exhausted → recovery_exhausted | 161.0 → 125.0 | 5.064 → 4.650 | 39.7 → 39.5 | 0 → 0 | 0/0 |
| s4-H-4701-static_map | HOST_SETUP_ERROR → HOST_SETUP_ERROR | 0.0 → 0.0 | 0.000 → 0.000 | 0.0 → 0.0 | 0 → 0 | 0/0 |
| s4-H-4702-static_map | HOST_SETUP_ERROR → HOST_SETUP_ERROR | 0.0 → 0.0 | 0.000 → 0.000 | 0.0 → 0.0 | 0 → 0 | 0/0 |
| s5-G-4701-static_map | recovery_exhausted → recovery_exhausted | 131.0 → 104.0 | 3.695 → 3.695 | 70.2 → 70.2 | 0 → 0 | 5/5 |
| s5-G-4702-static_map | recovery_exhausted → recovery_exhausted | 131.0 → 104.0 | 3.695 → 3.695 | 70.2 → 70.2 | 0 → 0 | 5/5 |
| s8-H-4701-static_map | collision → B_confirmed | 2.7 → 74.0 | 0.054 → 1.477 | 4.8 → 46.5 | 1 → 2 | 14/14 |
| s8-H-4702-static_map | collision → B_confirmed | 2.7 → 74.0 | 0.054 → 1.477 | 4.8 → 46.5 | 1 → 2 | 14/14 |

| 유효 개발 원인 / 각2seed | v3 세부 |
|---|---|
| s4-G | predicted reject {'follow': 6, 'spin': 1}; final ['round_robin_exhausted']; 3-view baseline 0.000000000m; contact []; backup completed [] |
| s5-G | predicted reject {'follow': 6, 'spin': 1, 'backup': 1}; final ['round_robin_exhausted']; 3-view baseline 0.000026585m; contact []; backup completed [] |
| s8-H | predicted reject {'follow': 8}; final []; 3-view baseline 0.119951028m; contact [2.7, 2.8500000000000005]; backup completed [10.999999999999995] |
