# egomap50 — 자기 문 후보·확인·문 경유 이동

2026-10-08 사용자 요청. egomap49 보고/소스 a7d41435를 먼저 완료했다.
검출기 egomap34·SEARCH·tape·rotL·RBPF/graph·360s 탐색·귀환 판정은 동결한다.
이번 결과는 기존 녹화의 오프라인 개발 진단이며 새 확증 자료가 아니다.

## 실행 전 등록

- 순서: egomap46 A/B(seed46001), egomap47(seed47001)을 개발 진단 → 설정 동결 커밋 →
  egomap49 seed49001–49006 각각 오프라인1회. 조기 중단2건도 제외하지 않는다.
  저장 자기 RGB 유래 선분·바닥 표본·자기 추정 자세만 입력. GT 문/카메라/경로는 출력 봉인 후 채점만.
- 검출 옵션 `door_detector=complete_points_v1`, 이동 옵션 `door_navigation=room_doors_v1`, 둘 다 기본off.
  원문 CP(Type I/II) + 폭/방향 검사, 중복 공간 연관, 다른 프레임의 정면 관측과 바닥 연결로 확인.
  문 이름·GT 좌표/방 구획을 제어에 전달하지 않는다. 자기 시작 좌표계·관측ID/시각을 보존한다.
- 원문 미명시 임계는 기존 own_gap_v1의 폭 .25–1.5m, 방향10°, 선거리 .15m,
  중복 중심거리 .25m를 사용한다. CP 접합 허용 .05m(기존 navigation 셀), 확인 정면10°,
  재관측 .05m 또는5°(기존), 문앞/뒤 .4m(기존 corridor), 로봇폭+.04m(기존 margin).
  확인 시점은 Xiang §4 Eq2의 문중심 법선1m 앞, 가까운 쪽·경로 가능한 곳을 선택.
  ray 자유 증거만으로 RGB 바닥을 봤다고 하지 않으며 **직접 floor 표본**이 양쪽에 있고,
  그 표본까지의 광선이 문 폭 안에서 연결됨을 요구한다. 현재 벽점이 통로를 막으면 확인 금지.
- 위상: 확인된 문을 cut한 관측 free 연결영역=지역 노드, 문=간선(Thrun).
  unknown은 방/간선 증거가 아니다. 미확인 문은 접근/정면관측 목표, 통과 간선으로 사용 금지.
  최종 B 목표는 보존하고 실패한 지역 waypoint만 blacklist한다. B→일반 frontier 전환은 별도 집계.
  360° sweep은 위치불확실(기존σ .15m)과 새 unknown 기대가 함께 있을 때만;
  그 외 목표방향 회전1회, 진행시간30s/충돌보호는 기존 그대로. 지도/운동 임계 변경0.
- 채점: raw 후보 발생 수, 공간 중복 병합 후 entity 수, 정면 확인 시점 기회 수,
  실제 확인 수; 후보/확인 P와 문 R. 거리 .25m·축10°·폭오차 .25m 이내 일대일 GT문 연관.
  중복 예측은 FP, 같은 문을 반복 보아 recall을 중복 계산하지 않는다.
  전체 GT문 분모와 관측 가능한 GT문 분모(양쪽 jamb가 같은 프레임 카메라FOV·4m·가림 안)를 모두 보고.
  평가 변환은 고정 출발 GT 변환만, 프레임별 GT 자세로 후보 위치를 고치지 않는다.
- **오프라인 관문(실행 전 고정):** egomap49 합계 후보P≥.50, 관측가능문R≥.50,
  확인문P≥.90·거짓확인0, 확인 TP≥1. 분모0은 미측정/실패. 6건 전부 표에 남긴다.
  개발에서도 같은 지표를 보고하되 설정 재튜닝0. fixed-pose replay는 새 시점 획득/실제 귀환 성공을 증명하지 못한다.
  옵션off 동일 bytes, topology/관측확인/mission보존 시험 통과도 필요.
- 관문 통과 때만 egomap49와 **동일 seed49001–49006 각1회** DEV, 탐색360s+귀환270s,
  B선언 resolved5프레임·추정거리≤.20m, GT차체중심 B안·거짓선언0을 egomap43 그대로.
  접촉·도착/6·귀환시간·회전시간비율·확인문P·B blacklist→frontier 횟수 보고.
  agent_lock/ugrp_session/dev_light, 한 번에 하나. 6회 예상3–6시간+잠금대기, 필요시 감독파일에 갱신.
  물리 이전엔 lock 불필요. ENOSPC=HOST_ERROR, 제외/재실행 없음. 실패 시 물리0·재튜닝0.
- 결과 raw `/Users/changmin/projects/ugrp/outputs/own-door-navigation-v1/`; 성공/실패4배속영상은
  실제 해당 결과가 있을 때만 만든다. offline overlay는 물리 성공 영상으로 표현하지 않는다.

## 참고 자료·원본 대비

1. [Xiang, Santos, Liu 2004, §2.1–2.2, §4.1 Eq2–4](https://www.scitepress.org/papers/2004/11358/11358.pdf),
   DOI 10.5220/0001135803700374. 원문 PDF를 내려받아 확인했다(web fetch403, 직접 다운로드 성공).
   연결 선분의 교점/가림 단절의 가까운 끝점(CP), Type I 두 CP와 Type II CP+수직선,
   폭·선방향·연장선 조건, 문중심 법선의 가까운 접근점을 채택한다.
   원문 레이저를 **동결 RGB 바닥투영 선분**으로 바꾸므로 CP는 가설이며 프레임 경계/먼 거리 끝점은 배제.
   원문의 open-loop 원호 접근 대신 기존 NavFn/RPP 충돌검사를 유지한다(메카넘·불확실 지도).
   후속 RGB 바닥 확인·시간 중복 병합은 좁은FOV/노이즈 제약의 명시적 추가, 원문에 있는 수치라고 주장하지 않는다.
2. [Thrun & Bücken 1996, Topological Maps §1–5](https://www.ri.cmu.edu/pub_files/pub1/thrun_sebastian_1996_8/thrun_sebastian_1996_8.pdf):
   free영역을 critical line으로 나눠 각 영역=노드/통로=간선으로 매핑한다.
   본 작업은 GVD 전체를 이식하지 않고 확인된 endpoint gap을 cut line으로 사용한다.
   아직 미관측 방을 임의 완성하거나 자기 지도 틈을 GT 문으로 대체하지 않는다.
3. [Bormann et al. 2016 공개 구현](https://github.com/ipa320/ipa_coverage_planning/blob/noetic_dev/ipa_room_segmentation/common/src/voronoi_segmentation.cpp),
   `segmentMap` L21–51: GVD→가지치기→거리극소→critical line→영역성장.
   완성 floor plan을 전제한 region segmentation이라 미관측이 많은 온라인 카메라 지도에 그대로 전체 적용하지 않는다.
   비교·구조 참고만, 코드를 복사하지 않음. package.xml은 LGPL academic/non-commercial, 상용은 IPA 문의로 명시한다. 새 의존성/venv 변경0.
4. 기존 탐색/회복·경로 원본은 egomap47 README 및 PR409에 pin된 NavFn/explore_lite/Nav2를 그대로 재사용.
   새 문 API는 자기 관측만, 다른 로봇 지도/배열 전송/모델호출0. 문 confidence는 확인 근거 점수이며 calibration된 확률 아님.

## 구현·오프라인 재생 경계 (개발 결과 열람 전)

`harness/own_door_memory.py`: `candidates`는 원문 §2 CP와 Type I/II, `floor_connection`은
직접 바닥 표본+광선/현재 벽의 확인 검증, `DoorMemory.observe`는 관측ID/시각·첫 기하 보존/중복 연관.
`harness/own_door_navigation.py`: `topology`/`door_route`는 cut→연결성→BFS,
`DoorNavigator.choose`는 Eq2 정면1m 접근/확인문 반대편 .4m 경유, `action_failed`는 최종 mission 보존.
`attach`/`attach_return` 두 옵션off는 받은 객체 자체 반환. 기존 receive에 명시적 opt-in hook만 추가했다.
GT/static 파일 import0, 로봇ID/프레임 중복 검사, loss 이전 own door snapshot 보존.
명시적 변경: range4m·FOV종단 CP배제·.05m 이하 선분 배제는 기존 카메라/격자 유효 범위;
CP 연결점은 .05m 격자 허용내 관측 끝점, 원문의 정확한 무잡음 교점 가정에 대한 수치 허용이다.

`code/offline.py predict`는 GT를 읽지 않고 저장 자기 자세/관측만 재생한 뒤 해시 봉인한다.
`score`는 별도 호출에서 출발 GT변환·실제 카메라·문으로만 평가한다. ray 가림은 벽만 모델링하므로
가시문 분모는 **잠재 가시성**이며 로봇/블록 가림 미모델링 한계를 함께 기록한다.
원래 graph 좌표 문 후보는 자기 map→odom 역변환만 적용한다. GT로 후보를 맞추지 않는다.
고정 경로에 없는 새로운 능동 확인 시점은 생성하지 않으며, 실제 회전 감소·귀환 도착은 미측정이다.
시험15개 통과(새 문10 + 기존 귀환5). NumPy 버전의 2D cross 제거는 스칼라 determinant로 대응,
수학/임계값 변경0. 기본off trace/입자/RNG 골든 byte 동일.

## 개발3건 완료 → 설정 동결 (egomap49 개봉 전)

|기록|프레임|off raw/병합|on raw/병합|on 후보TP·P|잠재 가시문R|정면 재관측 기회/개체|확인문|
|---|---:|---:|---:|---:|---:|---:|---:|
|46A|1791|9999/271|220/56|1 · 1.79%|1/1|49/11|0|
|46B|1791|27468/790|494/131|1 · 0.76%|1/2|38/12|0|
|47|1790|23767/815|625/166|1 · 0.60%|1/2|44/22|0|

세 개발 기록 모두 확인문0, 후보 정밀도 미달. 문턱/검출/연관 규칙은 변경하지 않는다.
개발 중 정책 단위검사에서 미확인 gap을 지나는 직접 B 경로가 확인을 건너뛰는 분기를 찾아,
그 gap의 정면 확인 시점을 우선하도록 수정했다. **검출·재생 결과에 영향0**, 추가 시험1개 포함16개 통과.
관문은 사전등록대로 egomap49 6건 합계에서 판정한다. 이6건도 과거에 관측한 DEV 자료이며 새 물리 확증이 아니다.
원본 후보와 비교 시 ID 재사용/pose drift로 멀어진 후보도 공간/축/폭 규칙으로 다시 병합했다.
동일 GT문을 가리키는 미병합 복제는 FP로 세므로 raw 검출 정밀도와 entity 정밀도를 혼동하지 않는다.
