# egomem2 — 관측 밖 대상 보존과 일대일 연관

진행 중. PR574·codex/egomem1의 ada1e3f60에서 계속한다. 최신 main
AGENTS.md와 current_stack.json을 fetch 후 대조했으며 둘 다 동일했다.
ROVIO 원본 FeatureStatistics 재사용과 상대 예측→RGB EKF 갱신 선택은 유지한다.
기본 off `rovio_object_gnn_v1`은 관측 밖 물체/지형지물의 보존과 연관만 바꾼다.
정적 지도·spawn·TOP·평가 정답을 제어에 전달하지 않는다.

## 수정 전 원본 분해

gcp5 CPU, 소스6f9e1d7a3. 같은2026프레임·동일 allowed.json SHA.
[전체 시간대별 표](prior-rejection_table.json), 원본 행은
`/home/ugrp/ugrp-sim/ops-reviews/egomem2/prior-diagnosis/missing-rows.json`.

| 제외 사유 | 기존 분모14912에서 개수 | 확인한 원인 |
|---|---:|---|
| candidate_memory_absent | 8488 | 마지막 같은 평가 라벨 삭제가 품질삭제6648·슬롯확보삭제1840 |
| duplicate_label_memory | 5198 | baseline만2510·양쪽2688·candidate만0 |
| 짝지어 유일 | 1226 | 기존 비교가 사용한 표본 |

동일 프레임 신규 기억 중 같은 평가 라벨 중복초과21개도 있었다.
생성 보류 목록은 그 프레임에 새로 만든 기억과 다시 비교하지 않았다.
평가 라벨은 nearest same-appearance 지형이므로 동일 라벨=동일 실제 물체를
보장하지 않는다. 위 삭제별 수는 각 누락 키 이전의 마지막 삭제 사유이며
개별 물체 정답 원인으로 단정하지 않는다. 두 검출기가 한 번도 보지 못한
대상은 baseline-present 분모에 없으므로 첫 검출 실패 수는 이 표에서 식별 불가다.

## 실사용 공개 구현 조사와 적용

SURVEY를 공용 ops-alert에 기록한 뒤 구현했다. 원문 URL·SHA는
[survey-sources.json](survey-sources.json)에 있다. 상용 제품 채택은 확인하지 않았다.

| 구현/사용처 | 확인한 동작/라이선스 | 선택 |
|---|---|---|
| [ROVIO 고정 원본](https://github.com/ethz-asl/rovio/tree/34735c0bfd786d44f6d21d31c0776290f1f91185), ETH VIO·ROVIOLI | 원본 FeatureStatistics C++·BSD-3-Clause, UNKNOWN도 가시성 감소로 삭제 가능 | 상대 예측·원본 품질통계 직접 호출 유지, 물체 기억 삭제 근거로는 사용 안 함 |
| [MRPT2.14.7 CRangeBearingKFSLAM2D](https://github.com/MRPT/mrpt/blob/2.14.7/libs/slam/src/slam/CRangeBearingKFSLAM2D.cpp), 공개 실제 range-bearing SLAM 구현 | 상태의 랜드마크는 관측 밖에서도 남으며 재관측 연관; BSD-3-Clause | 이 영속 물체 상태 구분을 적용. 전역 로봇 자세는 가져오지 않음 |
| [MRPT NN/JCBB](https://github.com/MRPT/mrpt/blob/2.14.7/libs/slam/src/slam/data_association.cpp) | full covariance·chi2 .99·일대일 NN/JCBB | 관측별 서로 다른 RGB 공분산을 API가 따로 받지 않아 미채택. 무제한 JCBB 탐색도 넣지 않음 |
| [Stone Soup1.7 GNNWith2DAssignment](https://github.com/dstl/Stone-Soup/blob/v1.7/stonesoup/dataassociator/neighbour.py), Dstl 공개 [실제 영상 추적 예제](https://github.com/dstl/Stone-Soup/blob/v1.7/docs/demos/Video_Processing.py) | 관문 안 가설과 missed 가설의 비용행렬→SciPy 전역 일대일 배정, MIT | 설치 라이브러리를 직접 호출. 새 연관 알고리즘을 재작성하지 않음 |
| [CubeSLAM](https://github.com/shichaoy/cube_slam), 저자 공개 단안 객체 SLAM | 객체를 랜드마크로 유지하는 사용 예를 README에서 확인 | 객체 검출 모델·전역 SLAM 의존. 코드/라이선스 세부 미검토로 미채택 |

우리 제약 때문에 바꾼 것: Stone Soup의 motion predictor 대신 기존 ROVIO식
자기 중심 예측 상태를 넣고, 자체 Hypothesiser가 기존 점/선의 innovation과
공분산을 전달한다. 선 각도는 wrap한다. 물체 삭제는 시야 밖/UNKNOWN만으로
하지 않는다. 기존32슬롯 자원 예산이 차면 기존 LRU를 쓰고 사유를 기록한다.
이것은 전체 MRPT/Stone Soup tracker나 ROVIO VIO 성능을 승계한 것이 아니다.
같은 프레임의 미배정 관측이 이미 배정된 대상과 관문 안이면 중복투표로
기록하며 새 기억을 만들지 않는다. 같은 프레임 신규 기억과도 같은 기존
관문으로 비교하여 이중 생성·이중 EKF 투표를 막는다. 서로 다른 기억을
평가 라벨로 합치지 않는다. 재관측 안 된 정보의 불확실성은 이동과 함께 커진다.

상수: chi-square(2)99%=9.21034037·RGB 공분산·32슬롯·6m 센서범위는
기존 후보 그대로다. GNN missed 비용은 기존 관문값이다. 추가 거리/나이
문턱은 없다. 검사 수는 최대32×그 프레임 RGB 관측 수, 새 후보는 켜며 wall
상한은 없다. 슬롯 예산은 물리 수용 기준이 아니다.

## 기존 물리 실패 검토와 새 시험

직접 본 egomem1 녹화1: 전체0–38SIM초2Hz, 28–37.9초10Hz 프레임 띠.
0–25초 실제 둘러보기 뒤25.5초부터 내부 파란 표면이 카메라 대부분을 차지하고
물체/무늬가 점차 커진다. r2는 정지. 파란 표시가 남는데 경계 검출만 빠지는
것을 시야 이탈로 간주한 판정이 잘못됐다. 성공 예시는 기존 두 녹화에 없다.
이전 수정의 `--strict-reacquisition`(외향 법선·실제 색 성분 소실 필수)을 새
물리 시험에서 켠다. 이 분기는 이전 녹화2가 감독 중단돼 완주 검증되지 않았다.
새 승인 예산은 최대2녹화이며 이전 예산과 별도다. 새 물리의 성공 여부는
원본10Hz RGB·이동/동일 구역 평가를 재계수한 뒤 기록한다. dev_light,
MJWarp/native0, 시작 사전 없음. LLM/학생/운반 성공과 구분한다.

분석/시뮬/영상 제작은 gcp5만 사용한다. Mac에는 요약·몽타주·실패 프레임과
≤8MB 대표 영상만 회수한다. 예상 추가 원본≤2GiB(2녹화·오프라인 JSON·해시),
DEV 원본은 PR574 열린 동안 보존. gcp5 시작 당시 여유20GiB로8GiB 바닥 위다.
MRPT 의존성 설치는 조회만 했고 실제 선택 라이브러리는 기존 venv의
stonesoup==1.7이다. 모델 키/에이전트 자격 증명은 전송하지 않는다.

새 물리는 `--translated-return`도 켠다(기본 off). 돌아보기만 한 재검출을
복귀로 보고하지 않으며, 기존 로봇 외피 지름만큼 자기 이동으로 돌아간 뒤
재검출을 받아들인다. 정답 이동 거리는 종료 뒤 별도로 확인한다.
비물리 검사21개(gcp5 CPU,2.39초) 통과: 기존/ROVIO 회귀 포함.

## 같은 원본2026프레임 오프라인 결과

실행48411d133. 원본 보존·동일 allowed payload를 hardlink하여 사용했다.
Symlink 압축파일을 zstd가 거부한 준비 실패1회, CLI 후보 누락1회와
대기열 전달 전 검사 실패1회를 보존했다. 모두 예측/물리 시작 전 종료였다.
성공 실행 경로는 `/home/ugrp/ugrp-sim/ops-reviews/egomem2/offline-object-gnn-r4`.
준비 실패 번호를 새 물리 녹화로 세지 않는다.

| 고정 baseline 키14912 | ROVIO 기존 | 새 물체 기억 |
|---|---:|---:|
| 기억 있음 | 6424/14912 | 14702/14912 (98.59%) |
| 양쪽 유일한 키 | 1226/14912 | 4202/14912 |
| 기억 없음 | 8488 | 210(모두 LRU 슬롯 교체 뒤) |
| 현재 전체 기억 생성 | 96(기존 기록) | 50 |
| 같은 프레임 같은 평가 라벨 신규 중복 초과 | 21 | 5(평가 라벨 정확성 한계 있음) |

[분모 고정 비교](operations/fixed-denominator-comparison.json)는 중복을 버리지 않고
각 키에서 **age_s 최소→생성 ID 순**으로 양쪽에 똑같이 대표를 고른다.
오차가 작은 기억이나 정답에 가까운 기억을 고르지 않는다. 누락도 전체분모의
무한오차 질량으로 남겨 전체분모P95와 조건부P95를 별도로 쓴다.

| 지표 | baseline | 새 후보 |
|---|---:|---:|
| 선 전체분모10790의 P95 | 4.235m | 4.713m(있음10580) |
| 점 전체분모4122의 P95 | 1.829m | 1.918m(있음4122) |
| 같은10580선 키 조건부 median/P95 | .601/4.152m | .476/4.121m |

**정확도 NOT_READY.** 커버리지가 회복돼 과거의 낮은 조건부 오차와 직접
같이 해석할 수 없다. 선 P95는 전체분모에서 개선되지 않았다. 평가 라벨
중복키는 여전히10320개며 baseline도 그10320개에 중복을 갖는다.
같은 프레임 신규 기억 중 같은 라벨 중복도5개 남았다. 새 연관은 같은
물체임을 정답 없이 보장하지 못하며, 검출/운동 공분산·태생 라벨 오류가
남은 원인일 수 있으나 이번 수치만으로 원인 비율을 단정하지 않는다.
[변경 뒤 분해](post-rejection_table.json), [관측446개의 순차 관문](operations/offline-memory-funnel.json):
446→446→426→417→417, 재관측367·생성50, 재관측 오차감소212/367.
관측 밖 ROVIO 통계 낮음4014건은 보존했고, 자원 LRU교체18건을 모두 기록했다.

평가 보강 `scripts/egomem2_return_audit.py`(5f16b824d)는 제어기에 import하지
않으며 녹화 중인48411d133 소스를 바꾸지 않는다. 종료 뒤 원본 SHA 전체와
첫 복귀 전진 명령 직전→종료의 정답 XY 순변위를 확인한다. 기존 로봇 지름
이상이어야 실제 복귀 이동 관문을 통과한다. 이전 녹화1은776개 SHA 일치,
색 소실0·실제 복귀 순변위0m로 다시 NOT_READY였다. 최초 약한 평가에는
색 소실 필드가 없어 새 엄격 평가를 별도 경로에 만든 뒤 재계수했다.

추가 [기존과 같은 유일 표본 비교](operations/unique-only-additional.json)는
4202/14912개다: 선2606개 median1.78184→1.78174m·P95 5.14751→5.13079m,
모서리1596개 median.67273→.65581m·P95 1.59759→1.90929m. 이 진단은
부가 자료이며 누락·중복을 제외한 수치를 전체 성능으로 쓰지 않는다.
