# 자기 위치 점프 DEV

- `poses[best]` 입자 전환으로 .693/.767m 점프; 원인은 [diagnosis.md](diagnosis.md).
- 기본 OFF: REP-105 연속 command odom, AMCL 최소 운동·클러스터, 혁신/운동공분산 게이트.
- 오프라인 본 실행 11/24개(18,790프레임)+smoke 별도; >20cm557→7/1, 전체 RMSE .663→.650/.639m(클러스터/혁신).
- Azure18/18: OFF/클러스터/혁신 B3/3/4, 귀환0/4/4, 둘 다0/2/2(각 N=6); 공통 RMSE .304/.244/.229m, >20cm210/0/0.
- 후보의 연속 제어 pose >5cm 점프0; map 보정·odom drift·일부 seed RMSE 악화·도착 오인은 남아 기본 OFF 유지.
- ARM 원본 전체 검증, Mac 텍스트180개20.3MB와 대표 영상1개; 자체 lease/실행기0, VM 시작/정지0.
- [summary.json](summary.json), [표준·차이](references/methods.md), [시험](local-validation.json), [S3 별도 경로](s3-scope.json).
