# E2E speed4 — DEV 후보, 새 코호트
- Refs #448 #453; base `codex/e2e-idle`; 번들 등록 없음, speed3 합성용.
- 사전 기준: seed61001·60 SIM초 cProfile; 예외 0·시간/프레임 증가·이동/명령/탐색 진입을 3–5분에 확인; 완주 성공으로 해석하지 않음.
- 토글(JSON `--speed4`): `render_half`, `rbpf_particles`(0/30/50), `floor_ray_stride`(1/2/4), `moving_observation_stride`(1/2), `vector_envelopes`, `vector_door_pairs`; 모두 기본 off(0/1/false).
- 검증: 76 tests 통과; 저장 자기 RGB/명령 12 SIM초 재생 180/180 정상. 권장 조합 XY RMSE 7.0/7.7/7.5cm(기존 7.6/7.9/7.7); 벡터화 위치·명령 180/180 동일. 완주·실시간 효능은 미검증.
- 저해상도는 320×240 렌더→640×480 선형 확대(고정 보정 호환); 위치/FOV 불변. 바닥 레이만 줄이고 벽 끝점은 유지; 이동 처리만 2.5Hz, hold/turn/transport/VO는 5Hz.
- VM3 단일 추가 실행 0/4 완료(초기화/relay/HTTP400); 이후 deallocated 확인, 재시작 없음. ARM 원본 해시 137/137·가벼운 회수 131/131 확인; 실패 원본 1건 VM3 미회수.
- 권장: `render_half=false, rbpf_particles=50, floor_ray_stride=2, moving_observation_stride=1, vector_envelopes=true, vector_door_pairs=true`; B 10/10→2/10·이동 stride2 r2 RMSE 7.9→14.9cm로 두 후보 제외. 절감 실측 없음; 기존 profile의 낙관적 선형 추정 입자14.9·레이74.3초/60 SIM초, 벡터화 Python self 비용 상한74.5초(합산 금지). 근거·한계·원본·해시는 `summary.json`과 `artifact-sha256.tsv`.
- 근거: [OpenCV resize](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html), [Nav2 AMCL](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [NumPy broadcasting](https://numpy.org/doc/stable/user/basics.broadcasting.html), [Python profile](https://docs.python.org/3.12/library/profile.html). 해상도 축소·입자/관측 예산·벡터화의 표준 방법을 사용; 효능은 별도 측정.
