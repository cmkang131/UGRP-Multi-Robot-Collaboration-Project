## 물리 A/B 결과

실행 SHA `86420cb258186d12ce2e99a23cb3cbb2a0f7e715`, source 원본 파일 해시 재확인.

|순서|옵션|wall/SIM|wall s|시작 부하 1/5/15분|종료 부하 1/5/15분|
|---|---|---:|---:|---|---|
|profile|off|1.413916|16.9670|4.98/4.71/5.17|4.31/4.57/5.11|
|A1|off|1.301053|15.6126|4.31/4.57/5.11|4.92/4.68/5.14|
|B1|relay-cache-buffered-v1|1.033589|12.4031|4.92/4.68/5.14|4.20/4.53/5.07|
|B2|relay-cache-buffered-v1|1.082338|12.9881|4.20/4.53/5.07|3.86/4.44/5.04|
|A2|off|1.204848|14.4582|3.86/4.44/5.04|3.54/4.33/4.98|

프로파일 제외 ABBA 평균 1.252950 → 1.057963 wall/SIM (wall 15.56% 감소, 1.184배 처리량). 조건별 n=2.
매 반복 48,000 스텝 누적 integration-state 해시 및 최종 상태 동일. 각 실행 81개 파일 원본 bytes 동일(A1↔A2/B1/B2); 누락 파일·차이 0.
초기화/reset 시간은 표의 timed prefix 밖 별도 sidecar에 기록. cProfile은 속도 평균에 포함하지 않음.
제어 입력을 고정한 12초 검증이며 온라인 제어기나 전체 운반/귀환 완주를 검증한 것은 아니다.

### 동기 물리 재생 cProfile

자기 시간(self time) 비율. C 확장/대기 포함, cumulative 비율의 중복 합산 없음.

|함수|호출 수|self s|비율|cumulative s|
|---|---:|---:|---:|---:|
|`~:0:<built-in method mujoco._functions.mj_step>`|48,000|10.8089|63.73%|10.8089|
|`sim/masterpi_drive_friction_v7.py:52:command_step`|144,000|1.2796|7.54%|3.8813|
|`numpy/lib/_arraysetops_impl.py:806:_isin`|144,000|0.9968|5.88%|1.9093|
|`~:0:<built-in method mujoco._render.mjr_render>`|61|0.4618|2.72%|0.4618|
|`sim/masterpi_drive_friction_v7.py:212:_physics_step_for`|48,000|0.3100|1.83%|15.1303|
|`~:0:<built-in method mujoco._render.mjr_readPixels>`|61|0.3052|1.80%|0.3052|
|`~:0:<method 'update' of '_hashlib.HASH' objects>`|48,000|0.2695|1.59%|0.2695|
|`~:0:<method 'reduce' of 'numpy.ufunc' objects>`|720,589|0.2636|1.55%|0.2636|
|`numpy/_core/fromnumeric.py:66:_wrapreduction`|288,000|0.1574|0.93%|0.2924|
|`numpy/_core/numeric.py:97:zeros_like`|144,000|0.1243|0.73%|0.1680|

### 저장 RGB/제어기 cProfile

자기 시간(self time) 비율. C 확장/대기 포함, cumulative 비율의 중복 합산 없음.

|함수|호출 수|self s|비율|cumulative s|
|---|---:|---:|---:|---:|
|`harness/own_map_navigation.py:88:cell`|650,272|1.1975|7.01%|1.8625|
|`harness/floor_goal.py:85:floor_intersections`|102|1.1797|6.91%|1.8214|
|`~:0:<method 'reduce' of 'numpy.ufunc' objects>`|139,969|1.0593|6.21%|1.0593|
|`harness/own_map_navigation.py:135:dense`|102|0.9859|5.78%|1.6898|
|`harness/own_map_navigation.py:89:<genexpr>`|1,950,816|0.6173|3.62%|0.6173|
|`experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py:132:window`|204|0.5894|3.45%|0.6046|
|`~:0:<method 'cumsum' of 'numpy.ndarray' objects>`|816|0.5095|2.98%|0.5095|
|`harness/grid_acceleration.py:60:dda`|32,664|0.4468|2.62%|0.5538|
|`harness/wall_confidence.py:44:weighted_insert`|1,127|0.4312|2.53%|1.5627|
|`~:0:<built-in method numpy.array>`|681,758|0.4171|2.44%|0.4171|

### 입력 relay만 cProfile

자기 시간(self time) 비율. C 확장/대기 포함, cumulative 비율의 중복 합산 없음.

|함수|호출 수|self s|비율|cumulative s|
|---|---:|---:|---:|---:|
|`sim/masterpi_drive_friction_v7.py:52:command_step`|144,000|2.4267|33.46%|7.2521|
|`numpy/lib/_arraysetops_impl.py:806:_isin`|144,000|1.9021|26.23%|3.5607|
|`~:0:<method 'reduce' of 'numpy.ufunc' objects>`|720,000|0.4808|6.63%|0.4808|
|`numpy/_core/fromnumeric.py:66:_wrapreduction`|288,000|0.2721|3.75%|0.5120|
|`numpy/_core/numeric.py:97:zeros_like`|144,000|0.2352|3.24%|0.3150|
|`numpy/lib/_arraysetops_impl.py:958:isin`|144,000|0.1848|2.55%|3.8474|
|`~:0:<built-in method numpy.asarray>`|720,000|0.1619|2.23%|0.1619|
|`numpy/_core/fromnumeric.py:86:_wrapreduction_any_all`|144,000|0.1430|1.97%|0.2528|
|`~:0:<method 'all' of 'numpy.ndarray' objects>`|288,000|0.1155|1.59%|0.3909|
|`numpy/_core/getlimits.py:399:__init__`|144,000|0.1121|1.55%|0.1121|

### 별도 mj_forward 호출

|호출자|횟수|wall s|
|---|---:|---:|
|`wall_parallax_strafe.py:21:apply`|61|0.013924|

카메라 촬영 전 파생 상태 갱신이다. 적분 후 상태가 달라져 동일 상태 중복으로 제거하지 않았다.
`mj_step` 내부 C forward는 위 Python 호출 수에 중복 포함하지 않는다. 렌더 스레드도 별도 forward 계측에 포함했다.

### Python 함수 상위 10개 (동기 재생)

분모는 cProfile 전체 self time(C 확장·렌더 대기 포함), Python 함수만 정렬했다.

|함수|호출 수|self s|전체 대비|
|---|---:|---:|---:|
|`sim/masterpi_drive_friction_v7.py:52:command_step`|144,000|1.2796|7.54%|
|`numpy/lib/_arraysetops_impl.py:806:_isin`|144,000|0.9968|5.88%|
|`sim/masterpi_drive_friction_v7.py:212:_physics_step_for`|48,000|0.3100|1.83%|
|`numpy/_core/fromnumeric.py:66:_wrapreduction`|288,000|0.1574|0.93%|
|`numpy/_core/numeric.py:97:zeros_like`|144,000|0.1243|0.73%|
|`numpy/lib/_arraysetops_impl.py:958:isin`|144,000|0.1013|0.60%|
|`sim/final_pair_highpose_clock.py:76:advance_to`|61|0.0896|0.53%|
|`numpy/_core/fromnumeric.py:86:_wrapreduction_any_all`|144,467|0.0840|0.50%|
|`sim/camera_robot_port.py:278:_finite_number`|144,005|0.0574|0.34%|
|`scripts/benchmark_egomap_sim_speed.py:91:step`|48,000|0.0556|0.33%|
