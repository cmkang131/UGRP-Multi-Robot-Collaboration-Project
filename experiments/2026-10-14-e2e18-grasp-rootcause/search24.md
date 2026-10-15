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
