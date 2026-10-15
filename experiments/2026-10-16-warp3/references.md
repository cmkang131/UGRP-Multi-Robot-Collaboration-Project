# warp3 참고·설계 경계

- [공식 MJWarp 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html), 2026-10-16 열람: GPU world 배치, `put_data`, CUDA graph, workspace overflow 확인. 최신 설명을 설치본의 지원 보증으로 쓰지 않는다.
- 설치본은 warp1에서 확인한 MuJoCo/MJWarp3.16.0, Warp1.15.0, 공식 source `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`이다. 이번에도 실제 함수/필드/파일 SHA를 확인한 뒤 이식한다.
- 설치본 `ray.py:1226 rays`는 `(nworld,nray)` ray 묶음과 render BVH를 지원한다. frozen teacher의 surface seven probes·one-third 가시성 기준을 옮기되 새 인식 상수는 만들지 않는다.
- 설치본 `render_util.py:53–69 create_warp_texture`는 `wp.Texture2D(..., filter_mode=LINEAR)`를 사용한다. OpenGL mipmap 설정을 GPU ray renderer에 억지로 적용하지 않는다. 요청한 no_mip_v1의 native resolution/linear filtering에 해당하는 실제 구현을 기록한다.
- 장면은 PR527 a68106fd의 indigo110_s80 + 원본 v1 바닥이다. frozen ACT11의 옛 벽 half-length1.475는 release 관문에서 먼저 만든 `release_geometry_v1` 확장(7c752fcdef2627a6aedd3766346a1241a1788d7b)을 재사용한다. 질감만 추가하며 벽 형상·마찰·카메라를 바꾸지 않는다.
- `floor_light_nearclip_v1`의 실제 XML nearclip 변환을 그대로 연결한다. 과거 wrapper의 floor_light_v1 이름 검사를 새 장면에 우회 적용하거나 조명을 두 번 변환하지 않는다.

초기16은 한 물리 모델에서 서로 다른 시작을 검사하는 진단이다. 40개 독립 교사 시드의 관문·성공률로 해석하지 않는다. 교사 행동에는 현재 보이는 대상의 상대 위치만, held 구간에는 화물 세계 좌표 없이 자기 RGB와 발행 명령만 사용한다. weld OFF, 판정/정답은 evaluator lane에 둔다.
