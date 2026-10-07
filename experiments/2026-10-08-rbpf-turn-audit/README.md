# egomap27 — 회전 오차 감사 / 기존 옵션 결합 (구현 전 사전 등록)

2026-10-08 사용자 요청. egomap23 동일 녹화 DEV 오프라인만, 물리·모델·잠금0.
기본 옵션/기존 결과 보존, 결과 후 문턱·모션 모델 변경0. TensorBoard 생략 유지.
raw `/Users/changmin/projects/ugrp/outputs/rbpf-turn-audit-v1/`, ENOSPC=HOST_ERROR.
단계 사이 supervisor 확인. GitHub500이면 로컬 커밋으로 진행하고 종료 시 정상 push 재시도.

## 수정 전 발견 / 대조

회전 구간은 같은 부호의 회전 명령이 연속된 묶음(중간 다른 명령이면 종료),
마지막 명령 이후 다음 명령 시각까지 tail 포함. 306회전 명령,96묶음.
모든 구간 DR/GT/추정 yaw 변화는 [turns.csv](results/turns.csv),
선택 입자의 **정합 전** yaw는 명령 DR 증분·저장 부모 인덱스로 복원했다.
GT는 이 평가와 이후 봉인 예측 채점에서만 사용한다.

- 35.7–39.9s: DR112.75° / GT124.98° / egomap26 추정108.77°.
  yaw 오차 −9.51→−25.72°. 37.3s에는 GT 방향까지 +19.71°가 필요했으나 low_overlap(.316),
  38.5s에는 +18.33°가 필요한데 overlap1/residual.079m로 잘못 수락했다.
  39.7s에는 +25.60° 필요, low_overlap(.333)/residual7.239m.
- 온라인 RBPF는 `self_map_rbpf.improved_proposal`의 **±8° coarse**, 최대3° fine 추가이나
  최적 오프셋이±8° 경계 이상이면 거부. 사용자 관찰의±15°는 `GraphOptions`의 후처리 loop 검색창이다.
  egomap26 그림은 frontend이므로 graph가 온라인 회전을 수정한 결과가 아니다.
- 전체52 정합 시도 중47개는 GT 방향이 명목±8° 밖. 그래도 이미 틀어진 자기 지도에 대한
  정합과 세계 GT 정렬은 같지 않다. 검색창 제외는 확인됐으나 확대만으로 해결되는지는 미확인이다.

## 결합의 명시적 의미 (새 옵션 기본 off)

기존 `gmapping_range_v1`과 `gmapping_selective_v1`은 map 삽입 의미가 상충하여 설치를 막았다.
전체 on 재생 기록은 없다. 사용자 요청에 따라 `rbpf_composition=insert_selective_v1`을 추가한다.
기존 standalone 옵션은 보존한다. 결합은 다음으로 고정한다.

1. motion gate1m/.5rad·4m·정착·positive depth·v122 명령 평균 그대로.
2. egomap24 공식 비율 모션 잡음, CSM 거부 시 **CSM 가중 갱신/재표본은 생략**.
   수락 시에만 기존 Neff<N/2 선택적 재표본. Manhattan likelihood는 기존처럼 별도 갱신.
3. 유효 scan은 거부돼도 각 입자의 sampled motion pose에서 삽입(egomap26 변경).
   즉 거부 시 map은 갱신하지만 CSM likelihood는 추가하지 않는다.
4. manhattan_v1의 초기 자기 축/분산/모드 처리 그대로. graph own_submap_v1 + switchable_v1을
   **실제로 finalize**한다. frontend 공분산과 graph 최적화 뒤 공분산을 혼동하지 않는다.

이 결합은 사용자 요청 정책이며 GMapping 원본의 거부 likelihood 갱신까지 동일하다는 뜻은 아니다.
표준 원문 확인과 차이는 [egomap26](../2026-10-08-rbpf-insertion/README.md),
[egomap24](../2026-10-07-rbpf-rejection/README.md),
[Manhattan](../2026-10-08-rbpf-manhattan/README.md),
[switchable](../2026-10-07-robust-wall-map/README.md) 그대로다.

## 검색창 비교 / 고정 판정

37.3s의 +19.71° 등 창 밖 증거가 있어 전체 on을 한 번 실행한 뒤, **같은 결합에서 검색창만**
`rbpf_search=correlative_20deg_v1`(기본off)로 한 번 비교한다. 추가 결과 기반 확대는 하지 않는다.
[Cartographer trajectory_builder_2d.lua L35–40](https://github.com/cartographer-project/cartographer/blob/master/configuration_files/trajectory_builder_2d.lua#L35-L40)의
real-time correlative 기본 각도 **±20°**를 그대로 택한다. 원본의
[후보 전체 탐색/평가 L77–137](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/scan_matching/real_time_correlative_scan_matcher_2d.cc#L77-L137)을 확인했다.
고정 SHA/파일 해시는 [sources.json](results/sources.json). Apache2.0, C++ 복사/새 의존성0.

기존 Olson식 coarse→fine 후보 검색·RBPF Gaussian proposal/importance 계산을 재사용하고
coarse각도 범위와 boundary 판정만8→20°로 확장한다(간격2° coarse/최대1° fine 그대로).
RBPF의 확률적 proposal을 보존하기 위해 Cartographer의 occupancy 점수·Ceres로 교체하지 않는다.
따라서 Cartographer 전체 구현 이식이 아니라 원본의 각도창/후보 열거 규칙을 적용하는 비교다.
XY창±.5m, 모든 정합 수락 문턱, graph±15°, seed 고정. GT로 후보/입자/설정을 선택하지 않는다.

먼저 기존 egomap26 on의 off bytes 회귀. 전체 on1회 → 각도창 확장1회, 모두 예측 봉인 후 GT 평가.
결합 software 관문: 유효55scan 삽입, 거부 CSM weight/resample0, Neff 조건 유지, 옵션off bytes 동일.
성능 관문은 기존 **종료 e≤2σXY AND 영역 P가 egomap26 on보다 개선**을 그대로 사용한다.
graph covariance가 없으므로 이 관문은 frontend에서 판정; graph P/R/경로/종료오차는 별도 행,
graph e/σ는 N/A. 물리는 관문과 관계없이0. 실패 시 추가 튜닝 없이 기록한다.

반드시 같이 보고: 종료오차/σ/eσ, yaw 추이, 영역 P/R 분자분모, 전체 덮임, 점유셀/삽입수,
취득7.379m·2.313m²·가시137/329벽 표본·891자세. 결과가 작은 표본인지도 그대로 보인다.
