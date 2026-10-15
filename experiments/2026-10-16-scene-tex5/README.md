# scenetex5 — 장면과 경계 단계를 함께 변경

진행 중. PR #527, 기본 off. v1 바닥 자산과 no_mip_v1을 사용하고 보라 벽 3개(명목 HSV 143/210/150, 144/210/175, 145/210/195)를 비교한다. 무늬는 없음. 물리·마찰·카메라 위치/FOV/K/D 불변, 인공 마커 없음. 이 값은 디자인 후보이며 검출 임계가 아니다.

수정 전 [거부 원인](before-change.json)과 scenetex4 README/round2-final/round3/review-notes/boundary-review.jpg, scenetex3 README를 읽었다. 균일 무채색 벽 전용 경계를 보존하려던 관문을 새 장면에 적용하지 않는다. selfmap의 96컬럼·strip2, ColumnModel, PlaneFlow, 하류 scan/segment 인터페이스는 보존하고 새 색 분할과 아래→위 전이 단계만 선택적으로 사용한다. v1은 기존 검출기를 쓴다.

첫 라운드: 같은 네 지도 88자세, v1/native와 v1/no_mip_v1 및 보라 후보3/no_mip_v1. PNG/JPEG90/PIL82. 최대3라운드. 정적 SIM0 + atan(1/fx) yaw 영상 쌍이며 실제 주행·위치 추정·임무 성공을 검증하지 않는다. 동적 실패 영상/10Hz 고리 버퍼를 검증했다고 주장하지 않는다. 렌더/분석/이미지 생성은 gcp2, Mac 렌더·GUI0. 모델 호출0.

색 임계는 렌더된 원본 표면 픽셀 분포의 백분위에서만 산출한다. 평가 분할은 이 오프라인 보정과 채점에만 쓰고 검출 함수에는 RGB와 고정 보정 파일·자기 명령 기반 카메라만 전달한다. 같은88자세로 튜닝하므로 탐색 결과이며 독립 일반화 검증이 아니다.

관문: (1) 같은88자세·물리·카메라 (2) 기존 검출 종류/개수 PNG/JPEG/PIL 각88/88·새 오검출0 (3) 경계 컬럼 중앙/p10 ≥ v1/native, 오차 중앙/p95 ≤ v1/native, 인코딩별 (4) 바닥 ORB20/7·내부support·연속 매칭 중앙/p10 및 LK tracks/inliers 중앙/p10 ≥ v1/native (5) 색 IoU·모든 벽 색 범위 침범 기록. 자세별 회귀 수는 기록만 하며 분포 관문으로 판정한다. 가림으로 벽 미노출은 장면 한계로 기록한다.

운영 예산: gcp2 n4-highcpu-64, 5동시(호스트≤40), raw6GiB + 분석/임시2GiB, Mac fetch-lite32MiB. dev, PR527, 원본 영속 디스크·sha256 보존. 시작 시339GiB/메모리123GiB·Mac40GiB 확인. gcp2 유휴 종료1회를 규칙14로 재시작; gcp1 접근 없음. 임대 scenetex5.json을 만들고 실행 PID로 갱신한다. 종료 시 임대/타 작업 확인 뒤 자기 임대만 제거한다.

## 참고 자료 (2026-10-16 원문 확인)

- [OpenCV inRange/HSV](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html): 색 공간 변환과 범위 분할.
- [OpenCV cvtColor/Lab](https://docs.opencv.org/4.13.0/d8/d01/group__imgproc__color__conversions.html): Lab 변환; 조명에 대한 완전한 불변성을 보장하지 않는다.
- [OpenCV fitLine](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html): L2/강건 M 추정 직선; 이웃 연속성 또는 직선에 의한 지지 검사에 참고.
- [Fischler & Bolles 1981 RANSAC 원문](https://www.sri.com/wp-content/uploads/2021/12/ransac-publication.pdf): 최소 표본 모델·합의 집합. 이번 96컬럼 구조에서는 기존 이웃 거리/방향 연속성을 우선 재사용하여 시간 제한 탐색을 만들지 않는다.
