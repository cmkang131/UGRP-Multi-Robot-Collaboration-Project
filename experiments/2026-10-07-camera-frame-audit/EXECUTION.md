# 실행 기록

- 사전 등록 `f2c498df`, static audit 소스 `67134e4b`, 관련16시험 통과 뒤 push.
- 첫 model load는 sparse checkout의 기존 PNG24개 부재로 HOST_ERROR, 결과 생성 전 중단.
  Git HEAD의 원본 PNG24개만 같은 worktree에 복원하고 bytes를 대조했다. 무늬 수정0.
  원 실패 폴더 `outputs/camera-frame-audit-v1/HOST_ERROR.json` 보존.
- `retry-assets-restored/same-qpos.json`은945조건 링크별 대조 완료.
  후속 intrinsic 검사에서 MuJoCo3.12 named camera view에 `intrinsic` 필드가 없어 HOST_ERROR.
  공식 model의 `cam_intrinsic/cam_sensorsize/cam_resolution` 배열 접근으로 어댑터만 고치고
  작은 실제 MuJoCo XML API 시험을 추가한다. 정기구학 결과·model·카메라·DR 수정0.
  같은 원인 재발은 없으며 완료된945조건을 다시 돌리지 않고 남은 검사만 이어간다.
