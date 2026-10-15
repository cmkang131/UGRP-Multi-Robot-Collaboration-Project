# 참고 자료와 확인 범위

2026-10-16 조회. API의 실제 사용은 설치된 MJWarp dev `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148` / MuJoCo3.16 / Warp1.15와 simalt5 호환 코드에 고정한다. 웹 HEAD의 기능을 설치본에 있다고 가정하지 않는다.

- [공식 MJWarp 설명·배치·CUDA graph·overflow](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html). 고처리량/낮은 단일 지연의 차이, put_data nworld/nconmax/njmax, 메모리·solver 튜닝을 확인. 이 설명이 이 장면에서의 가속을 보증하지 않는다.
- [고정 batch renderer](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/render.py). 설치본 `refit_bvh → render → get_rgb`, world별 RGB readback을 사용. 부분 alpha 처리 차이는 simalt3와 이번 몽타주에서 남아 있으며 구역 숨김/색 변경으로 우회하지 않는다.
- [공식 README batch rendering](https://github.com/google-deepmind/mujoco_warp#batch-rendering). mesh/texture/heterogeneous camera support 설명. 우리 관측의 의미 동등성이나 교사 성공의 증거가 아니다.
- [선택 world 렌더 요청 #1373](https://github.com/google-deepmind/mujoco_warp/issues/1373). 고정 batch render가 전체 world 대상으로 돈다는 성능 제약을 확인. 이식은 모든 세계를 10Hz로 렌더하며 미관측 world 프레임을 생략하지 않는다. issue의 HEAD 지원 여부를 설치본에 승계하지 않는다.
- [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground), [vision PPO 실행 예](https://github.com/google-deepmind/mujoco_playground/blob/main/learning/train_jax_ppo.py). GPU robot learning/vision 관측 배치의 공개 예. 이번에는 JAX/Brax/학습 환경을 추가하지 않았다. UGRP의 자기 관측 경계를 자체 transport로 유지한다.
- [큰 배치 메모리 이슈 #926](https://github.com/google-deepmind/mujoco_warp/issues/926). buffer/workspace 관리 조사 참고. contact/friction/solver 물리 상수는 줄이지 않는다.
- [부분 투명도 등 issue 검색](https://github.com/google-deepmind/mujoco_warp/issues?q=alpha+transparency+render): 이번 검색에서 이 장면에 적용·검증된 수정은 확보하지 못했다. 사례가 존재하지 않는다는 뜻은 아니다.

프로젝트 근거: PR #524의 simalt3 migration-assessment, simalt4·simalt5 README/summary, docs/act_execution_decisions.md 4절, frozen ACT11 solo runner/teacher/Score/CameraRobotPort, ACT14/15 기록과 ACT16a 미승인 계획. ACT16 새 평가 시드91620–91659는 이 파일럿에 쓰지 않고 기존 gate source plans를 재사용했다. 과거 C/GCP1 성공률은 새 MJWarp 관문으로 승계하지 않는다.
