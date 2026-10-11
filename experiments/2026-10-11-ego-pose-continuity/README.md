# 자기 위치 점프 DEV

- 기본 OFF: REP-105 제어 odom/지도 offset, AMCL 최소 운동·클러스터, 혁신/운동공분산 게이트.
- egomap70 8기록 11,126프레임 고정 posterior 재생; 공통 checkpoint prefix 중복 포함, 독립 코호트 아님.
- 20cm 점프: off403, cluster6, innovation1; RMSE .7770/.7645/.7568m, 실행별 악화0/8.
- REP-105는 지도 보정을 별도 TF에 두고 shared heading 제어를 연속 command odom에서 수행한다. odom drift가 사라진다는 뜻은 아니다.
- B/귀환은 과거 선언 시각의 거리만 재평가; 새로운 선언·물리 성공은 Azure에서 별도 측정.
- Azure: fresh63001–63006 × off/cluster/innovation, 18조건 등록; 진행·실패는 summary.json.
- [표준 방법·차이](references/methods.md), [원인](diagnosis.md), 원본 경로·해시는 summary.json.
