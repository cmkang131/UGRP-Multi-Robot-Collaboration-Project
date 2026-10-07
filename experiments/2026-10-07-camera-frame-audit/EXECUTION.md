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
- `08ebd776`: API 수정·기록 프레임 감사, 관련18시험 통과 후 push. 기존945조건은 보존하고
  남은 native camera/DLT 검사 및36,076개 저장 frame 비교를 완료했다. dynamics/렌더0.
- `efd1d5ce`: 중력 검산 사전 기록·소스, 관련20시험 통과 후 push. 북/남362frame의
  평가 역산 qpos를 정기구학에 넣고 CoM 중력 모멘트만 계산했다. fit/물리 적분0.
- 결과 그림 첫 import는 plot 전용 matplotlib 위치를 기본 checkout으로 잘못 지정해 실패했다.
  실제 기존 `ego-wall-map/outputs/self-map-plot-deps`로 경로만 고쳐 정상 생성·직접 검수했다.
  설치/venv 변경·추론/평가 재실행0. 모델 로드·API·그림 경로 오류는 서로 다른 원인이며 모두 기록했다.
- 새 운영 후보가 없으므로 조건부 바닥/시차 재생·탐색 녹화·지도 재생에 진입하지 않았다.
  이전 관문 실패와 texture/parallax 동결을 유지한다. 추가 yaw fit/부호 반전0.
