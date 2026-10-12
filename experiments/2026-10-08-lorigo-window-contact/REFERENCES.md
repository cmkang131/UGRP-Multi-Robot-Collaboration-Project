# 원문·구현 대응

조사 2026-10-08 06:54–06:59 KST, 코드 변경 전 README 사전등록 `b5459a2d`.
모든 PDF의 본문을 직접 읽었고 Lorigo Fig2–4도 확인했다. 원문은 로컬 outputs의
`lorigo-window-contact-v1/references/`에 저장; `results/research.json`에 URL·SHA.

1. [Lorigo, Brooks, Grimson, IROS1997, pp.373–379](https://people.csail.mit.edu/brooks/papers/final-iros.pdf).
   §2.1 이미지64²; §2.2 창20×10,가로45slice,1px 이동,각 하단창 고정참조,
   histogram L1 및 두채널합,gradient/normalized RG/HS(S<.033 무시).
   §2.3 실제 시스템은 median. §3.5 넓은패턴/그림자/반사 실패 명시.
   공개 라이선스 원본 코드를 가져온 것이 아니라 위 수식을 직접 구현했다.
2. [Delage, Lee, Ng, CVPR2006](https://ai.stanford.edu/~ang/papers/cvpr06-3dreconstructionindoor.pdf).
   §3,식5–8: 경계 위치·방향/chroma를 DBN으로 묶고 logistic회귀+EM으로 학습.
   §4: 48사진8건물,건물별holdout. 비균일 밝기/다색 바닥과 단순 색/edge heuristic의
   한계를 직접 논의한다. 현재 데이터에서 임의 파라미터를 끼운 DBN은 재현이 아니다.
3. [Lee, Hebert, Kanade, CVPR2009](https://publications.ri.cmu.edu/storage/publications/pub_files/2009/6/CVPR.2009.pdf).
   §3 Indoor World(직교·단일바닥·단일천장),§5 Algorithm1과orientation map,
   §6 54사진 평가. 낮은 경기장벽의 윗변을 천장접점으로 가정하면 안 된다.
4. [Pears, Liang, Chen, EURASIP2005](https://link.springer.com/content/pdf/10.1155/ASP.2005.2250.pdf).
   §2 바닥 homography/FOE/RP-space의1D상관·정현파,§3 cross-ratio 높이,
   §4.3 균일색 영역도 윤곽운동으로 바닥 종이와 상자를 구별.
   near-pure translation 제약이 있다. 저자 IROS2001 URL은404;2005는원문 확보.

## 구현 대응 및 원문 미명시 사항

`harness/wall_floor_lorigo.py`:

- `window_histogram`:32bin 정수count. 적분합은원문 incremental add/subtract와
  같은창을 계산하며 explicit20×10 brute-force count와시험으로 일치.
- `features`: gradient5×5Gaussian·중앙차분/normalizedRG/HS. RG정규화식,
  gradient스케일·경계차분·Gaussian크기·resize보간은 원문 미명시 처리 규약.
- `boundary_arrays`: frame마다각slice하단참조를새로잡고위로1px 이동.
  처음 L1>80인 위치만 저장. RG/HS는두L1합. 세모듈median,미검출=상단0.
- `detect`: undistort invalid support를검은RGB와분리. 입력기하유효성만 검사하며
  obstacle mask morphology/픽셀bin수락/시간학습fallback 없음.
  카메라·96열 ABI·4m·positive_depth·면연결은기존경로재사용.
- `wall_contact_detector.detect`: 새값일때만진입. 기존off/Ulrich/edge규칙 분기는보존.
  선택적 `Diagnostics`는결과저장만하며다음프레임의입력으로사용하지않음.

L1 문턱80은원문/공개코드에서확인한값이아니다. 기존count80을사전에고정했지만
pixel bin count와window L1은의미가다르므로egomap39와동일한분류기라주장하지않는다.
창중심(top+5)과45→96열nearest도우리카메라출력어댑터규약이다. 결과후바꾸지않는다.
절대정답벽을구별하는semantic classifier가아니므로바닥이아닌상자/기둥을벽으로
기록할수있는한계는평가유형에남긴다. 다음후보를이번코드에추가하지않는다.
