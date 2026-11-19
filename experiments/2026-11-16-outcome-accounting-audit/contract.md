## 성공 조건과 검증 범위

이 감사의 기준은 `main`의 커밋 `ca954d9fa64f94303a3f645c265aff85e2af2fce`다. 현재 연구 설계와 저장소에 남은 과거 실행 경로를 구분한다. [문서 우선순위]에 따르면 README·작업 계획·연구 설계가 현재 기준이며, 날짜별 실험과 그 밖의 문서는 해당 시점의 기록이다.

### 현재 연구에서 무엇을 성공으로 보나

2026-11-15 작업 계획의 주 지표는 **계획 덮기**다. 로봇들의 마지막 선택이 팀 주문을 모두 덮었는지 평가한다. **물리 성공은 맞는 목적지 표식 앞에 상자를 놓았는지**이며 보조 지표다. 계획은 맞았지만 동작이 실패한 실행은 별도로 센다. 따라서 계획 성공, 물리 성공, 둘 모두의 성공을 하나의 `success`로 합쳐 보고하면 어떤 층의 성능을 측정했는지 알 수 없다. 근거: [최신 지표 정의].

| 구분 | 문서가 정의하거나 확인했다고 보고한 범위 | 그 결과만으로 입증되지 않는 것 |
|---|---|---|
| 무하물 이동 | 문 통과와 구역 도착 | 적재 운반, 주문 충족, 협업 |
| Solo 집기·내려놓기 | 집어서 3초 이상 안정적으로 들고, 떨어뜨리지 않고 같은 자리에 내려놓기 | 든 채 이동, 목적지 배달, 다로봇 협업 |
| 현재 물리 운반 | 맞는 표식 앞에 놓기 | 팀 주문을 충족하는 계획, 통신의 효과 |
| 현재 계획 덮기 | 마지막 선택들이 팀 주문을 모두 덮음 | 물리 동작의 완주 |
| 동일 물체 공동 운반 | 두 로봇이 한 물체를 맞잡아 옮기는 과거 Pair 과제 | 현재 연구의 성공 조건으로 승계할 수 없음 |

[Solo 보고 범위]의 **개발 19/20, 평가 12/12는 본 감사에서 원본을 독립 재계수하지 않았다.** 해당 문서는 이 수치에 든 채 이동·목적지 배달·실물 실행이 포함되지 않는다고 명시한다. [집기 끝 전환]은 자기 발행 명령이 든 자세에 머물렀는지 보는 단계 전환 규칙이다. 명령 완료를 실제 들림이나 운반 성공의 증거로 사용할 수 없다. [무하물·통신 과제] 역시 주행과 메시지 왕복 검증을 적재 운반·협업 성공과 구분한다.

현재의 협업은 정보 공유, 작업 분담, 목적지 선택, 통과 순서의 조정이다. **같은 물체를 두 로봇이 함께 드는 Pair는 연구에서 제외됐다.** 따라서 과거 Pair 판정기를 검사한 결과는 그 실행 경로의 검증 결과로 표시한다. 동시에 여러 로봇이 움직였다는 사실이나 물체가 이동했다는 사실만으로 자연어 협상의 효과가 검증되는 것도 아니다. 근거: [현재 연구 범위].

### 실패·중단·제외·반복의 분모

현재 계획은 11/20 동결 때 온도·반복 횟수·주 검정·제외 규칙을 사전에 기록하도록 정했다. 동결 뒤 실행 실패는 그대로 센다. 본 비교는 장면 단위이며 같은 장면의 반복을 독립 표본으로 부풀리지 않는다. 근거: [동결 규칙], [실행 횟수], [분석 규칙].

| 구분 | 현재 계획의 처리 |
|---|---|
| 계획이 맞고 동작은 실패 | 계획·물리 성패를 따로 기록 |
| 실패와 제외 | 전체 몇 번 중 몇 번인지, 제외 건수와 이유를 함께 공개 |
| 정답 계획 기준선 | 본 비교 장면 전부의 60회가 실행 실패율의 분모 |
| 반복 실행 | 설계 40장면 × 세 구조 × 2회; 분석 단위는 장면 |
| 무작위 20장면 | 설계 장면과 합쳐 검정하지 않음 |
| 개발에 사용한 장면 | X01·L01·C01·D01·X02를 주 분석에서 제외 |
| 코드·입력 조건 변경 | 이전 버전의 결과와 합산하지 않음 |

과거 집계기를 검토할 때는 그 경로의 계약을 사용한다. [구형 zone 지표]는 `sim_horizon`, `budget_exhausted`, `deadlock`, `aborted`, `api_failure`, `policy_failure`, `orders_incomplete`를 성공률·배송률의 분모에 남기도록 정한다. 성공은 `orders_complete`, 정상 배송은 물건당 한 번 집계하는 계약이다. [v72 실패 규칙]은 첫 모델 요청 전 `HOST_ERROR`만 한 번 재시도하도록 제한하고, 전체 시도·인프라 오류·제외 후 시행 수와 전체 시도를 포함한 PAR-2를 함께 보고하도록 정한다. [구형 carry 코호트]는 다른 구성요소 때문에 운반이 중단되어도 전체 작업 실패는 유지하되, 운반 모델의 조건부 지표에서는 중도 중단으로 구분한다. 이 서로 다른 분모를 표시 없이 합칠 수 없다.

### 검증 차단: 최신 런타임과 완결된 판정 규약 미공개

[현재 코드 공개 범위]는 든 채 이동, 여러 로봇 실행, 계획기 연결, 천장 카메라 코드가 아직 저장소에 없다고 명시한다. 공개된 Solo 묶음도 같은 이름의 옛 `harness/`·`scripts/` 파일과 구분하라고 안내한다. 따라서 **최신 런타임의 성공 판정과 전체 집계는 이번 감사에서 검증하지 못했다.** 구형 코드의 재현 가능한 오류가 곧 최신 실험의 성공률 오류라는 뜻은 아니다.

이는 확인된 오판정과 구분하는 **검증 차단 항목**이다. 최신 평가 코드와 함께 주문 수량·중복 선택·주문 외 운반 처리, 표식 도착 허용 범위와 실제 놓기 확인, 종료 기록 누락, 시행 중단·재시도의 ID와 분모 규칙을 공개해야 한다. 실행 예정 목록과 모든 attempt의 종료 상태·제외 사유가 있어야 파일이 남은 실행만으로 계산한 비율인지 검사할 수 있다. 현재 계획이 11/20 사전 동결을 예정하고 있으므로, 아직 정하지 않은 규칙을 감사자가 임의로 정해 기존 결과를 재판정하지 않았다.

[문서 우선순위]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/README.md#L7-L11
[최신 지표 정의]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/plan.md#L75-L82
[Solo 보고 범위]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/solo_pipeline/README.md#L44-L48
[집기 끝 전환]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/solo_architecture.md#L57-L58
[무하물·통신 과제]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/sim2real/03_pipeline.md#L22-L26
[현재 연구 범위]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/README.md#L12-L18
[동결 규칙]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/plan.md#L34-L41
[실행 횟수]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/plan.md#L58-L73
[분석 규칙]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/plan.md#L75-L94
[구형 zone 지표]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/zone_study_metrics.md#L129-L173
[v72 실패 규칙]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/zone_study_llm_failure_rules.md#L8-L54
[구형 carry 코호트]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/research_controller_validation.md#L21-L26
[현재 코드 공개 범위]: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/ca954d9fa64f94303a3f645c265aff85e2af2fce/docs/architecture.md#L113-L118
