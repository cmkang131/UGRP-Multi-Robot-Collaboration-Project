# 제공자 motion params 조회 — PR #240 검토 8

`PoseProvider.get_motion_params()`는 공개된 제공자 상태의 운동 보정을 복사해서 반환한다.
정적 보정과 자기 발행 명령에 따른 load/profile만 사용한다. 조회는 시간·관측 갱신·명령 큐를
진행시키지 않으며 반환값을 수정해도 제공자 내부 보정은 바뀌지 않는다.

`OwnCamPoseSource`와 `VisionPoseSource`가 자기 구현 내부에서 보정을 선택하고,
`DelayedPoseSource`는 이미 지연이 해제된 제공자 상태를 조회한다. 아직 큐에 있는
profile 변경이나 영상은 앞당겨 반영하지 않는다. `GuardedPoseProviderV3`와 기본
`OwnCamPoseSourceV3`는 이 공개 메서드로 memory-v3 명령 이동량을 계산한다.
ON/OFF 컨트롤러 모두 같은 인터페이스와 기존 confidence 임계값을 쓴다.

`wall_tags.camera_in_base()`는 자기 발행 PWM으로 카메라 외부 보정만 계산하는 순수
기하 helper다. 태그 사전·ID·크기·detector를 읽지 않으며 동결 markerless/VIS3 원본이
참조하므로 이 작업에서 옮기지 않았다. 태그 측정 경로 금지는 계속 유지한다.

회귀는 초기 servo 명령, 명령 기반 이동량, 지연 profile 해제 전후 및 복사 독립성을
vision/tags·지연 ON/OFF·memory ON/OFF 조합에서 검사한다. 실제 이동이나 위치 추정
성능 검증은 아니다. [기존 생성 경계](pose_provider_boundary_v5f.md)는 별도로 유지한다.
