# warp3 참고·설계 경계

- [공식 MJWarp 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html), 2026-10-16 열람: GPU world 배치, `put_data`, CUDA graph, workspace overflow 확인. 최신 설명을 설치본의 지원 보증으로 쓰지 않는다.
- 설치본은 warp1에서 확인한 MuJoCo/MJWarp3.16.0, Warp1.15.0, 공식 source `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`이다. 이번에도 실제 함수/필드/파일 SHA를 확인한 뒤 이식한다.
- 설치본 `ray.py:1226 rays`는 `(nworld,nray)` ray 묶음과 render BVH를 지원한다. frozen teacher의 surface seven probes·one-third 가시성 기준을 옮기되 새 인식 상수는 만들지 않는다.
- 설치본 `render_util.py:53–69 create_warp_texture`는 `wp.Texture2D(..., filter_mode=LINEAR)`를 사용한다. OpenGL mipmap 설정을 GPU ray renderer에 억지로 적용하지 않는다. 요청한 no_mip_v1의 native resolution/linear filtering에 해당하는 실제 구현을 기록한다.
- 장면은 PR527 a68106fd의 indigo110_s80 + 원본 v1 바닥이다. frozen ACT11의 옛 벽 half-length1.475는 release 관문에서 먼저 만든 `release_geometry_v1` 확장(7c752fcdef2627a6aedd3766346a1241a1788d7b)을 재사용한다. 질감만 추가하며 벽 형상·마찰·카메라를 바꾸지 않는다.
- `floor_light_nearclip_v1`의 실제 XML nearclip 변환을 그대로 연결한다. 과거 wrapper의 floor_light_v1 이름 검사를 새 장면에 우회 적용하거나 조명을 두 번 변환하지 않는다.

초기16은 한 물리 모델에서 서로 다른 시작을 검사하는 진단이다. 40개 독립 교사 시드의 관문·성공률로 해석하지 않는다. 교사 행동에는 현재 보이는 대상의 상대 위치만, held 구간에는 화물 세계 좌표 없이 자기 RGB와 발행 명령만 사용한다. weld OFF, 판정/정답은 evaluator lane에 둔다.

## 실행 스케줄 진단 (관문 중, 정식 warm 처리량 아님)

[공식 NVIDIA MPS 문서](https://docs.nvidia.com/deploy/mps/latest/index.html), 2026-10-16 열람: MPS는 여러 CUDA 프로세스의 GPU 사용과 context switching 비용을 개선하는 런타임이다. 실제 L4에서 MPS server 프로세스는 없었다. 7개 프로세스 동시 구간과 한 그룹만 실행한 짧은 구간을 관측했지만, 접촉/동작 단계와 queued work가 달라 원인을 확정하거나 효율 수치로 쓰지 않는다. 현재는 큰3그룹(29world)을 유지하고 작은4그룹(11world)은 task-owned SIGSTOP/SIGCONT로 이어간다. 제어/물리/SIM 시계는 그대로이며 pause 시간은 측정 wall time에 포함되므로 이 관문 타이밍을 intrinsic 처리량으로 사용하지 않는다. 실제 정식 warm N64/256·C16 측정은 4단계에만 한다.

설치본 solver.py4357은 compact solver에서 `m.opt.tolerance`를 data의 `ctol`/`cls_tol`로 치환한다. 따라서 nominal float32 tolerance flag만 바꾸면 현재 compact 물리 비용이 해결된다고 주장하지 않는다. 기존 warp1의 float32 probe는 no-sleep의 짧은 prefix였고 compact 관문과 분리한다. 이번 관문 profile은 변경하지 않았다.

비용 집계 주의: 여러 topology group이 동일 L4의 겹친 벽시계 시간을 갖고 일부 SIGSTOP 되었으므로 group별 `vm_cost_estimate_usd`를 더하지 않는다. warm 측정은 외부 임대/실행이 없는 별도 구간에서 한 VM의 실제 측정 시간으로 계산하고, 상속 hourly estimate와 실제 결제액을 구분한다. R1 관문에는 beamact2 GPU 공유 부하가 확인되어 자체 성능 근거로 쓰지 않는다.

렌더 설치본 정적 확인: `render_util.py:69`는 TextureFilterMode.LINEAR, Warp1.15의 Texture2D 기본 `num_mip_levels=1`을 사용한다. 따라서 선택 no_mip 조건은 GPU 경로에서 선형/1단계로 적용되어 있으며 OpenGL wrapper를 GPU renderer에 덧붙이지 않는다. 원본 파일 SHA와 반투명 구역 제한은 [render-quality-source-audit.json](render-quality-source-audit.json)에 기록했다. 이는 C RGB 동등성 승인이나 교사 성공 판정이 아니다.
