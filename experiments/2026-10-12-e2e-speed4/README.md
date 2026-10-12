# E2E speed4 — DEV 후보, 새 코호트
- Refs #448 #453; base `codex/e2e-idle`; 번들 등록 없음, speed3 합성용.
- 사전 기준: seed61001·60 SIM초 cProfile; 예외 0·시간/프레임 증가·이동/명령/탐색 진입을 3–5분에 확인; 완주 성공으로 해석하지 않음.
- 토글(JSON `--speed4`): `render_half`, `rbpf_particles`(0/30/50), `floor_ray_stride`(1/2/4), `moving_observation_stride`(1/2), `vector_envelopes`; 모두 기본 off(0/1/false).
- 후보: baseline, render_half, particles50+ray2, moving2, vector_envelopes, combined; 저장 자기 RGB/명령 재생과 평가 전용 상대 위치 오차를 분리한다.
- 저해상도는 320×240 렌더→640×480 선형 확대(고정 보정 호환); 위치/FOV 불변. 바닥 레이만 줄이고 벽 끝점은 유지; 이동 처리만 2.5Hz, hold/turn/transport/VO는 5Hz.
- VM3 단일 추가 실행; 기존 짝 측정 중이면 대기, VM 수명 변경 없음. 원본은 VM3 영속 경로, Mac에는 가벼운 파일만.
- 권장(기능 확인 후): `render_half=false, rbpf_particles=50, floor_ray_stride=2, moving_observation_stride=1, vector_envelopes=true`; 절반 해상도 B 검출은 10/10→2/10으로 기각. 측정·기능 확인은 `summary.json`; 기존 60초 profile은 `/Users/changmin/projects/ugrp/outputs/e2e-speed/fetch-lite/e2e13-profile-s61001/`.
- 근거: [OpenCV resize](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html), [Nav2 AMCL](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [NumPy broadcasting](https://numpy.org/doc/stable/user/basics.broadcasting.html), [Python profile](https://docs.python.org/3.12/library/profile.html). 해상도 축소·입자/관측 예산·벡터화의 표준 방법을 사용; 효능은 별도 측정.
