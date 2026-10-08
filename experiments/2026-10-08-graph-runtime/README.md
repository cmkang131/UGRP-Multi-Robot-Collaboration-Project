# egomap48 — 최종 graph 오프라인 성능 (실행 전 등록)

2026-10-08 사용자 지시. 기준21582623, PR405 DRAFT. 물리·렌더·모델 호출0.
egomap47 seed47001의 봉인된 own frontend-ledger/poses로 마지막 graph를 계산한다.
원본 `/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1/new-seed`는 수정하지 않는다.
새 raw `/Users/changmin/projects/ugrp/outputs/graph-runtime-v1`; GT는 최종 계산 봉인 후 채점만.

순서: 문서/드라이버 커밋→배타 timing 잠금→기존 최종 graph cProfile1회(30분 상한 제거,
유한한204스캔 입력1회만)→상위 병목과 표준 원문 확인→기본off 옵션 구현·시험→고정 on/off 시간/동일성.
프로파일에는 후보수/정합/field 생성/최적화·LSMR/중복 계산과 노드·엣지·nfev를 기록한다.
이미 Jacobian sparsity+LSMR를 쓰므로 단순히 새 희소 solver를 추가했다고 주장하지 않는다.
결과 동일성 우선: 출력 전체 JSON 직렬화 SHA 비교, 지도·pose·constraint 최대차도 기록.
byte 동일 실패 시 pose≤1e-12·map log-odds≤1e-12/셀집합 완전 동일을 보조 수치 기준으로 보고하고
byte 동일이라 부르지 않는다. 이를 넘으면 가속 미채택. 정합/판정 문턱 변경0.

최종 graph는 egomap46 B와 별도 표: **덮음≥80% AND 영역P≥63.6%** 그대로,
R/RMSE·전체칸·관측영역 칸/벽표본 분모 포함. 새 실행/확증 아님, 동일 녹화 사후 계산.
egomap47 HOST_ERROR를 소급 완료로 바꾸지 않는다. 누락된 마지막 GT1개는 평가 제외를 명시.
360초 예상 wall/SIM은 측정 구간·외삽 가정과 graph/frame 중복 계산 차감을 명시한다.
프레임1.52배를 실제 물리 전체에 무조건 곱하지 않는다. raw 예산512MiB, ENOSPC=HOST_ERROR.
기존 가속도 포함하는 조건은 별도 표기. 새 의존성/venv0. 바뀐 모듈 시험만, 초록 후 커밋/push.
단계 사이 supervisor 확인, 잠금 점유 시 대기, 다른 프로세스/브랜치 수정0. TensorBoard 생략 유지.

## 프로파일·선택 (구현 후 동일성/시간 측정 전)

기준 cProfile1회 완료36.756초, 204 scans+21 submaps=225 pose 노드, 402제약(내부398+loop4).
정합3751회28.559초(77.7%, field 생성 포함), probability field3623회6.550초,
distance field64회0.150초. make_submaps1.811초, legacy/robust rebuild각0.893/0.906초.
legacy optimize0.084초/nfev6, switchable optimize0.169초/nfev12;
LSMR16호출 누적0.143초. 최종 graph 한 번이30분인 것이 아니라 전체실행30분 상한이 마지막 계산을 잘랐다.

선택 `graph_acceleration=match_cache_v1` 기본off:
- [Cartographer ConstraintBuilder2D](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/constraints/constraint_builder_2d.cc)
  151–171 `DispatchScanMatcherConstruction`은 submap matcher를 재사용한다.
- [PoseGraph2D](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/pose_graph_2d.cc)
  292–378은 새 node/완성 submap에 제약을 추가하고 기존 제약을 유지한다.
- [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)의
  jac_sparsity/LSMR는 이미 사용 중. solver·수렴 허용오차·초깃값은 변경하지 않는다.

우리 RBPF의 과거 lineage는 바뀔 수 있으므로 ID만 캐시하지 않는다: **submap grid/resolution/선분**,
**scan 선분/initial relative pose/모든 GraphOptions**의 정확한 내용이 같을 때만 정합 결과를 재사용한다.
해시/키 불일치는 재계산; 후보 필터·검색 범위·수락 기준 불변. submap별 occupied/확률/거리 field 재사용,
성공과 거부 모두 캐시, 반환 deep-copy, 로봇별 별도 인스턴스. LRU8192쌍/64fields는 메모리 상한이며
eviction은 재계산만 유발하고 결과는 바꾸지 않는다. 최적화 자체/field 외 그래프 재구축은 그대로.
원문 전략의 독립 Python 구현; 외부 코드 복사/새 solver/venv0. 기본off는 기존 분기로 동작.

동일성 검증은 최종 graph off/cold-on/repeat-warm-on 모두, warm은 같은 입력 재계산의 상한 이득으로만 표기.
기록된35회 graph 호출에서 반복 입력 수를 별도 감사해 warm 최선값을360초 전체 속도라고 주장하지 않는다.
