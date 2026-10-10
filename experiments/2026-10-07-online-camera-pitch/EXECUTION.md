# 실행 기록

- 사전 등록 `e240df27`, 구현 `7428987b`; 관련14시험 통과 후 구현 커밋.
- 조건 감사: s1045/46/47/50 모든30,512프레임 join. 조건별 표는 `results/conditions.csv/json`.
- 첫 개발 영상 계산은 예측 봉인/오차 채점 이전 `IndexError`로 중단했다.
  OpenCV5 `LSD.detect()[0]`는 N×4, 원문은 OpenCV4 N×1×4를 가정한다.
  원문 `__detect_lines`의 `lines[:,0]`도 같은 가정이다.
  어댑터에서 양쪽을 N×4로 normalize한 뒤 원문과 동일한 LSD0/30px 결과를
  subclass의 선분 입력에 전달한다. 원문 파일·가설·점수·seed·관문은 변경하지 않는다.
  이 호환 변경은 prereg 후 데이터 품질 결과를 보기 전에 수행한 실행 오류 수정이다.
  빈 실패 디렉터리 `outputs/online-camera-pitch-v1/online_vp_v1/s1042` 보존,
  재시도는 새 `outputs/online-camera-pitch-v1-complete/`에 저장한다.
  같은 원인으로 다시 실행이 막히면 반복 수정 없이 중단한다.

- 호환 수정 `c9c4aba0` 전 관련15시험 통과(실제 LSD→원문 전체 가설/투표 synthetic wireframe 포함).
  개발2 예측 후 `10eb7add`에서 소스/설정 동결, 확인4 각1회. 모두 FAIL, 추가 재튜닝0.
- 마지막 검증: `test_online_camera_pitch.py`, `test_servo_camera_fk.py`,
  `test_wall_floor_boundary.py` **20 passed**, off geometry/투영 및 비어 있지 않은 검출 scan/segment/adapter bytes 동일.
  새7시험을 기존 CI 목록에 등록했다. 앞선 audit/S2 비교까지 포함한15시험도 통과했다(합산해 독립 표본으로 세지 않음).
- [RESULTS.md](RESULTS.md), 조건 CSV/JSON, 그림2장, raw43파일26,966,754bytes 해시 확인.
  개발 판단 실패와 라이브러리 호환 수정은 구분한다. 이 결과로 자기 지도 트랙 중단,
  RBPF/graph/누적지도 재생0. 실물 측정 전 재튜닝 없음.

재현(기존 raw 경로는 덮어쓰지 않고 새 `--output`을 지정):

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-online-camera-pitch/code/conditions.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-online-camera-pitch/code/evaluate_pitch.py --split development --camera-pitch online_vp_v1 --output /Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1-complete
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-online-camera-pitch/code/evaluate_pitch.py --split confirmation --camera-pitch online_vp_v1 --freeze experiments/2026-10-07-online-camera-pitch/freeze.json --output /Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1-complete
PYTHONPATH=outputs/self-map-plot-deps /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-online-camera-pitch/code/report.py
```

위 명령은 실제 사용 기록이다. conditions는 새 run 경로로 `OUT`을 명시해야 하며 기존 폴더가 있으면 거부한다.
report는 봉인된 결과만 읽으며 예측 재실행이 아니다. `--camera-pitch off`가 평가 CLI 기본값이다.
