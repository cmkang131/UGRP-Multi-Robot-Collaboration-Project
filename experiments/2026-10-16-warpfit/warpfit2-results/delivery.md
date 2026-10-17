# warpfit2 — native-v1 다음 runtime 비교

3라운드25/25 고정명령 배치 완주, HOST_ERROR0·cap_end0. 기본값 변경0. 상자 선택30/30은 모든 비교에서 유지했고 빔은 각16/16 또는64/64 짧은 유지를 충족했다. 동일 reset 복제이며 독립 seed 일반화·교사/학생/E2E 관문이 아니다.

|round/N|runtime|구간|기준 GPU ms/step|후보 GPU ms/step|기준/후보|
|---|---|---|---:|---:|---:|
|R1/N16|warp_upstream_plane_v1|box repeat1|0.647283|0.655781|0.9870×|
|R1/N16|warp_upstream_plane_v1|box repeat2|0.644866|0.657857|0.9803×|
|R1/N16|warp_upstream_plane_v1|beam repeat1|2.916601|3.325936|0.8769×|
|R1/N16|warp_upstream_plane_v1|drive repeat1|2.132826|2.245182|0.9500×|
|R2/N16|warp_measured_capacity_v1|box repeat1|0.653706|0.645764|1.0123×|
|R2/N16|warp_measured_capacity_v1|box repeat2|0.647409|0.646097|1.0020×|
|R2/N16|warp_measured_capacity_v1|beam repeat1|2.921521|2.915968|1.0019×|
|R2/N16|warp_measured_capacity_v1|drive repeat1|2.128233|2.119834|1.0040×|
|R3/N64|warp_measured_capacity_v1|box repeat1|0.735464|0.731975|1.0048×|
|R3/N64|warp_upstream_plane_v1|box repeat1|0.735464|0.755769|0.9731×|
|R3/N64|warp_measured_capacity_v1|beam repeat1|3.554833|3.534999|1.0056×|
|R3/N64|warp_upstream_plane_v1|beam repeat1|3.554833|4.053461|0.8770×|
|R3/N64|warp_measured_capacity_v1|drive repeat1|2.410173|2.407292|1.0012×|
|R3/N64|warp_upstream_plane_v1|drive repeat1|2.410173|2.632673|0.9155×|

## 횡펄스: 해당축 부호 있는 변위

같은 tape를 받은 세계들의 중앙값(펄스 끝/정지1초 후)이다. 원본 CSV에는 모든 XY/yaw·tilt·world를 보존한다. FOLDED/PR564 초기 겹침 제거 진단 장면이며 HIGH·생산 보정이 아니다. 400ms·warm 예측값은 미등록으로 null이다.

|round/N|runtime|cold60 mm|warm60 mm|cold400 mm|warm400 mm|
|---|---|---:|---:|---:|---:|
|R1/N16|off|3.150 / 7.065|2.150 / 2.939|43.478 / 50.137|42.627 / 44.203|
|R1/N16|warp_upstream_plane_v1|2.950 / 6.703|1.677 / -0.019|41.013 / 47.299|37.821 / 44.235|
|R2/N16|off|3.153 / 6.940|2.147 / 3.049|43.497 / 50.124|42.627 / 44.086|
|R2/N16|warp_measured_capacity_v1|3.155 / 7.066|2.140 / 3.899|43.485 / 50.142|42.704 / 45.198|
|R3/N64|warp_measured_capacity_v1|3.154 / 6.939|2.141 / 2.934|43.496 / 50.162|42.645 / 46.270|
|R3/N64|warp_upstream_plane_v1|2.951 / 6.701|1.684 / -0.016|41.029 / 46.877|37.850 / 44.228|
|R3/N64|off|3.151 / 7.062|2.140 / 2.927|43.485 / 50.144|42.623 / 44.263|

## 빔 상대 slip P95

|round/N|runtime|slip P95 mm|유지|
|---|---|---:|---:|
|R1/N16|off|0.063008|16/16|
|R1/N16|warp_upstream_plane_v1|0.433418|16/16|
|R2/N16|off|0.067150|16/16|
|R2/N16|warp_measured_capacity_v1|0.066002|16/16|
|R3/N64|warp_measured_capacity_v1|0.069746|64/64|
|R3/N64|warp_upstream_plane_v1|0.433842|64/64|
|R3/N64|off|0.069392|64/64|

기존 교사12mm+전 손가락 양의 힘과 같은 라운드 native-v1 P05/P95로 비교했다. 백분위에서 제외된 프레임은 실제 낙하가 아니다. CUDA event 시간은 고정명령·매step 최대치 기록 커널을 포함하며 setup/JIT·RGB 기록은 제외한다. wall/SIM은 기록·평가를 포함한 배치 지연이며 세계당 상각값과 다르다.
