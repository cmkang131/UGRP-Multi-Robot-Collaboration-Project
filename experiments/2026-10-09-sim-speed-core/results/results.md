# 최종 고정 입력 동등성·속도 결과

실행 SHA `725f45b155fda3f7dc93beba782b848ca3b4a6dd`. 각 경로 30 SIM초, ABBA, n=2/조건. 초기화/reset·프로파일 실행은 wall/SIM 평균에서 제외.
부하 평균은 각 조건의 두 반복 시작/끝 1·5·15분 loadavg의 산술 평균이다.

|경로|off wall/SIM|on wall/SIM|wall 감소|off 부하 1/5/15|on 부하 1/5/15|동일 행동 파일/반복|
|---|---:|---:|---:|---|---|---:|
|s2 seed1065|1.083963|0.887058|18.17%|2.78/3.75/4.65|2.77/3.74/4.65|625|
|s3 seed14201|1.871652|1.674306|10.54%|2.87/3.39/4.32|3.05/3.44/4.34|1825|
|egomap seed49001|1.199962|0.997754|16.85%|3.08/3.14/4.02|2.50/3.00/3.97|172|

각 반복 120,000스텝의 integration-state+relay 누적 해시와 최종 상태가 동일하다. 명령·궤적·접촉·판정·영상·scene 등 위 파일은 직접 bytes 차이0이다.
모드가 다른 `v7-speedups.json`과 `runtime-bundle.json` 2개는 의도적인 출처 차이다. 각 모드/실제 enabled/모듈 SHA/입력 bundle 연결도 별도 검증했다.
S3 판정은 원본과 같은 EVALUATOR_ERROR/ContractViolation이다. 오류 문자열까지 동일하며 임무 성공이 아니다. 전체 온라인 제어기·실물 검증은 포함하지 않는다.
자산의 Git export 경로가 달라 원본 scene 비교에서는 file 경로만 자산 SHA로 치환했다. 자산 bytes 및 나머지 XML 동일, on/off XML 자체는 raw bytes 동일이다.

|경로/순서|mode|wall s|wall/SIM|시작 부하 1/5/15|끝 부하 1/5/15|
|---|---|---:|---:|---|---|
|s2/A1|off|32.009865|1.066996|2.77/3.97/4.79|2.70/3.81/4.70|
|s2/B1|relay-cache-v1|26.240015|0.874667|2.70/3.81/4.70|2.80/3.74/4.65|
|s2/B2|relay-cache-v1|26.983485|0.899450|2.80/3.74/4.65|2.78/3.65/4.58|
|s2/A2|off|33.027898|1.100930|2.78/3.65/4.58|2.86/3.58/4.52|
|s3/A1|off|58.193855|1.939795|2.95/3.59/4.52|3.46/3.59/4.45|
|s3/B1|relay-cache-v1|51.521097|1.717370|3.46/3.59/4.45|3.17/3.48/4.36|
|s3/B2|relay-cache-v1|48.937253|1.631242|3.15/3.48/4.35|2.42/3.22/4.20|
|s3/A2|off|54.105247|1.803508|2.42/3.22/4.20|2.66/3.15/4.11|
|egomap/A1|off|35.622485|1.187416|2.64/3.13/4.09|2.72/3.10/4.04|
|egomap/B1|relay-cache-v1|29.880871|0.996029|2.72/3.10/4.04|2.44/2.99/3.96|
|egomap/B2|relay-cache-v1|29.984391|0.999480|2.44/2.99/3.96|2.40/2.92/3.90|
|egomap/A2|off|36.375235|1.212508|2.40/2.92/3.90|4.55/3.43/4.04|

## egomap off Python 상위 10개

분모는 C 확장/대기를 포함한 cProfile 전체 self time. Python 항목만 순위화하며 cumulative 중복 합산 없음.
|함수|호출|self s|비율|cumulative s|
|---|---:|---:|---:|---:|
|`sim/masterpi_drive_friction_v7.py:52:command_step`|360,000|3.10283|7.564%|9.41609|
|`numpy/lib/_arraysetops_impl.py:806:_isin`|360,000|2.39483|5.838%|4.61731|
|`sim/masterpi_drive_friction_v7.py:212:_physics_step_for`|120,000|0.71896|1.753%|36.46660|
|`numpy/_core/fromnumeric.py:66:_wrapreduction`|720,000|0.39289|0.958%|0.71802|
|`numpy/_core/numeric.py:97:zeros_like`|360,000|0.29665|0.723%|0.40231|
|`numpy/lib/_arraysetops_impl.py:958:isin`|360,000|0.25088|0.612%|4.96790|
|`scripts/benchmark_v7_speed.py:199:step`|120,000|0.24316|0.593%|37.77336|
|`sim/final_pair_highpose_clock.py:76:advance_to`|151|0.22475|0.548%|38.82223|
|`numpy/_core/fromnumeric.py:86:_wrapreduction_any_all`|361,186|0.20473|0.499%|0.36113|
|`sim/camera_robot_port.py:278:_finite_number`|360,006|0.14056|0.343%|0.22982|

## egomap relay-cache-v1 Python 상위 10개

분모는 C 확장/대기를 포함한 cProfile 전체 self time. Python 항목만 순위화하며 cumulative 중복 합산 없음.
|함수|호출|self s|비율|cumulative s|
|---|---:|---:|---:|---:|
|`sim/masterpi_drive_friction_v7.py:212:_physics_step_for`|120,000|0.64583|1.975%|28.29408|
|`sim/v7_exact_speedups.py:41:command_step`|360,000|0.43447|1.329%|1.27695|
|`sim/v7_exact_speedups.py:47:<genexpr>`|1,080,000|0.22441|0.686%|0.29072|
|`scripts/benchmark_v7_speed.py:199:step`|120,000|0.20862|0.638%|29.54080|
|`sim/final_pair_highpose_clock.py:76:advance_to`|151|0.20449|0.626%|30.50086|
|`sim/v7_exact_speedups.py:44:<genexpr>`|1,080,000|0.18457|0.565%|0.18457|
|`sim/camera_robot_port.py:278:_finite_number`|360,006|0.12898|0.395%|0.20816|
|`sim/v7_exact_speedups.py:48:<genexpr>`|1,080,000|0.11412|0.349%|0.26815|
|`sim/camera_robot_port.py:246:_advance_servos`|360,005|0.11287|0.345%|0.14369|
|`sim/camera_robot_port.py:196:tick`|360,000|0.11018|0.337%|0.46566|

추가 미세 개선인 torque 속성 직접 보관은 캐시와 함께 측정됐다. 공통 step의 불필요한 zeros 할당 제거는 양쪽에 동일하게 적용되어 이 표에서 독립 효과를 주장하지 않는다.
mj_forward는 이번에도 제거하지 않았다. 선행 #415의 카메라 갱신 호출 확인과 MuJoCo의 적분 후 파생 상태 설명에 따라 유지했다.
v1의 referee 종료·v2의 감독 세션 종료 대기는 raw/사유를 보존했다. v2는 물리 실행0이며 명령은 새 출력 경로 외 v3와 동일하다.
