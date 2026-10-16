# release16 — 몸통과 맡은 끝 띠를 하나의 관측 물체로 정합

기준 `7379fdd31a97b29ad2edc83cb8f6df1c94a8916e`, 작업 브랜치 `claude/grasp-act-probes`.
`release13.md`→`release14.md`→`release15.md`와 지정된 Mac 회수 원본을 먼저 읽었다.
새 프로필 **`release16_known_shape_v1`**, 기본 `off`. PR #491 head는 별도 `claude/grasp-act-release`이며 이 작업 브랜치 SHA를 코멘트로 연결한다.
새 실행 SHA는 이 기록을 포함한 커밋 및 새 큐에 고정한다. 결과를 이전 프로필과 합산하지 않는다.

## 변경과 입력 경계

- 인식의 대상은 **몸통 + 맡은 끝 띠가 붙은 한 빔**이다. release15의 좁힌 teal 색 범위·자기 RGB 왜곡 보정을 그대로 쓴다. 연결성분은 합집합에서 한 번 정하고 `valid`, 선 모델, FOV 경계가 같은 선택 마스크를 사용한다. 로그에 마스크 SHA256·면적·선 잔차·성분 수를 남긴다.
- JPEG 색 경계의 작은 틈은 3×3 closing으로 **성분 소속만** 연결한다. 특징에는 원래 관측 픽셀만 사용한다. 떨어진 조각은 각각 관측된 선 방향 차이 ≤5°, 폭비 0.5–2, 종방향 빈 간격 ≤96px, 중심선 간격 ≤max(5px, 좁은 폭의 15%)일 때만 병합한다. 별도의 평행 물체·너무 큰 빈틈은 합치지 않는다.
- 선은 양 측면 경계가 보이는 중앙 20–80% 행 창의 중심을 4px 간격으로 얻고, 최소 12행·120px 구간에서 2점 RANSAC→합의집합 재적합을 한다. 후보 128개+끝점 쌍, RNG=0, 잔차4px·최소85% 합의다. 단순 색 전체의 PCA나 잘린 중심만으로 yaw를 만들지 않는다.
- 전수 검사에서 추가로 발견한 **떨어진 파란 목적 구역**은 몸통 지지가 없는 색 전용 성분으로 제외한다. 색만 같은 배경을 끝 띠로 취급하지 않는다. **끝면의 다면체 윤곽** 때문에 단일 선을 지지하지 못하면 `beam_direction_unresolved`로 가시성은 남기되 방향은 null, FOV 재관측만 허용한다. 이를 물체 미관측으로 바꾸어 1초 뒤 실패시키지 않는다.
- **무효 허용 1초, 정지 후 재관측, 16초 전체·3초 무진척·누적 이동 한도, FOV 비용·이동 후보·지도 여유·명령은 release15 그대로**다. `LineAlign.tick`, `line_step`, 지도 함수를 재사용하며 새 클래스는 인식 함수와 오류 접두사만 바꾼다. 새로운 학생 대체 경로가 아니다.
- 제어 입력은 자기 RGB·자기 발행 명령·고정 보정·정적 지도뿐이다. 정답은 아래 평가 오차에만 쓴다. 공용 top은 제어·인식에 넣지 않았고, 기존 개요 배열은 관계 검토에만 열었다. weld off, 기록 모드 정답 옵션 거부 및 미구현 학생 writer 거부를 유지했다. 시연 준비 prefix를 RGB-only 실행/학생 데이터로 재분류하지 않는다.

## 전수 범위·정의

두 root 아래의 내려놓기/놓고 다시 보기 실행의 모든 로컬 자기 JPEG를 파일 목록으로 수집했다.
`/Users/changmin/projects/ugrp/outputs/gcp1-runs/`와
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/`만 사용했다.
`eval-own`, `eval-regrasp-input`, `eval-lookaround-input` 및 과거 평탄화 파일명을 포함한다.
개요·배열 이미지·다른 화물 작업은 분모에서 뺐다. `(run, relative path, sha256)`가 같은 복사본만 중복 제거했으며 서로 다른 시각의 같은 픽셀은 제거하지 않았다.
원본 640×480 입력과 320×240 검토 JPEG를 별도 집계한다. 후자는 같은 보정 함수에 넣기 위해 640×480으로 선형 확대했으며 **원본 입력과 동등하다고 하지 않는다**.
회수되지 않은 파일·동영상에서 새로 추출하지 않은 프레임은 포함하지 않는다. release13은 새 실행이 없는 분석 라운드로, 그때 읽었던 release11/12 원본이 이번 목록에 포함된다.

`valid`는 현재 빔 물체 관측이 있다는 뜻이며 선 방향·정렬·물리 성공과 다르다. `ambiguous`는 복수 물체/비선형을 거부한 구버전 상태도 포함하고, `unobserved`는 면적 부족/미검출이다.
둘러보기에서 빔이 없는 정상 영상도 포함하므로 valid 비율은 **분류 정확도나 교사 성공률이 아니다**.
연속성은 같은 실행·로봇·스트림의 인접 저장 프레임 중 두 방향이 모두 있고 `0 < Δt ≤ 1.01s`인 쌍만 잰다. 방향 급변은 10° 초과, 위치 급변은 y=239.5에서 선 위치64px 초과다. 빠진 프레임을 보간하거나 무효 구간을 건너뛰지 않는다.

**43개 실행, 4,870장 전수 처리; 복사본 498장 제외, JPEG 4,870/4,870·payload 457개 원본 manifest 대조 통과.** 시각 연결이 없는 프레임 28장은 검출 분모에 포함하고 시간 연속성/방향 평가에서는 제외했다. 로컬 JPEG가 없는 실행 123개는 상세 목록에 별도 기록했다.

[짧은 요약·해시](release16-summary.json), [프레임별 전체 표 JSONL](release16-frames.jsonl.zst), [실행별 통계·재생·payload 해시](release16-detail.json.zst). `zstd -dc <파일>`로 전체 행을 읽는다. 프레임 표에는 원본 경로·시각·해시·구/신 valid/reason·선 위치/기울기·FOV·명령 분기·평가 오차가 있다.

|범위|N|구14/15 valid / ambiguous / unobserved|신16 valid / ambiguous / unobserved|띠 분할|
|---|---:|---|---|---:|
|전체|4870|3495 (71.77%) / 224 (4.60%) / 1151 (23.63%)|3726 (76.51%) / 0 (0.00%) / 1144 (23.49%)|219|
|eval-lookaround-input/640x480|509|136 (26.72%) / 1 (0.20%) / 372 (73.08%)|137 (26.92%) / 0 (0.00%) / 372 (73.08%)|1|
|eval-own/320x240|4106|3116 (75.89%) / 219 (5.33%) / 771 (18.78%)|3338 (81.30%) / 0 (0.00%) / 768 (18.70%)|214|
|eval-regrasp-input/640x480|255|243 (95.29%) / 4 (1.57%) / 8 (3.14%)|251 (98.43%) / 0 (0.00%) / 4 (1.57%)|4|
|실제 line_recheck 입력|28|22 (78.57%) / 4 (14.29%) / 2 (7.14%)|26 (92.86%) / 0 (0.00%) / 2 (7.14%)|4|

구14·15의 valid/선 모델은 같은 shaft-only 함수를 사용하므로 이 집계값은 동일하다. 띠 분할은 새 인식에서 valid인 선택 물체 안에 몸통 성분이 2개 이상이고 둘째 면적 > 첫째30%인 경우다. 분할을 새 물체 성분으로 만든 경우를 세므로 단순 valid 증가와 다르다. 실제 저장 corpus의 큰 빈틈 직선 병합 수는 0장이며 해당 분기는 별도 합성 회귀로 검증했다.

|선 연속성|방향 있는 프레임|인접 유효쌍|방향 급변 >10°|위치 급변 >64px|
|---|---:|---:|---:|---:|
|release14|1050|639|0|0|
|release15|1050|639|0|0|
|release16|1229|731|0|0|

평가 정답이 있는 프레임은 빔 양 띠 중심·몸 pose를 발행 팔 PWM의 고정 카메라 FK로 투영해 선 방향 오차를 쟀다. **실측 카메라 외부 파라미터/관절은 저장되지 않아 정확한 픽셀 정답 오차는 미확인**이며 아래는 정답 pose+명령 FK의 평가 전용 근사다. 미측정 오차를0으로 넣지 않았고 제어 선택에는 반환하지 않았다.

|비교 범위|모델|평가 가능 N|방향 오차 중앙값 / p90 (°)|
|---|---|---:|---|
|각 모델 방향 유효|release15|653|0.0646 / 1.1338|
|공통 동일 프레임|release15|642|0.0632 / 1.1352|
|각 모델 방향 유효|release16|832|0.0693 / 0.7530|
|공통 동일 프레임|release16|642|0.0556 / 0.6020|

둘러보기 자세의 오차와 근거리 정렬의 오차를 섞어 개선으로 단정하지 않는다. 스트림별 오차와 개별 미측정 사유/명령 시각은 상세 파일에 있다. 단일 선 방향을 아직 지지하지 못한 끝면 영상 4장은 가시성만 유지하고 yaw를 허용하지 않는다. 떨어진 색 띠 후보 제외는 156장에서 적용됐다. 구 valid→신 invalid는 0장이다.

## 실행별 전수 표

|실행|N|구 valid/ambiguous/unobserved|신 valid/ambiguous/unobserved|띠 분할|신 방향/연속쌍/급변(각·위치)|
|---|---:|---|---|---:|---|
|probe-setdown-0-4626ee99|14|12/0/2|12/0/2|0|4/0/0·0|
|probe-setdown-1-4626ee99|14|12/0/2|12/0/2|0|4/0/0·0|
|r12d-00-97942a82|24|20/0/4|20/0/4|0|8/0/0·0|
|r12d-01-97942a82|153|139/2/12|141/0/12|1|48/37/0·0|
|r14d-00-7369ad5e|22|18/3/1|21/0/1|3|9/3/0·0|
|r14d-01-7369ad5e|18|15/0/3|15/0/3|0|4/0/0·0|
|r15d-00-7379fdd3|18|13/4/1|17/0/1|4|12/3/0·0|
|r15d-01-7379fdd3|18|14/4/0|18/0/0|4|6/2/0·0|
|release-command-diagnostic-00-cdace35e|16|10/2/4|12/0/4|2|2/0/0·0|
|release-command-diagnostic-01-cdace35e|16|10/2/4|12/0/4|2|2/0/0·0|
|release-command-diagnostic-02-cdace35e|22|10/2/10|12/0/10|2|4/0/0·0|
|release-command-gate-04-cdace35e|22|12/2/8|14/0/8|2|6/0/0·0|
|release-command-gate-05-cdace35e|22|12/2/8|14/0/8|2|2/0/0·0|
|release-command-gate-06-cdace35e|22|10/2/10|12/0/10|2|4/0/0·0|
|release-command-gate-12-cdace35e|24|12/2/10|14/0/10|2|6/0/0·0|
|release-command-gate-22-cdace35e|22|12/2/8|14/0/8|2|4/0/0·0|
|release-command-gate-23-cdace35e|22|12/2/8|14/0/8|2|6/0/0·0|
|release-diag-1-5d6e8291|12|12/0/0|12/0/0|0|0/0/0·0|
|release-diag-4-5d6e8291|14|14/0/0|14/0/0|0|3/0/0·0|
|release-gate-38-4a69e6bc|12|11/1/0|12/0/0|1|2/0/0·0|
|release-gate-39-4a69e6bc|92|88/4/0|92/0/0|4|27/19/0·0|
|release-global-diagnostic-02-14ddb6ad|226|174/16/36|190/0/36|16|66/42/0·0|
|release-global-diagnostic-06-14ddb6ad|136|108/6/22|114/0/22|6|39/24/0·0|
|release-v13-6-4626ee99|16|16/0/0|16/0/0|0|4/0/0·0|
|release-v13-7-4626ee99|12|12/0/0|12/0/0|0|2/0/0·0|
|release11-diag-01-c9ba20a6|204|194/2/8|196/0/8|1|116/95/0·0|
|release11-diag-08-c9ba20a6|322|278/8/36|293/0/29|6|75/57/0·0|
|release5-diagnostic-00-e96386d3|316|224/24/68|248/0/68|24|80/50/0·0|
|release5-diagnostic-01-e96386d3|214|154/16/44|170/0/44|16|53/34/0·0|
|release5-diagnostic-02-e96386d3|176|93/5/78|98/0/78|5|32/13/0·0|
|release5-diagnostic-03-e96386d3|110|84/4/22|88/0/22|4|30/18/0·0|
|release5-diagnostic-04-e96386d3|162|123/5/34|128/0/34|5|44/27/0·0|
|release5-diagnostic-05-e96386d3|212|156/10/46|166/0/46|10|54/35/0·0|
|release5-diagnostic-06-e96386d3|212|159/9/44|168/0/44|9|51/33/0·0|
|release6-diagnostic-07-63201b88|225|121/12/92|133/0/92|12|40/18/0·0|
|release7-diagnostic-00-a2314b16|110|86/2/22|88/0/22|2|28/18/0·0|
|release7-diagnostic-01-a2314b16|110|82/4/24|86/0/24|4|28/16/0·0|
|release7-diagnostic-02-a2314b16|212|158/10/44|168/0/44|10|55/34/0·0|
|release7-diagnostic-03-a2314b16|368|163/12/193|175/0/193|11|53/25/0·0|
|release7-diagnostic-04-a2314b16|264|191/17/56|208/0/56|17|68/42/0·0|
|release7-diagnostic-05-a2314b16|214|159/9/46|168/0/46|9|54/34/0·0|
|release7-diagnostic-06-a2314b16|264|194/12/58|206/0/58|12|66/39/0·0|
|release7-diagnostic-07-a2314b16|186|98/5/83|103/0/83|5|28/13/0·0|

## 실패 4건과 저장 상태 분기 재생

|실행 / seed|실패 직전 저장 자기 입력|구→신|신 분기(지도 검사 포함)|
|---|---|---|---|
|r14d-00-7369ad5e / 74963|r2, 35.8s|shaft_missing → beam_missing, valid=False|unobserved; 전/옆/yaw 0.0000/0.0000/0.0000|
|r14d-01-7369ad5e / 74976|r1, 32.8s|shaft_missing → beam_missing, valid=False|unobserved; 전/옆/yaw 0.0000/0.0000/0.0000|
|r15d-00-7379fdd3 / 74963|r2, 38.4s|shaft_ambiguous → beam_rows, valid=True|recover_fov; 전/옆/yaw 0.0040/0.0000/0.0000|
|r15d-01-7379fdd3 / 74976|r1, 36.4s|shaft_ambiguous → beam_rows, valid=True|line_ibvs; 전/옆/yaw 0.0000/0.0014/-0.0111|

**release15 두 건의 색 띠 분할은 valid로 복원했다. release14 마지막 두 장은 각각 실제 선택 색 픽셀0 / 약103개라 복원할 시각 근거가 없다. 4/4 회복으로 보고하지 않는다.** release14 시야 상실 이전 r2 34.8s / r1 31.8s는 release15에서 도입한 yaw0 시야 이동을 유지한다. 마지막 실패 tick은 teacher 행이 없으므로 직전 발행 명령(최대0.1s 전)을 사용했고 나이를 별도 기록했다. 미래 명령·미래 RGB 위치 보정은 사용하지 않았다.

74963/74976은 반복 튜닝된 개발 시드다. 분기 이후 저장 영상은 **옛 제어기의 궤적**이며 새 폐루프 궤적으로 이어 붙이지 않는다. **물리 효과·재파지·들기·GO/ACK·놓기 성공은 미검증**이다.

## 직접 열람·검증·대기열

release14/15 각 두 실행의 처음·중간·끝 6시각×개요/r1/r2 배열72장과 release15 실패 전 자기 원본12장을 직접 확인했다. release14 개요 상대시각은 00:0/7/13.3/20.3/26.3/33.3s, 01:0/6/12.3/18.3/24.3/30.3s; release15는 00:0/7/14.3/21.3/29.3/36.3s, 01:0/7/13.3/20.3/27.3/34.3s. 실패 자기 입력 world시각은 00:34.8/35.6/36.2/37.0/37.6/38.4s, 01:31.8/32.8/33.6/34.6/35.4/36.4s다. 본 범위에서 두 로봇은 반대 끝이며 같은 끝 접근/상호 막힘은 보이지 않았다. 전수에서 드러난 추가 반례14장도 직접 열었다. 모든4,870장을 사람이 본 것은 아니고 전수 인식 계산과 선택 영상 열람을 구분한다.

관련 시험만 **59 passed in 113.05s (0:01:53)**: `tests/test_release16.py`, `tests/test_release15.py`, `tests/test_grasp_act_release_run.py`. [시험 로그](release16-tests.txt). 실제 러너의 fake-backend 시계 진행·지도·픽셀 인식·순차 들기/ACK 연결을 검증했으며 시뮬레이터/렌더는 실행하지 않았다. 새 회귀는 CI 목록에도 등록했다.

[진단 계획](release16-diagnostic-plan.json)은 **재현2(74963·74976) → 원본 검토 → 새 진단7(78460–78466) → 정지**다. [시드 감사](release16-seed-audit.json.zst)는 main+열린 PR20개 head, 공유 outputs 전체의 기존 대기열 JSON192개를 검사했으며 숫자·등록 범위 충돌0, 해시 내부 우연 부분일치는 제외했다. [직전 재확인](release16-seed-recheck.json)도 보존했다. 원격 호스트 사용 이력은 접속 금지로 조회하지 않았다.

새 큐만 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate-<SHA8>.json`에 배치한다. `approved=false`, top-level `ready=false`, 모든 `stage_ready=false`, 9/9 run `ready=false`, `authorized_run_count=0`; **관문40 미승인·미등록·자동승격 금지**다. 예산9×96MiB=864MiB, Mac 분석 산출물은 64MiB 상한(dev)으로 한정했다. 원본은 보존하고 상세 원장만 무손실 zstd 압축·해제 해시를 대조했다. 기존 큐는 수정하지 않는다. 새 파일의 고정 SHA·명령·승인 플래그와 기존 큐 전후 해시, push/PR 영수증은 `outputs/release16/delivery.json`에 남긴다.

## 참고 자료 — 확인 범위 (2026-10-15)

- Fischler & Bolles (1981), *Random Sample Consensus: A Paradigm for Model Fitting with Applications to Image Analysis and Automated Cartography*, CACM 24(6), 381–395, DOI 10.1145/358669.358692. [SRI 저자기관 서지](https://www.sri.com/publication/artificial-intelligence-pubs/random-sample-consensus-a-paradigm-for-model-fitting-with-applications-to-image-analysis-and-automated-cartography-2/)에서 제목·저자·연도·권호 확인. SRI 페이지 소개는 논문과 무관한 내용이므로 인용하지 않았다. [ACM 원문](https://dl.acm.org/doi/10.1145/358669.358692)은 403, Stanford 원문 사본은 timeout으로 **1981 원문 본문 직접 확인 미확인**. 아래 공식 구현 설명으로 알고리즘을 확인했다.
- [scikit-image `measure.ransac` 공식 문서](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.ransac): 최소 표본 선택→모델 적합→잔차로 합의집합 선택→최대 합의집합의 전체 표본으로 재적합 절차를 확인했다. 이를 2점 직선·128 후보·고정 RNG·합의집합 최소 85%·잔차 4px로 구현했다. 행 y는 정확한 표본 위치이므로 x(y) 선형회귀를 사용한다. 임계값은 이 프로젝트의 제한이며 논문 보장을 승계하지 않는다.
- [OpenCV 연결성분·선 적합 공식 문서](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html): `connectedComponentsWithStats`의 label/면적/경계, `fitLine`의 선 매개변수와 강인 적합 설명 확인. 몸통+맡은 띠 합집합의 연결 성분을 먼저 만들며 3×3 closing은 JPEG 경계 연결에만 사용하고 실제 특징 계산에는 원래 픽셀만 쓴다. collinear 분리는 독립 선의 방향·위치·폭·간격 정합을 통과할 때만 병합한다.
- [PCL ModelOutlierRemoval 공식 예제](https://pointclouds.org/documentation/tutorials/model_outlier_removal.html): 알려진 기하 모델과 관측의 잔차로 inlier/outlier를 가르는 구조 확인. PCL의 3D 구/점군 코드 자체를 이식하지 않았다. 여기서 `known_shape`는 곧은 빔의 투영 선 및 색 띠 부착 관계뿐이고 실시간 정답 위치/길이 투영을 인식에 주지 않는다. 6D pose 정합·원문 전체 재현·물리 성능은 주장하지 않는다.
