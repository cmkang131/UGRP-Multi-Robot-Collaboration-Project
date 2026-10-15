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

확장 조사: 설치된 고정 `io.put_model`(287행)의 `batch_sizes`는 array spec 첫 차원이 `*`인 필드만 세계별로 둘 수 있다. `body_mass`, `body_inertia`, `geom_size`, `geom_aabb`, `qpos0`, `stat.meaninertia`가 이에 해당한다. [고정 io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L287), [고정 types.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/types.py). 기본 off `per_world_model_references_v1`는 각 세계의 exact-XML C312 자산을 복원한 뒤, 변하는 변환 모델 배열이 모두 `*` 필드인지 검사해 world 순서대로 합친다. 배치 불가능 필드·옵션·토폴로지 차이는 계속 거부하며, 미사용 화물의 질량도 버리지 않는다. 설치본 `forward.py:354–387`의 overflow는 OR로 누적되고 일반 step에서 zero하지 않아 10Hz 동기화 때도 중간 스텝의 overflow를 볼 수 있음을 코드로 확인했다.

Native 초기 상태 복사는 [MuJoCo 변경 기록의 mj_copyData/copy.copy 설명](https://mujoco.readthedocs.io/en/3.3.6/changelog.html)을 참고했다. 설치본에서 native state의 값/버퍼 독립을 직접 검사하고 source의 오래된 contact-copy 버그 수정을 현재 검증으로 대신하지 않는다.

수치 성능 후보: [공식 Options 설명](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html#options)과 설치된 고정 io.py433–437은 float64용 tolerance를 GPU float32에서 최소1e-6으로 올려 불필요한 solver 반복을 막는다고 설명한다. 이전 strict-C 호환 경로는 이를1e-8로 되돌렸다. 기본 off `float32_solver_default_v1`는 변환기가 실제 정한 값을 보존하며, 새 task 성공 허용값을 넣지 않는다. A/B·solver_niter를 따로 기록하고 이 후보를1e-8 결과와 합산하지 않는다.

기본 off native sleeping/compact 후보는 [공식 compact solver](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html#compact-solver)의 Newton+sleep+nvmax 경로를 사용한다. 모델 전체246 DoF를 줄이거나 다른 로봇의 형상/질량을 제거하지 않는다. 실제 command를 받는 r1은 never sleep, 나머지 free body는 native allowed이며 충돌로 정상 wake한다. nvmax는 실제 C import active DOF 수와 정적 r1+target DOF 수의 최댓값을 다음2거듭제곱으로 올려 정하고, 예기치 않은 wake로 용량을 넘으면 실패 처리한다. sleep tolerance는 native 기본값을 그대로 두며, 원래 scene.setup과 같은0.4SIM초의 quiet setup을 추가해 sleep 상태를 측정한다. 이 물리 실행 프로필은 기존 off·C 결과와 합산하지 않는다. task Score를 바꾸지 않는다.


실행 결과로 범위를 정정한다. `sleep-prefix-n1`(`49b436ce`)은 pinned types.py320–332가 명시적 `NEVER/ALLOWED/INIT`를 미지원하므로 `put_model`에서 HOST_ERROR였다. 최신 문서의 sleep 지원만으로 명시 정책 지원을 가정한 후보는 채택하지 않았고 최종 CLI에서 제거했다. 다른 자동 sleep 정책의 지원까지 부정하는 결과는 아니다. 고정 환경을 갈아끼우거나 정책 enum을 근사하지 않았다. 서로 다른 실제 source seed의 모델 결합도 `dof_length`가 world-batch 필드가 아니어서 거부했다. 질량·기하·파생 모델 필드를 임의 공유해 통과시키지 않는다.


추가 조사로 별도 후보 `native_sleep_policy_compat_v1`를 만든다. [MuJoCo3.16 engine_sleep.c125–126](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_sleep.c#L125)은 NEVER와 AUTO_NEVER를 같은 sleep 금지 predicate로 검사하고, ALLOWED/AUTO_ALLOWED는 같은 나머지 경로다. [pinned MJWarp sleep.py290–292](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/sleep.py#L290)은 AUTO_NEVER만 검사한다. 따라서 컴파일 이후 NEVER→AUTO_NEVER, ALLOWED→AUTO_ALLOWED를 정확히 옮기는 별도 호환 adapter를 시험한다. INIT는 초기화 의미가 따로 있어 계속 거부한다. 설치된 pinned package 전체에서 tree_sleep_policy의 실행 읽기는 이 predicate뿐임을 grep으로 확인했다(io의 admission/types/test 제외). package 자체나 버전은 바꾸지 않는다. [공식 body sleep](https://mujoco.readthedocs.io/en/latest/XMLreference.html#body-sleep)의 자동/명시 override 설명을 함께 읽었다. 이 근거는 작은 후보의 검증 시작점이며 실제 성공/속도/초기 sleep 상태는 새 실행에서 따로 확인한다.
