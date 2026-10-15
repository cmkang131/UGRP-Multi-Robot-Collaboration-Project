# search24 — 도달 가능한 차체 자세에서만 접근 후보 선택

시작 소스 `35861e92374c5fe936d5f54884a38bd7fe62f5fb` (search23 push).

## 수정 전 거부 분포

search23 R2 저장 원장을 먼저 집계했다. 반복 후보 시험 수이며 성공률 분모와 다르다.

|범주|시험 수|
|---|---:|
|집게 각도|9976|
|IK|4988|
|현재 기하|1648|
|기억 여유|976|
|계획 예산|555|
|연결 가시성|241|
|no_path|0|

총18384회 중 각도+IK14964회(81.4%). R3는 호스트 중단6회라 미측정이며 실패6회로 세지 않는다.

## 각도 제한 확인

`sim/grasp_act_pregrasp.py:24`의 `jaw_geometry`는 임의의 고정 각도 cutoff가 아니다. 손가락 패드의 pitch 방향 투영 길이와 `HANDLE_WIDTH_M/2*abs(tan(offset))`, 집게의 열림/닫힘 틈을 비교하는 **기하 필요조건**이다. 손목 yaw로 보상할 수 없다는 기존 모델을 유지한다. `FINGER_PAD_LENGTH_M=0.0143`은 `sim/masterpi_geometry_v3.py:157`의 drawing side view 측정, 반폭0.0045m는 `sim/masterpi_geometry.py:150`, 손잡이 폭0.040m는 `sim/zone_cargo.py:41`이다. 벌림35mm/이동16mm는 시뮬레이션 저작 기하이며 실제 로봇의 임의 화물 파지/마찰 각도 한계 실측을 뜻하지 않는다. 수치·조건을 넓히지 않는다. IK의 calibrated radial/PWM/pitch envelope도 그대로다.

## 조사와 적용 범위

- Vahrenkamp, Asfour, Dillmann, **2013**, *Robot Placement based on Reachability Inversion*, ICRA, pp1970–1975, DOI10.1109/ICRA.2013.6630839. 요청의2009년은 [KIT 출판기관 기록](https://publikationen.bibliothek.kit.edu/1000037428)과 다르다. 서지 확인 범위이며 이 사이트에서 논문 본문을 얻지 못했다.
- Zacharias, Borst, Hirzinger, **2007**, *Capturing Robot Workspace Structure: Representing Robot Capabilities*, [DLR 기록](https://elib.dlr.de/51226/), DOI10.1109/IROS.2007.4399105. DLR은 원문 비공개이며 외부 PDF 열기 실패. 서지와 capability-map 개념 확인 범위를 구분한다.
- Makhal & Goins, **2017**, *Reuleaux: Robot Base Placement by Reachability Analysis*, [원문PDF](https://arxiv.org/pdf/1710.01328), [공식 구현](https://github.com/ros-industrial-attic/reuleaux/tree/master/map_creator), [ROS-I 설명](https://rosindustrial.org/news/2016/10/18/google-summer-of-code-project-workspace-analysis-and-base-placement). PDF 본문과 공식 문서에서 reachable pose의 역변환→task pose에 합성→base placement를 확인했다.

적용은 현재 search23 visible-only 빔 끝 교사의 유한 평면 IRM이다. ROS/MoveIt 의존성을 추가하지 않는다. 주행은 기존 격자 A*, 장애물/상대/시야/팔 검사를 그대로 통과해야 한다. 이산 지도 밖 연속공간 완전성·접촉 성공을 주장하지 않는다. 상자·크레이트의 다른 교사 경로는 이 빔 교사 검증과 구분한다.

`search24_irm=search24_irm_v1`, `search24_budget=search24_checks_v1` 모두 기본 off. 새 후보는 둘 다 켠다. 정확한 현재 자기 RGB 대상 높이와 고정 기구학으로 환경 장애물 검사 전에 reachable map을 만들고 정확한 높이로 캐시한다. calibrated radial envelope2mm, inward offset5도와 기존 거리 anchor를 샘플링한다. 전체 hover/8단계 descent/lift IK와 기존 jaw 조건을 통과한 cell만 저장한다. 역변환 cell을 현재 **보이는** 맡은 끝에 합성한다. fresh band가 없으면 새 후보를 내지 않는다. 전체 정답·접촉·측정 관절·held object 좌표를 추가하지 않는다.

계산량 토글은 틱당 기존98304개의 논리 검사 상한만 적용하고 wall3초를 제거한다. pick-cloud cache cold/warm 양쪽에서 같은 sample 수를 차감한다. 가시성 문턱5·기하/σ 여유·FOV·weld OFF는 유지한다. 거부 row에는 category, blocked_object, min_gap_m, gap_scope를 남긴다. IK/시야/예산처럼 기하 차단 증거가 없는 경우 null과 명시적 not-applicable 범위를 남겨 물체나 틈을 꾸며내지 않는다. cap_s 종료는 cap_end로 구분한다.

## 실행 기록

GCP n4-highcpu-64, scheduling maxRunDuration86400초/STOP, budget-stop ACTIVE, 모델 키/에이전트 자격증명 전송0. 임대/예약은 admission.lock 아래 EXIT와 released/completed를 구분해 총40이하로 확인한다. Mac에서는 비물리 회귀만 실행한다. VM에서 분석하고 요약/몽타주/실패 자기 프레임만 회수한다.

첫 reference wrapper는 batch에 없는 `--self-pose-source issued` 인수 때문에 CLI EXIT2, 물리 실행0으로 끝났다. 해당 인수를 제거한 frozen source35861e92 재측정6회를 별도 이름으로 제출했다. CLI 실패는 결과/라운드 분모에 합산하지 않는다.

오프라인 검사: 신규IRM10건(모든 cell의 IK/각도, fresh-only, 좌표변환, wall 독립, cold/warm 동일 계산량, 실패 장면의 완전 stance)을 통과했다. 기존 search21 helper가 ALL_MODES 추가로 새 토글을 의도치 않게 켜므로 명시OFF로 수정했다. 기존 search15 mock은 search23에서 이미 추가된 navigation keyword를 받도록 mock 인수만 고쳤다.

### search23 R3 후보 재측정

`search24-r3-reference-35861e92-fixed`, 실행 SHA35861e92374c5fe936d5f54884a38bd7fe62f5fb. 이전 R3 SHA0205485e의 실행 소스13파일 hash와13/13 일치(문서 커밋 차이). 6회 완료, 성공2/6, HOST_ERROR0, cap_end0. 각도21460·IK10730·현재기하5856·기억860·연결시야493·no_path0. episode000/001은8311709 base/v6,002/003은315709 base/v6가 접근 인계로 종료했다. 새8312300/8312301 성공. VM 전체 SHA256SUMS 검증 및 선택 실패RGB48장+몽타주4개 해시 일치. 실제 프레임에서 r1의 빔 끝 접근이 멈추고 r2가 청록 끝에서 대기함을 확인했다.

### 후보 R1

`bacfb71fbe157e50afaa573c02867f90ffd8b158`, 6회 완료,2/6 성공, HOST_ERROR0, cap_end0. 각도0·IK0, 기록상 현재기하28262·기억6149·연결시야1383·계산예산24·no_path0. endpoint_feasible835와 feasible20은 거부가 아니므로 별도다. 첫30SIM초에 이르기 전에 모든 실행이 끝났으므로 first30 실측은 미생성이다. 전체 실행 wall/SIM 중앙5.204(경고;6.0미만),315709 v6 단일 실행8.446. 호스트/프로필/라운드는 합산하지 않는다.

원본의 `unsafe_body_sweep` row가 가진 failure_audit는 실제 이동 구간의 기억 차단물인데, 기존 record_candidates는 목표 collision_audit만 봐 현재기하로 분류했다. 이 분류는 search22 재관측 대상 선택에도 쓰여 실제 기억 차단물을 누락할 수 있다. R2는 search24 토글을 켠 경우에만 failure_audit→goal audit→path audit 순으로 원인을 사용한다. 기존 토글off의 분류/재관측 행동은 유지한다. 여유 축소·기억 TTL 변경·위치 정답 보정이 아니다. 정확한 거리/높이의 불변 IK certificate를 실제 후보/팔 cloud 검사에서도 재사용해 같은 IK를 반복 풀던 비용을 줄인다. 변화한 재관측 선택은 새 SHA의 물리 진단으로 구분한다.

GCP의 자기 visible_measurements+실제 발행 명령만으로 한 단면을 재구성한 추가검사에서 숨은 memory의 실제/요구 gap 차이를 확인했다. 이 분석은 teacher의 free-space/reobserver cache 전체 재생이 아니므로 실제 전체 제어기 상태와 동등하다고 주장하지 않는다. R2 수정 근거는 원본 row에 이미 저장된 failure_audit다.
