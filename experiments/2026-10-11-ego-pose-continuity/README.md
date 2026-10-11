# 자기 위치 점프 DEV

- 기본 OFF: REP-105 제어 odom/지도 offset, AMCL 최소 운동·클러스터, 혁신/운동공분산 게이트.
- egomap70 본 실행 11기록 18,790프레임 고정 posterior 재생(smoke 1개 별도); 공통 checkpoint prefix 중복 포함, 독립 코호트 아님.
- 20cm 점프: off557, cluster7, innovation1; RMSE .6634/.6496/.6389m, 실행별 악화0/11.
- REP-105: `local_pose`는 map, `pose_continuity.control_pose`는 연속 command odom이다. shared heading은 후자를 쓰며, map 오차·목표 오인·odom drift를 제거했다는 뜻은 아니다.
- B/귀환은 과거 선언 시각의 거리만 재평가; 새로운 선언·물리 성공은 Azure에서 별도 측정.
- Azure: fresh63001–63006 × off/cluster/innovation, 18조건 등록; 진행·실패는 summary.json.
- [표준 방법·차이](references/methods.md), [원인](diagnosis.md), 원본 경로·해시는 summary.json.
