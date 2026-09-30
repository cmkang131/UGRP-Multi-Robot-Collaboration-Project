# v6h 분류기 후속 검토 반영 (초안 v2)

`../PREREG_DRAFT.md` §4–5.1과 같은 정의다. 실제 봉인·확증 승인 파일은 만들지 않았다. 과거 탐색 모드는 끝점과 저장 안전 기록의 공개 집계를 보존하고 어떤 60개 입력도 확증 PASS로 출력하지 않는다. 봉인 파일과 독립 고정 해시를 받은 확증 모드의 입력 계약은 [SEALED_INPUT.md](SEALED_INPUT.md)에 있다. 6·7은 이전 OPEN을 대체하는 **구현된 초안 정의**이며 독립 검토·봉인 승인과 다르다.

| 순서 | 현재 초안 정의 |
|---|---|
| 1 접촉 창 | 닫힌 구간이 조금이라도 겹치면 포함, 경계 오차 1e-9 s |
| 2 중단 leg | start→첫 carry 실패 시각, 없으면 stop→trace 끝 순, 출처 표시 |
| 3 예방 가드 | 실제 접촉 없는 가드 정지는 FAIL; 실패 carry 창에 접촉이 있으면 BLOCKED |
| 4 leg 밖 접촉 | 저장 기록에 접촉이 있으면 기존 PASS_CONTACT_RECOVERED 식별자 유지. 표기는 **접촉 동반 끝점 통과**이며 실제 접촉 복구/종료를 주장하지 않음 |
| 5 leg 밖 실패 | 내려놓기·재파지 실패도 통과를 막음. carry 창 밖 접촉만 있으면 FAIL, 하드 위반은 우선 |
| 6 handover | 확증에서 L0 끝→L1 시작의 바닥≤5 mm/기울기≤3°/네 집게 개방 표본 및 L1 시작 전≤0.051 s 들림≥3 cm/네 집게 접촉 표본 요구, teacher restaging 금지. 목적지 setdown은 시험 밖 |
| 7 전체 창 | teacher 준비 포함 전체 수집→실제 종료 정리, 엄격한 시간 순서/≤0.051 s 공백/행 수/접촉 추적 범위. 완료 L1은 첫 wait_lower stage stop. 실제 실패·timeout은 PASS 거부, 의도된 종료의 wrapper category는 실제 timeout과 구별 |
| 8 주 시드 | A·B는 941, 앞 12곳의 943은 별도. 탐색 대조 911/strict/any는 각각 보고 |
| 9 보조 안전 | 선택 72건과 대체된 HOST_ERROR 원본을 포함한 모든 실행 시도에 하드 위반 0 필요, 주 시드 분자는 별도 유지 |
| 10 누락·재시도 | 누락은 NOT_EVALUABLE/오류, FAIL로 억지 변환하지 않음. 봉인에서 미리 정한 같은 설정·시드 HOST_ERROR 재시도 최대 1회, 원본/대체 연결·단일 선택. null 실패 값은 실패 없음 |
| 11 주 판정 | 봉인된 C01…C60×941+C01…C12×943 및 배치/prior/계획/소스/정책/번들 해시 일치 후 A≥48/60+안전, B는 941 두 로봇×두 leg의 6축 검사 AND. 도달 후 PF 누락은 B NOT_EVALUABLE, 미도달은 별도. 최대 나이 .30 s, 동일 배치·로봇 가중 |

하드 문턱(기울기>15°, 관통>5 mm), leg 검사·접촉 겹침·Wilson은 기존 `chain_analysis.py`/`pair_chain_probe.py`를 재사용한다. 일반 leg 끝점 기울기 한계는 여전히 10°이므로, 끝점 15°는 하드 위반은 아니지만 일반 FAIL이다. 모든 도달 leg의 필수 유한값과 r1/r2×2 bool 집게를 먼저 확인하므로 빈 dict/inf는 PASS가 아니다. 잘린 trace나 전체 접촉 추적 범위 누락도 거부한다. 기존 러너가 새 metadata를 제공한다고 주장하지 않는다.

[재검증 기록](review_validation_20260930/)은 **기존 raw 읽기 전용 대조**다. 16개 코호트 308건의 공개 케이스/strict 배치/L0/L1 통과 수와 부분 tX1 12/14를 확인한다. 원본 결과·배치·기존 수치 산출물은 보존한다. 재현:

```sh
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py --output /tmp/v6h-review-NEW
```

현재 배치 추출은 이전 확증 추첨과 근접한 후보도 버려 **독립 동일분포가 아니다**. Wilson/이항은 명목 구간·설계 민감도, p=.88은 검증되지 않은 설계 가정이다. 새 [수치 출력](sizing_review_20260930/COHORT_SIZING.md)에 MC 성공/실패 draw·모형 내부 구간을 추가하고 과거 출력은 보존했다.

새 물리 실험·모델 호출·봉인·등록·병합은 없다. 기존 결과 TensorBoard 키 `b_v6h_gain_20260930`, `door_relax_envelope_20260930`, `b_v6h_axial_lag_20260930`를 보존하며 이 읽기 전용 대조에서 변환·서버·브라우저 표시를 다시 검증하지 않았다.

## #299 독립 검토 항목별 응답

검토 대상 `c86d9bac62036904ecc641db5e59e79edb58dec2`, 리뷰/독립 시험 출처 `de16cbc96becf19755f09197b9ef139609f00fe9` (`codex/review-299`). 이전 검증 기록은 보존한다.

- **R1 끝점 위반 누락:** trace·L0/L1 및 추가 leg 끝점·chain setdown 관측·저장 GT(teacher 준비, 로봇별 leg 시작/끝/done, stage exit/stop, 실제 종료)와 저장 최대값의 합집합을 사용한다. trace 사이 끝점 16°는 `FAIL_HARD_LIMIT`; 정확히 15°/5 mm는 기존 경계를 유지한다. 이미 하드 위반이면 완료 성공에 필요한 handover/첫 wait_lower 검사로 이를 일반 실패나 미평가로 낮추지 않는다. 데이터 형식/범위 검사는 유지한다.
- **R2 HOST_ERROR 원본 위반 소실:** 선택 판정 입력과 실행 시도 목록을 분리했다. 성공률/σ는 허용된 대체 한 건만 세고, 안전은 원본·재시도·주/보조 시드 전부 검사한다. 원 HOST_ERROR의 class는 미분류이며 별도 안전 위반 ID·최대값·파일 해시·배치 안전 거부를 보존한다. 원본과 재시도 모두 위반하면 위반 시도 2건, 위반 배치 1곳이다. 부분 trace의 유효 관측도 남기고, 알려진 위반은 B가 미평가여도 전체 `FAIL_A_B_SAFETY`다.
- **HOST_ERROR 규칙 해석:** `PREREG_DRAFT.md` §4·§5.1(10–11)·§8과 `REGISTRATION_PLAN.md`를 확인했다. 재시도는 중복 분모 방지이며 안전 면제는 명시돼 있지 않다. 기존 전체 안전 거부와 이번 사용자 지시에 따라 보수적으로 모든 관측 위반을 유지하고, 같은 해석을 두 문서와 `SEALED_INPUT.md`에 명시했다. 새 protocol 필드도 실제 봉인 전에 고정해야 한다. 없는 HOST_ERROR 파일은 부재를 표시하되 허용 재시도를 막지 않는다. 저장 파일이 손상되고 알려진 위반도 없으면 `NOT_EVALUABLE`이다.
- **독립 시험/분모/308건 보존:** 리뷰어 파일을 복사해 두 xfail 장식자를 제거했다(기존 33개 시험의 assertion/독립 fixture 보존). offline CI 목록에도 등록했다. 60곳 분모, 47/48 경계, 양 시드, 정상 재시도·미대체 HOST_ERROR, 공개 308건 및 부분 tX1은 새 검증 기록으로 대조한다.
- **구 코드 17개 실패의 뜻:** 17개는 실제 assertion/입력 검증 회귀이며 서로 다른 false PASS 17개라는 뜻은 아니다. 구 코드의 181°/NaN leg error는 일반 FAIL이었고 새 검사는 `EvidenceError`를 요구한다. null 사례도 정상 assertion 뒤 non-null 실패를 거부하지 못한 것이며, 이전 중단 patch의 cA 0/24 문제와 구별한다.

새 검증/출처는 `review_299_fix_validation/` 및 `../REVIEW_RESPONSE.md`의 #299 절에 기록한다. 물리/SIM step/렌더/모델 호출은 없으며, 이 합성 회귀·과거 집계 재대조는 확증 성공·봉인·러너 인수 승인이나 TensorBoard 신규 실험이 아니다.

최종 결과: 관련 **260 passed**(독립 33개 모두 포함, xfail/skip 0), 구 코드 회귀 부분집합 **17 passed**, 16코호트 **308건**의 공개 집계 및 17개 cases.jsonl 해시 일치. cA/cB 각 24/24, 부분 tX1 12/14 + HOST_ERROR 2건 유지. 검토 대상 코드의 6개 실패는 수정 코드에서 모두 전체 안전 거부로 바뀌었다. 자세한 출처·첫 실행의 테스트 기대값 수정 기록은 [검증 README](review_299_fix_validation/README.md)에 있다.
