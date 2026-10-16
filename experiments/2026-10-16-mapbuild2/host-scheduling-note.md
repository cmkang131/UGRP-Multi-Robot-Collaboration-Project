# 사용자 실행상한 없음 결정과 호스트 설정 차이

L4 `ugrp-act-l4-gcp2`의 읽기 전용 describe에서 기존 `maxRunDuration.seconds=28800`(8시간)이 남아 있다. 이번 작업은 이를 추가·복원하지 않았다. 시작 시각은 2026-10-16T06:01:09Z이고 기존 자동 정지 예상은 14:01:09Z다.

[공식 set-scheduling 문서](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/set-scheduling)와 설치된 gcloud help는 TERMINATED 상태에서만 변경할 수 있다고 명시한다. 해제 명령은 `gcloud compute instances set-scheduling ugrp-act-l4-gcp2 --clear-max-run-duration --zone asia-northeast3-a --account changmin5781@gmail.com --project ugrp-sim-b-1014`이다.

act16w·beamact3·warp3와 공유 중이므로 이 작업이 VM을 정지하지 않는다. 다음 자연 정지 후, 다시 시작하기 전에 기존 상한을 해제해야 한다. 실행기에는 wall 상한이 없으며 4 SIM초는 기록 자극 범위다. idle20과 budget-stop은 보존한다. 관찰 원본은 host-scheduling-observed.json.
