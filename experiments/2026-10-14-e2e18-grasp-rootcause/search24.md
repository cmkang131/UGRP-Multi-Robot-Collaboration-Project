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

### 후보 R2 — 최종 NOT_READY_2_OF_6

실행 SHA **ec8752a1e72d9a1bd1c01c0a292467e75039e75b**, `search24-r2-short6-ec8752a1`. 6회 모두 완료, 성공2/6, HOST_ERROR0, cap_end0. 재측정+후보2개로 물리 진단3묶음(각6회)을 마쳤다. CLI 인수 실패는 물리0회인 별도 실행 기록이다.

|원본별 거부 범주|search23 R3 후보 재측정|search24 R1|search24 R2|
|---|---:|---:|---:|
|각도|21460|0|0|
|IK|10730|0|0|
|현재 기하|5856|28262|26273|
|기억 여유|860|6149|14079|
|연결 가시성|493|1383|1383|
|계산 예산|0|24|24|
|no_path|0|0|0|
|물리 성공/완료|2/6|2/6|2/6|

같은 후보를 여러 틱·단계에서 재검사한 **시험 건수**다. 후보 집합·재관측 행동·라운드 길이가 달라 거부 건수 감소를 성공률 개선으로 해석하지 않는다. R1은 이동 구간 기억 차단의 분류 오류가 포함된 당시 기록이며 R2와 단순 합산하지 않는다. R2 endpoint_feasible983·feasible28은 거부가 아니므로 위 표에서 제외했다.

8311709 base/v6는17.5초(R1)에서24.6/24.1SIM초(R2)까지 진전했으나 결국 접근 인계다. 끝 앞 tile_1(base)/red_2(v6)의 현재 기하와 기억 틈, 뒤쪽 can_1/yellow_1의 기억 여유가 반복 차단한다.315709 base는 yellow_1와 기억 peer r2, v6는 can_1와 연결 시야가 남는다. 최소 틈은 `search24-r2-blockers.json`에 범주·이름·표본 수·필요 여유와 함께 저장했다. 예: 기억 can_1의 거부 후보 최소gap0.007429m/요구0.072486m(v6 315709); 이 값은 **거부 후보 전체의 최소값**이며 실제 로봇의 충돌이나 최종 자세 틈을 뜻하지 않는다. 격자·σ 여유·각도·가시성 문턱을 낮추지 않았다.

R2 전체 wall/SIM 중앙4.764,315709 v6 단일7.819이다. 모두30SIM초 전에 끝나 첫30SIM초 측정은 미생성이고, 위 숫자는 전체 짧은 실행이다. 초기 host load는R1과R2가 달라 속도 차이를 IK 재사용만의 효과로 단정하지 않는다. 첫30SIM초 실제 부하에서 속도·재생 동등성을 새로 확증한 것은 아니다. 고정 입력의 cold/warm 검사량/출력 동등성은 비물리 회귀 범위다.

R2 자기 visible measurement6380행을 최종 감사해 invisible_measurements0·held_world_reads0이며 켠 감사가6/6 모두 있다. 세 묶음 모두 VM의 전체 SHA256SUMS 검증 완료. 각 실패4회의 자기RGB48장+몽타주4개, 세 묶음 합계144프레임+12몽타주를 해시 검증하고 몽타주에서 직접 확인했다. R2 8311709는 실제 카메라를 바꾸어 보면서 파랑 끝에 더 접근했으나 파지까지 못 갔고, r2는 청록 끝에서 계속 대기한다.315709 두 경우도 파랑 끝 접근 뒤 인계다. Mac에는 요약·선택 실패RGB·몽타주만 회수했고 전체 raw는GCP 영속 디스크에 남겼다. 현재 실행 원본의 호스트 밖 전체 백업은 없다.

관련 비물리 회귀 **160통과**. 새 소스의 IK certificate, 가시성/차체/팔 기하, cache 논리 비용, 실제 차단물 분류, off 동작·admission·batch 전파를 검사했다. Mac 물리·렌더0, 판단 모델 호출/토큰0, 학습 데이터/ACT학습0. 성공률≥95% 교사 관문을 통과한 결과가 아니다.

**4/6 조건 미달이므로 새32회 대기열을 만들거나 제출하지 않았다.** 기존 search23 대기열도 변경하지 않았다. 알고리즘은기본off인 후보로 남긴다. 자기 실행 worker0·예약/임대 해제를 확인했고 다른 작업의 예약·실행·VM을 건드리지 않았다. 기록 요약은 `search24-results.json`, 라운드 원본 연결/해시는 각 `search24-*-results.json`, 마지막 거부 세부는 `search24-r2-blockers.json`이다. 커밋·push·PR댓글을 마친 후 종료하며 병합은 하지 않는다.
