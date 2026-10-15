# reloc12 원본 관문표 (reloc13 수정 전)

단위: 동일 프레임 순서 누적. 신선한 정적 보정 프레임 수는 별도이며 명령 전파도 실행 자세 전달로 센다.

|run|프레임|등록|실행 자세 전달|지도 삽입|주행 사용|제어 오류|
|---|---:|---:|---:|---:|---:|---:|
|reloc12-r2-ransac-texture-93571-ff1ccf27|220|82|82|0|0|23|
|reloc12-r2-ransac-texture-93583-ff1ccf27|218|133|133|0|0|72|
|reloc12-r2-ransac-texture-93584-ff1ccf27|234|147|147|0|0|36|
|reloc12-r2-ransac-texture-93585-ff1ccf27|220|84|84|0|0|16|

등록후 삽입거부446건 전부 pose_uncertain. 물체=`static_registration_or_map_evidence`, 최소틈=null(위치 관문 해당 없음).

R7: {'ambiguity_evaluated': 154, 'unique': 121, 'pf_agreement_reliable': 75, 'three_confirmations': 220, 'reject:no_sensor_update': 653, 'reject:pf_unresolved': 286, 'reject:xy_covariance': 116, 'reject:yaw_covariance': 126, 'reject:geometry': 308, 'reject:ambiguity_pending_upstream': 738, 'reject:geometric_ambiguity': 33, 'reject:cluster_mass': 13}

오류 범주(소스별 증상, 독립 원인 확정과 구분): {'yaw_only:visual_relocalized:visual_relocalized': 2, 'yaw_only:visual_update:visual_update': 40, 'yaw_only:command_only:insufficient_matches': 34, 'yaw_only:command_only:no_rigid_consensus': 4, 'xy_only:visual_update:visual_update': 20, 'xy_only:command_only:insufficient_matches': 11, 'xy_and_yaw:visual_update:visual_update': 14, 'yaw_only:visual_relocalized:selfmap4_static_lines': 6, 'xy_and_yaw:command_only:insufficient_matches': 10, 'xy_only:visual_relocalized:selfmap4_static_lines': 6}

57° yaw 오류는 두 실행에서 ORB 전역 재등록 후 지속됐다. 확대 불확실성이 innovation 관문을 느슨하게 하고 bootstrap 누적이 지도 삽입을 막는다. 10cm를 조금 넘는 위치 오차 및 정적 PF yaw 오차도 별도 존재한다. 실제 정확도는 covariance 축소로 보증되지 않는다.

HOST_ERROR4건 모두 마지막 프레임 executor_stop_reason=selfmap4_relocalization_exhausted. 코드 self_map_executor.py의 recovery SIM deadline/시도 횟수에서 stop하고 run_self_map_diagnostic.py가 HOST_ERROR로 기록한다. 원본 종료시점43.4–46.6초, 호스트장애 증거 없음.

재현: GCP ff1ccf27a43fe73d9b49dac82caf26a4584060d0 cwd, `PYTHONPATH=. .venv-sim/bin/python /tmp/analyze_reloc13.py /home/ugrp/ugrp-sim/runs/reloc12-r2-ransac-texture-*-ff1ccf27 --output /tmp/reloc13-baseline-funnel.json`. 스크립트는 scripts/analyze_reloc13.py. 전체 경로·해시·147개 오류 프레임과 백분위는 baseline-funnel.json.

수용 후보 검토: 감사의 geo_n/geo_eig1 AUC 최대.69는 단일 정확도 관문을 정당화하지 못한다. ORB 인라이어 수와 R7 모호성·세 확인·앵커는 분리 집계하며, 이번에는 새 수용 상수를 추가하지 않는다. 실제 물리의 오등록·오류 분포를 먼저 재측정한다.
