# egomap42 — 인과적 지도 snapshot + S2 색 구역·문 랜드마크

## 누설 정정 및 실행 전 조건 등록

2026-10-08 감독 요청. egomap41 최종179.8초/64스캔 지도에는 재위치 구간의 미래
관측이 들어갔다. 60초 조건의 B 목표도 미래72.1초 관측이었다. 기존 비교는 **누설로
무효**이며 그대로 보존·병기한다. 종료 yaw 우위를 자기 지도의 장점으로 해석하지 않는다.
이번 수정은 판정 완화가 아니라 입력의 인과성 수정이다. 검출기·지도 구성은 egomap34 고정.

- 녹화: `/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed`, seed32002.
  잃는 시점 경과60/90/120초(절대61.3/91.3/121.3), RNG41001/41002/41003 그대로.
- **자기 지도:** `online-maps.jsonl` 중 t보다 엄격히 이른 마지막 행의 grid와 ledger.
  당시 저장된 상태를 그대로 사용한다. 최종 grid/graph를 잘라 재구성하지 않는다.
  선택 시점59.5/84.1/119.1초, 각각27/34/38스캔·747/1227/1763관측칸이다.
- 자기 랜드마크: t 이전 자기 RGB의 S2 검출만 당시 자기 추정 pose로 변환해 기억한다.
  관측 ID/시각/당시 pose를 보존하며 미래 최적화·GT 정렬·정적 영역/문 위치는 사용하지 않는다.
  부분 색 경계만 기억하며 보지 않은 전체 사각형·구역 중심으로 확장하지 않는다.
  동일 색 관측은 모두 가능한 대응이며 원본 최대우도 대응을 사용한다(새 지도 병합/튜닝0).
- 정적 조건: 기존 authored static grid, 정적 region 경계·passage 중심/폭 사용.
  두 조건의 검출 색 vocabulary는 원본 S2 지도의 고정 색상 명세만 공유한다.
  색 signature는 사전 지식이며 자기 조건에는 지도 좌표·구역 식별 정답을 주지 않는다.
- 재위치 입력은 **t보다 엄격히 뒤**의 실제 own RGB/명령만. 경계1e-8초 이내 행은
  양쪽에서 제외한다. 초기 위치/방향은 각 고정 지도 free 전체 균등, GT·저장현재pose prior0.
- 목표 정의도 egomap41 그대로: t 이전 floor_color_v3에서 처음 locally_confirmed_region인
  B 후보와 관측 ID. 60초 조건은 목표 미관측으로 별도 집계(미래 관측으로 채우지 않음).
  정적 기준선은 같은 B의 정적 중심. 카운트 분모3은 유지하며 미관측을 빼 유리하게 만들지 않는다.

### 조건 및 고정 판정

새 조건은 causal own/static × `sensor_landmarks=off|floor_zones_doors_v1` ×3시점,
**총12회**를 각각1회만 예측·봉인 후 별도 GT 채점한다. causal off는 누설 수정 효과와
랜드마크 효과를 분리하는 대조군이다. 기존 egomap41 no-landmark6회는 누설 표시로 병기한다.
모션·KLD·관문·seed·벽 접점은 이전 그대로이며 floor/door 독립 관측은 벽0점이어도
원본 S2처럼 측정 패킷이 된다. 랜드마크 옵션 기본off, off bytes/RNG 동일을 시험한다.

**[egomap41 판정](../2026-10-08-own-map-utility/README.md#판정결과-전-고정)을 변경 없이 재사용:**
내부 resolved 연속5 RGB + 평가 XY≤.25m/yaw≤10°; 정적 수렴≥2/3;
자기 수렴 수 열세 없음·공통 수렴 존재·공통 중앙 XY오차/시간 각각 정적≤2배·거짓수렴0.
목표≤.20m 내부 선언, 실제 B 내부 여부는 평가만; 정적 올바른 선언≥1/3,
자기 올바른 선언 열세 없음/거짓0, 자기 최초수렴 경로의 정답기하 충돌0.
물리 제안 관문은 위 모두 만족. 고정 녹화에서는 새 경로 실제 도달률은 **미검증**이다.
결과 후 문턱·옵션·seed 변경0. offline12회는 한 녹화의 중첩 구간이며 독립 확증 아님.

지도별 점유/free칸·면적·스캔/랜드마크 관측 수, 후속RGB·벽/랜드마크 표본 수,
수렴/오차/시간/σ/거짓선언·미관측 목표를 기록한다. 기존 egomap34 전체지도 품질을
부분 snapshot의 품질로 승계하지 않는다. snapshot 벽 coverage는 GT 평가에서 별도 산출한다.

### 원본 재사용 및 경계

PR406 `codex/s2-realism` **6a9e93f1a463ed2e356b044487c6b025ad018b63**의
`harness/zone_solo_cyan_landmarks.py`: HSV/연결성/Hough/양면지지 바닥경계,
양쪽 jamb·거리 discontinuity 문, Gaussian 거리/방위/폭·색상별 최대우도 대응,
5% random component를 수치/함수 그대로 복사한다. 벽우도×랜드마크우도 결합도 동일.
원본 S2가 인용하는 Probabilistic Robotics §6.6/Table6.4, §7.5를 계승한다.
`zone_solo_cyan_visibility.py`의 명령기구학 자기그림자·RGB cyan 마스크를 재사용한다.
새 의존성/venv0, #406 파일 변경0. 정확한 복사 행·해시는 구현 provenance에 남긴다.

필수 어댑터 차이: S2 Runtime 대신 egomap34의 명령 SEARCH FK(강성on) 카메라와
동결 벽 접점/녹화 ABI를 공급한다. 자기 지도에는 관측한 부분선분/문만 제공한다.
정적 전체 영역과 자기 부분 관측의 정보량 차이를 보존한다. 원본 landmark 검출·우도
문턱을 바꾸지 않으며, S2 전체 능동 관측/운반 Runtime을 이식했다고 주장하지 않는다.

## 보존·실행 경계

출력 `/Users/changmin/projects/ugrp/outputs/own-map-causal-landmarks-v1`.
물리·렌더·모델·잠금0. 예측은 GT 파일/실시간 상태 읽기0, 평가만 출발 GT 변환 사용.
F 구현은 유지, 상대 배열 전송/merge0. 새 출력만 추가, 원본/과거실패 보존.
ENOSPC=HOST_ERROR. 바뀐 모듈 시험만, 초록 후 커밋·push, PR405 DRAFT/병합0.
단계 사이 SUPERVISOR 확인. TensorBoard 생략 유지. push 오류는 로컬 진행 후 재시도.
