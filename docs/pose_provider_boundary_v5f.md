# 표식 무관 생성 경계 v5f

기준 HEAD: `8b0ddd27a931bfcecee1e3725ad4a6ed739c5c37`, 미커밋 후속 변경.
전수 감사 `codex-tag-audit.md`의 활성 진입점을 수정했다. 주입 제공자가 있으면
기본 태그 PF/detector/태그 사전·ID·크기 접근 없이 최종 제공자를 사용한다.
카메라 기하 계산 함수의 재사용과 태그 측정 API는 구분한다.

| 감사 항목 | 활성 경로와 처리 |
|---|---|
| 배송 adapter 부모 생성자 | `_DeliverController → SharedPoseDelivery`; `pose_source`를 초기 생성 시 전달 |
| Study/Own host 선행 기본 제공자 3개 | `pose_factory(robot_id, own_static, params, seed)`를 executor 생성 전에 호출. 초기 명령도 최종 제공자에 1회 전달 |
| M1/memory 공유 leg | `SharedLegDriver`, `SharedMemoryLeg`, `LegDriverMemV3`가 `SharedPoseDriver` 상태 초기화 사용 |
| 원본 M2 지연 PF 교체 | `ProviderM2DoorStudent`가 `begin_relocalization` 사용. `RoutedM2`는 이 adapter와 기존 `PairGraspRelook`을 상속 |
| memory controller/detector 프레임 참조 | `owncam_memory_delivery.M1OwnCamDeliveryMem`에 pose/landmark provider를 각각 주입. 기본 태그 관측만 `owncam_memory_inputs`에 격리 |
| v3 기본 provider 중복 생성 | 최종 v3 제공자와 memory를 각 1회 생성. 주입 시 `GuardedPoseProviderV3`가 중립 evidence만 수신 |
| 고정 VIS3 PF의 M1 태그 사전 | `vision_motion_init.motion_module`의 사설 클래스가 공통 운동/분포 상태만 초기화. frozen module/global을 패치하지 않음 |
| study map/Scene/public map | `vision_zero_tag_v2`와 `zone_wide_door_geometry_v2`를 새로 등록. `GeometryCargoZoneScene`은 표준 cargo/zone XML transform 사용, 태그 transform 미호출. scenario의 명시적 `landmark_detail=none`으로 projection/도식/검증 연결 |
| 상속된 dormant observe | 공유 leg/goto는 직접 observe를 거부하고 소유 제공자로 프레임을 1회 전달. pair는 이미 처리된 추정만 읽음 |

동결 `m1_owncam_delivery.py`, memory-v2 controller/정책/실험 원본,
`owncam_drive.py`, `owncam_drive_v2.py`, `pair_owncam_approach.py`, `run_m2_pair.py`,
VIS3/markerless 원본은 수정하지 않는다. 이 원본의 태그 경로는 과거 재현 전용이다.
활성 M1은 `SharedPoseDelivery`, 활성 memory는 `owncam_memory_delivery`를 사용한다.
현재 memory-v3 runner의 `m1_provider`, `memory_provider` 선택자가 활성 adapter를
명시하며 `off_legacy`, `memory_v2`는 기존 재현용 선택자로 남는다. 주입 API는
활성 controller의 `pose_source`와 `landmark_provider`다.

`VisionPoseSourceV2`는 태그 호환용 빈 `landmarks` 필드도 없는 새 지도를 엄격히
검증한다. 원래 VIS3 지도/모델/보정은 그대로 보존한다. 새 지도의 차이는 ID·버전과
빈 표식 메타데이터 제거이며 벽·카메라·화물 형상은 바꾸지 않았다.
제공자 identity는 초기화 adapter와 지도 해시를 포함한다. v1 호환 진입점도
동일한 중립 초기화를 사용하며 바뀐 identity로 과거 점수와 구분한다.
worker의 영상 프로토콜/모델은 v1을 재사용하며 v2 제공자의 위치 추정 성능을
새로 검증한 것은 아니다.

memory의 landmark provider 기본값은 주입 pose가 있을 때 관측 없는 geometry
provider다. 실제 memory landmark 관측은 별도 provider를 주입해야 한다.
v3는 `observation_quality.consistency`의 `nis`, `log_likelihood`, `settled`와
accepted receipt를 검사한다. 이 증거가 없는 vision 제공자는 기존 v3 guard의
불확실성 하한을 그대로 적용한다. 낮은 PF 분산만으로 검증을 통과시키지 않는다.

회귀 표는 `tests/test_zone_pair_tag_boundary_matrix.py`에 있다. `landmarks` 없음,
`id` 없음, `size_m` 없음, detector 차단을 pair/goto(비적재·적재)/deliver/M1/
memory(v2 활성·v3 ON·OFF)/각 leg/M2 adapter/두 host에 각각 적용한다.
모든 행에서 추가로 frozen 생성자, PF, detector, 태그 사전 함수를 차단하고
제공자 identity·최초 제어 결정·지연 leg/reset·초기 명령을 확인한다.
고정 PF와의 상태 및 명령 후 RNG 일치, default v3 생성 횟수, 중립 evidence,
map/Scene/XML/projection도 별도로 검사한다.

수치 임계값, GT/eval_only 제어 유입 금지, weld OFF, cargo_noslip_v1은 유지한다.
이 검사는 물리 step·실제 모델 호출 없이 수행한다. 연구 성공이나 실물 안전 승인,
학습·실험 결과가 아니므로 TensorBoard 실험 snapshot을 만들지 않는다.
