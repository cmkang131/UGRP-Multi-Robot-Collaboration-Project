# 조사와 채택 범위 (2026-10-14)

- [OpenCV HSV inRange 공식 튜토리얼](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html): RGB→HSV와 범위 임계화 표준 API를 사용한다. 문서가 우리 장면의 임계값/정확도를 보증하는 것은 아니다.
- [OpenCV connectedComponentsWithStats 공식 API](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html): 이진 마스크의8연결 성분·면적·영상 상자를 그대로 사용하고 라임 인접성만 작업 물체에 맞춰 확인한다. 검증된 CCL을 재구현하지 않는다.
- [Bolelli 등 Spaghetti Labeling, TIP29(2020), 저자 대학 저장소](https://iris.unimore.it/handle/11380/1181437), [저자 공개 코드 YACCLAB](https://github.com/prittt/YACCLAB): 현대 CCL 구현/비교의 공개 근거. 본 변경은 OpenCV API를 사용하며 특정 내부 CCL 알고리즘의 실행/속도 우위를 주장하지 않는다.
- 기존 calibrated own-camera ray→고정 빔 상면 교차는 유지한다. 색 띠 픽셀 인식과 metric grasp pose admission을 분리하는 설계는 이 실패 분석에서 도출한 적용 판단이다. 4.5cm 지지·HSV·면적32는 이 DEV 원본으로 조정한 후보이며 문헌상 보증/새 조건 인수 완료가 아니다.
