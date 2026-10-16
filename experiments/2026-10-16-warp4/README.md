# warp4 — 빔 짝 / release MJWarp 배치

사용자 2026-10-16 "MJWarp에서 하도록 바꿔줘". PR534 최신 e97464a3 위에 쌓는다. 새 실행기의 기본 백엔드는 MJWarp이며 LLM E2E는 CPU에 둔다. **이식 개발 중, 자체 관문 미완료**. CPU 성공을 승계하거나 합산하지 않는다.

단일 모델은 free-root의 초기 위치·방향만 고정 XML로 옮기며 장면 setup/qpos로 세계별 시작을 둔다. 나머지 XML 및 post-setup 모델 배열(특히 dof_length)은 exact 검사한다. SLEEP 비트 off 예외를 쓰지 않는다. 차이는 누락 없이 거부표에 기록한다. 질량·크기·마찰·장면·FOV·성공식은 변경하지 않는다.

빔 짝은 adapter835ccef2 + teacher26f84d0f, peer_yield ON이다. release는8e81b7d9의 A/B 설정을 각각 보존한다. AST 변경은 advance의 yield 경계와 v7의 mj_step을 명령 tape 저장으로 치환하는 것뿐이다. release의 quantized wheel/명령 odometry를 물리 substep마다 그대로 실행한다. 물리는 PR534 WarpTransport 하나가 CUDA graph로 실행하며 GPU 접촉만 평가에 쓴다. 행동 측정은 원래 가시성 게이트/held suppression을 유지한다. C mirror의 ray/IK는 이 첫 이식에서 scalar이며 전체 교사 벡터화로 보고하지 않는다.

release25의 grasp prefix는 기존 observable_v2 준비 구간이며 접촉·높이로 시작을 고른다. 본 release와 별도로 표기하고 학습/관문 입력으로 인정하지 않는다. 준비 이후 release 입력 감사와 성공을 별도 검증한다. prefix를 visible-only 교사 성공으로 보고하지 않는다.

기록 전용 옵션: 전체 자기 RGB2Hz, 마지막10SIM초10Hz JPEG ring, 세계별 qpos/qvel, raw/source/hash/funnel. 학습 RGB·LLM 호출·Mac 물리·렌더·GUI0. gcp2 L4의 warp3/beamact3를 유지하고 shared-load로 기록한다.

검증: 비물리 시험21개 통과. 단일모델 runtime/run-first·40/A40/B40·N16/64/256 정상상태 처리량은 아직 미측정.

참고: [MJWarp 공식 배치·CUDA graph·workspace 문서](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html), [MuJoCo freejoint XML](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-freejoint), 2026-10-16 열람. 설치본 버전/파일은 실행 시 따로 기록하며 최신 문서가 설치본 지원을 보증하지 않는다.
