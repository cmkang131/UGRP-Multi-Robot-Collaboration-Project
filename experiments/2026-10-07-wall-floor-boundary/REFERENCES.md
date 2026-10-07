# 단안 바닥 경계 검출 조사 (2026-10-07)

| 방법 / 확인한 1차 출처 | 원래 방법 | 이번 제약과 선택 |
|---|---|---|
| [Delage, Lee, Ng, CVPR 2006](https://ai.stanford.edu/~ang/papers/cvpr06-3dreconstructionindoor.pdf), §2–3 | floor chroma·열별 경계·소실점 방향을 DBN으로 추론. 경계 특징의 logistic regression은 학습 라벨 필요 | 외형/구조를 함께 다루지만 공개 학습 계수·실행 코드를 확보하지 못했다. GT를 평가에만 쓰는 이번 작업에서 임의 계수를 넣고 원본 구현이라고 부르지 않음 |
| [Lee, Hebert, Kanade, CVPR 2009](https://www.cs.cmu.edu/~dclee/pub/cvpr09lee.pdf), §3–5 | 선분/소실점·corner 제약으로 Indoor World 가설을 만들고 orientation map으로 검증 | 천장–벽·바닥–벽 대칭과 3방향 선분을 활용. 낮은 고정 카메라·좁은 FOV에는 천장/모서리가 부족하며 낮은 독립 벽도 있어 이번 기본법으로 부적합 |
| [Ulrich & Nourbakhsh, AAAI 2000](https://www.cs.cmu.edu/~illah/PAPERS/abod.pdf), §3–4 / [저자 기관 소개](https://publications.ri.cmu.edu/appearance-based-obstacle-detection-with-monocular-color-vision) | Gaussian5×5 → HSI → 앞쪽 참조 영역의 hue/intensity 1D histogram → 평균 필터 → 어느 histogram이라도 threshold 미달이면 obstacle. 열별 가장 아래 obstacle을 바닥 접점으로 투영 | **§4의 single-frame basic variant 선정.** 학습 라벨/외부 모델/새 카메라 없이 실내외 로봇에서 사용한 방법. 원본 §5–6의 encoder 기반 온라인 학습은 명령 DR로 주행 성공을 보장할 수 없어 채택하지 않음 |
| [Lee, Yi & Cho, Sensors 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4813886/) / [출판사](https://www.mdpi.com/1424-8220/16/3/311) | 저고도 카메라의 시간적 IPM 비교·바닥 외형·MRF segmentation | 가까운 바닥에 적합하지만 영상 간 실제 이동/수직 가설 비교까지 필요. 이번에는 먼저 단일 프레임 분할의 독립 관문을 둠. 초록·공개 본문 검색 확인, PMC 직접 재열람은 접근 확인 화면으로 제한됨 |

## 선택한 알고리즘과 변경 경계

Ulrich §4의 네 단계를 순서 그대로 독립 구현한다. 원본 저자 코드 페이지는 이번 조회에서 열리지 않아
원본 소스 복사/동일 바이너리라고 주장하지 않는다. 알고리즘을 재구현하며 논문 PDF 자체는 Git에 재배포하지 않는다.
HSI의 hue는 저조도/저채도에서 무효화, intensity는 RGB 평균. 논문에 명시된 Gaussian5×5와
hue/intensity count threshold60/80은 그대로 쓴다. 논문에 명시되지 않은 bin 수256, histogram 평균 창5,
최소 intensity10/255·saturation.1은 구현상 고정값으로 공개한다. 결과로 조정하지 않는다.

참조 영역은 원문처럼 카메라 앞 바닥의 사다리꼴이다. 우리 fixed calibration으로 바닥의
전방 .30–1.00 m·좌우 ±.30 m를 이미지에 투영한 영역을 사용한다. valid image/support가
1,024픽셀 미만이면 보류한다. 원문과 달리640×480 undistorted 영상, 실제 K/D·21자세 카메라 보정,
양의 깊이·4 m·자기 명령 정착 gate를 사용한다. 카메라 높이/FOV/팔 자세는 바꾸지 않는다.
참조 영역에 장애물이 없다는 **가정은 검증된 free 관측이 아니다**. 실물 조명·하중 일반화는 미검증이다.

원문은 벽 의미 분류기가 아니라 obstacle/floor 분류기다. 다른 색 바닥·물체도 obstacle이 될 수 있고
벽과 바닥 외형이 같으면 놓친다. 이 한계를 숨기지 않고 벽 GT에 대해 FP/FN을 그대로 센다.
기존 면 연결(최소4열/거리·방위 연속성)은 지도 API 변환에만 재사용하며 DBN/새 학습으로 포장하지 않는다.
IPM은 원문 §3의 평면/비돌출 가정에 따른 ray-plane 교점이며 이미 있는 보정 기하를 쓴다.

[OpenCV GaussianBlur](https://docs.opencv.org/4.x/d4/d86/group__imgproc__filter.html)와 기존 NumPy/OpenCV만 사용한다.
새 라이브러리·venv·학습 가중치·모델 호출 없음. 새 파이프라인의 수치/회귀 시험과 독립 검출 관문은 README에 둔다.
