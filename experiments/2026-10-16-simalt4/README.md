# simalt4 — MJWarp 파지 동등성 진단

진행 중. simalt3 완료 신호를 2026-10-15 15:38:49 UTC, 5분 간격 다섯 번째 확인에서 읽었다(25분 대기). 기존 물리값과 운영 backend는 유지한다. 이번의 원격 호스트는 gcp2 프로젝트 `ugrp-sim-b-1014`의 기존 `ugrp-act-l4-gcp2`뿐이다. L4 사용 상한 3시간, 자원 상한 종료는 `cap_end`, 비용 정지 발동이면 즉시 중단한다.

## 고치기 전 근거

simalt3 README/summary/rejection_table, 명령 trace 명세, C3.16 대조, contact-distribution, playback-review를 읽었다. C3.12의 파지 유지 30/30은 독립 30회가 아닌 10Hz 평가 표본이다. 같은 tape를 C3.16도 실패했으므로 GPU 단정은 금지한다. 실패 Warp grip/turn과 양성 C3.12 grip의 기존 전체 2Hz 및 dense 10Hz 프레임 띠 총14장을 직접 다시 읽었다. grip 전체 0.5–43.0초, 실패 직전 15.2–25.1초, 성공 끝 33.5–43.4초, turn 전체 0.1–4.0초다. 20.5초 이후 Warp 상자가 화면 위로 커지며 올라오지만 C는 화면 아래 띠만 남는다. 듬성한 hold 위치 정지만으로 잡힘을 판단할 수 없다. 큰 왕복 진동은 turn 띠에서 보이지 않았다. 기존 MP4는 ffprobe 검증 기록과 SHA가 있으며 새로 GUI 재생하지 않았다. r2는 축소 장면에 없다.

## 사전 계획

1. 동결 scene.xml/fixture.npz(교사 `6f057f7e`) 재사용. C3.12·C3.16·MJWarp 개발 `57b4692f`를 같은 L4 CPU/GPU에서 실행한다.
2. 새 evaluator `scripts/simalt_step_probe.py`로 모든 physics step의 접촉 수/버퍼/overflow/최소 거리/법선·접선 힘/패드 관절/qpos·qvel을 저장한다. 제어 입력은 기존 tape뿐이다. C3.16 대 Warp를 먼저 비교하고 C3.12 대 C3.16을 분리한다. 원본은 VM에 두고 표·요약만 회수한다.
3. 수정 전에 분포/첫 분기 표를 생성한다. 마찰·solref/solimp·질량·dt·noslip_iterations·관절 이득은 바꾸지 않는다. 최대3라운드, 같은 원인이3회 남으면 종료한다. 변경은 기본off 실행 모드뿐이다.
4. 작은 장면의 주행4구간/close-hold-release, 3초 양쪽 접촉30/30·높이 차2mm·끝점5mm/2°(모두 사용자의 탐색 제안값)를 통과해야 두 로봇+빔3초로 확장한다. 이후 N16/64/256 재측정한다. 실패 시 확대/속도 측정은 미제출로 기록한다.

원본 예상 신규쓰기 ≤2GiB, Mac 요약/몽타주 ≤100MiB. 기존 L4 영속 디스크 여유 약76GiB, Mac41GiB(실행 직전 재확인). raw 외부 백업 및 실물 검증은 이번 범위가 아니다. 모델 호출/학습 없음.

## 참고 자료 (2026-10-16 KST 확인)

- [공식 MJWarp 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html): nconmax는 world당 기대값, naconmax는 전체 상한, njmax는 world당 제약 상한. XML size 값은 읽지 않는다. overflow는 undefined behavior이며 `Data.overflow`를 검사한다. 작은 N 지연과 큰 배치 처리량은 구분한다.
- [고정 개발 README](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/README.md#MuJoCo-API-Compatibility): IMPLICITFAST midpoint, PGS, plugin actuator/sensor 미지원; flex 실험적. noslip은 discrete integrator에서 미지원이며 현재 실행의 noslip10 지원 여부는 실제 모델·호출에서 검사한다. 오래된 정식 tag의 noslip 미지원과 혼동하지 않는다.
- [고정 io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L433): float32를 위해 tolerance를 최소1e-6으로 바꾼다. simalt3처럼 C의1e-8을 복원한다. cone/solver/integrator는 put_model이 C opt에서 복사하며 임의 기본값을 추가하지 않는다. condim·margin·gap도 그대로 복사/접촉 생성한다. 이 고정판에 전체 float64 실행 토글이 있는지는 미확인이다.
- [고정 충돌 분기](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/collision_driver.py#L47): plane/mesh는 primitive plane-convex, box/box·mesh/mesh·box/mesh는 convex CCD. primitive box/box SAT 대안 코드도 존재한다. 형상과 contact parameter를 바꾸지 않는 파이프라인 후보이며 효과는 미측정이다.
- [MuJoCo3.13 변경 기록](https://mujoco.readthedocs.io/en/stable/changelog.html#version-3-13-0-september-8-2026), [Plane-Mesh rewrite 67562d95f](https://github.com/google-deepmind/mujoco/commit/67562d95f), [C3.12 원본](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/engine/engine_collision_convex.c#L1001), [C3.16 원본](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_collision_convex.c#L1091): C3.12는 support vertex와 graph 이웃, C3.16은 support face polygon의 최대4점. 실제 실패 원인인지는 첫 분기와 대조로 확인해야 한다.
- [이슈1546](https://github.com/google-deepmind/mujoco_warp/issues/1546): world 좌표 float32 GJK/EPA에서 접촉 제약이 사라지는 재현, pair-local 좌표 수정 PR1613으로 해결됐다는 maintainer 답변. 현재 고정 소스 포함 여부·이번 재현 관련성은 별도 확인한다. margin/gap을 바꾸는 해결은 이번에 금지다.
- [이슈1635](https://github.com/google-deepmind/mujoco_warp/issues/1635): Warp 자체 deterministic 모드의 convex 접촉 누락 사례. overflow가0이어도 접촉이 빠질 수 있었다. maintainer는 해당 Warp deterministic 기능을 지원하지 않는다고 답했다. 현재 설정을 기록한다.
- [이슈87 noslip](https://github.com/google-deepmind/mujoco_warp/issues/87), [이슈1517 작은 마찰 NaN](https://github.com/google-deepmind/mujoco_warp/issues/1517), [이슈926 버퍼 메모리](https://github.com/google-deepmind/mujoco_warp/issues/926): 각각 noslip 후처리, 저마찰 퇴화, 할당/메모리 사례다. nconmax/njmax 넘침이 이번 파지 미끄러짐을 직접 설명한다는 사례는 검색에서 확인하지 못했다.
- [공식 Discussions](https://github.com/google-deepmind/mujoco_warp/discussions) 및 grasp/friction/contact 검색: 이번 장면과 같은 파지 해결법을 확인하지 못했다. 일반 MuJoCo의 마찰/condim 변경 조언은 이번 허용 수정 범위 밖이다.

참고 소스의 다운로드 URL·SHA는 `references/sources.json`에 보존한다. upstream 전체 소스 복제본은 결과 코드가 아니며 로컬 outputs와 VM 증거 경로에 둔다.
