# 오프라인 프로파일 상위 10개

모두 다른 연구 실행 중의 진단이며 물리 속도 비교가 아니다. self time 비율이며 C 함수도 포함한다.

## 저장 RGB/제어기 (51/51 원본 bytes 일치)

|함수|호출 수|self s|비율|누적 s|
|---|---:|---:|---:|---:|
|`harness/own_map_navigation.py:88:cell`|650,272|1.197548|7.015%|1.862502|
|`harness/floor_goal.py:85:floor_intersections`|102|1.179719|6.910%|1.821391|
|`~:0:<method 'reduce' of 'numpy.ufunc' objects>`|139,969|1.059346|6.205%|1.059346|
|`harness/own_map_navigation.py:135:dense`|102|0.985931|5.775%|1.689756|
|`harness/own_map_navigation.py:89:<genexpr>`|1,950,816|0.617273|3.616%|0.617273|
|`experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py:132:window`|204|0.589390|3.452%|0.604646|
|`~:0:<method 'cumsum' of 'numpy.ndarray' objects>`|816|0.509543|2.985%|0.509543|
|`harness/grid_acceleration.py:60:dda`|32,664|0.446784|2.617%|0.553762|
|`harness/wall_confidence.py:44:weighted_insert`|1,127|0.431164|2.526%|1.562686|
|`~:0:<built-in method numpy.array>`|681,758|0.417126|2.443%|0.417126|

## 발행 모터 relay (144,000회, 물리 0)

|함수|호출 수|self s|비율|누적 s|
|---|---:|---:|---:|---:|
|`sim/masterpi_drive_friction_v7.py:52:command_step`|144,000|2.426740|33.462%|7.252145|
|`numpy/lib/_arraysetops_impl.py:806:_isin`|144,000|1.902102|26.228%|3.560731|
|`~:0:<method 'reduce' of 'numpy.ufunc' objects>`|720,000|0.480836|6.630%|0.480836|
|`numpy/_core/fromnumeric.py:66:_wrapreduction`|288,000|0.272068|3.751%|0.511972|
|`numpy/_core/numeric.py:97:zeros_like`|144,000|0.235216|3.243%|0.314977|
|`numpy/lib/_arraysetops_impl.py:958:isin`|144,000|0.184771|2.548%|3.847390|
|`~:0:<built-in method numpy.asarray>`|720,000|0.161892|2.232%|0.161892|
|`numpy/_core/fromnumeric.py:86:_wrapreduction_any_all`|144,000|0.143036|1.972%|0.252751|
|`~:0:<method 'all' of 'numpy.ndarray' objects>`|288,000|0.115544|1.593%|0.390926|
|`numpy/_core/getlimits.py:399:__init__`|144,000|0.112106|1.546%|0.112106|

