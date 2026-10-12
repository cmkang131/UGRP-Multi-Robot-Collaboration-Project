# E2E VO 바닥 마스크 — 기본 off, DRAFT / not-ready
- 조사: [references.json](references.json) — 벽도 호모그래피 평면이다. 왜곡 제거→정적 벽 가림→RANSAC 내점→기존 지면 SE(2)가 필요하다.
- `vo_floor_mask=geom_v1`: 고정 카메라 광선·정적 지도 벽·같은 지도 좌표계의 추정 자세; 기본 `off`, 비교 `homography_v1`. `install(..., static_map=..., map_pose_provider=...)`는 자기 RGB 정합 제공자가 필수다.
- 기존 E2E `local_pose`는 자기 출발점 좌표다. 제공자 없으면 live 설치 거부, 재생은 `unknown_map_registration`→기존 대체 경로; GT·spawn·단위변환으로 대체하지 않았다.
- [summary.json](summary.json): 124/124프레임·120쌍, 기존 VO 재현 오차0; geom 정합0/124로 혼입 개선 미검증. 마지막 벽 ROI4/4: off20,204/20,400px(99.04%), 전체 마스크의 최소10.43–10.98%; RANSAC 화소 마스크 동일.
- RANSAC 단독: 이동64/120 위치오차합103.006→86.380mm·방향7.069→6.482°; 회전42/120 위치113.607→119.915mm·방향6.530→6.050°; 부분미끄러짐14/120, 정지0/120. 위치 개선2/4창·악화1/4창(1mm 기준).
- 관련 시험52/52. 소스 `1c8fdcdd`, [재생 상세](replay/replay.json), [입력 해시](replay/input-hashes.json); 원본 summary.raw 경로를 읽었고 새 이미지/원격 회수0, 시뮬·모델0. 정답은 예측 파일 저장 후 별도 평가에만 읽었다.
- 재현: `PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_e2e_vomask --raw-root /Users/changmin/projects/ugrp-wt/e2e14-combo/outputs/e2e14-combo/r2/fetch-lite --image-root /Users/changmin/projects/ugrp-wt/e2e-usstall/outputs/e2e-usstall-audit --output <새-로컬-기록-경로>`
- 새 번들·Azure 명령 미등록: 완전 geom 개선 미확인·RANSAC 회전 위치 악화. 정합·개선 확인 후 v206 대비 seeds61001–61003×2·6동시·7시간·별도 릴레이를 등록한다. 이번 작업 실행0.
- 다음: 자기 RGB 지도 정합 제공자·정지 표본 확보. 이미 본 DEV 자료이며 전체 E2E/초음파 성능 검증이 아니다. Refs #446 #450.
