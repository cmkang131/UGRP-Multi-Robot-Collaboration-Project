# 9차 독립 반증·재현 기록

분야 저자의 주장과 fixture를 편집자가 별도로 읽고 실행했습니다. 각 결과는 해당 source SHA와 아래 경계에 한정합니다. 기존 오류를 신규로 다시 세지 않았습니다.

| 대상 | 별도 실행과 대조 | 판정·제한 |
|---|---|---|
| P06 horizon | 실제 candidate writer AST + seal/inspector/cohort. H12정상, H6/H24 mismatch, referee-present 거절. 결과 JSON 완전 일치. | P2 candidate integrity. 성공 분모1/성공0 보존. 현재pair/runtime나cohort PAR2평균 왜곡으로 확대하지 않음. |
| claim 기록 | 실제 gate/action-map/link/own method. fresh0, A재시도후B2, 같은A relook2, reset mechanism B0/누적2. 결과 완전 일치. | P3 허가별 기록귀속. fake Team.start/hold완료; motor·비용 영향 미입증. |
| STATUS | 144정상 조합 + 철회/재승인/만료/identity/abort/late-poll. 결과 완전 일치. | fixed-enum primitive 한정 통과. 물리파지·독립네트워크·기존same-tick issue 문제의 해결 아님. |
| vision temporal | 마지막 HIGH8초와 동일faketrajectory assert본을 별도 임시폴더 실행. wall latency·환경표시 제외 JSON 일치. unsettled/columns 부족0update. | 선언된 own-command view reset의 적용 범위. synthetic PF/likelihood; 실제pose·NEES·480×640영상/whole provider 검증 아님. |
| runtime provenance | exact Git source복원·실제 scheduler/request/completer/relay. overlap/after-completion와 inflight/nonexistent/known 참조. 결과 JSON 완전 일치. | accepted 예약과 SIM release를 구별하는 의미 공백. reply_to가 실제입력 증거는 아님. 내용/GT누출이나모델 발생률 미입증. |
| PF 정적 수학 | fractions기반 K3/rho.5, 정방향/역방향/동일관측, 61/81 sampling variance. 별도 임시 실행 JSON 일치. | 정적latent·등상관Gaussian 가정만. 움직이는PF를역순불변으로 요구하거나실제정확도 실패를 주장하지 않음. |

## 독립 검토로 좁힌 주장

- vision의 nonzero command reset은 source가 명시한 policy입니다. command renewal에 따라 가중치가 달라지는 사실을 구현 위반으로 바꾸지 않았습니다. `stalled_stub`은 odometry0인 fake endpoint이며 실제stall관측이 아닙니다.
- runtime 시작 snapshot에도 future declared-send ID가 있으므로 lazy prepare를 snapshot 복사로 바꾸는 것만으로 해결된다고 쓰지 않았습니다. pending reservation의 합법적 의미와 실제 SIM release를 분리합니다.
- P06 성공 분모는 정상이며 문제가 있는 것은 per-trial horizon/PAR2의 frozen bundle 일치입니다. actual runner가 candidate writer를 쓰는 것으로 소급하지 않습니다.
- claim wait대조는10초hold 창 이후의 시각을 사용하지만 완료 자체는fake입니다. directly replaced permit 경로도 같은 counter귀속을 재현합니다.
- own_status는 decision_sources에 따로 없는 대신 prompt가 own_commands로 보고하도록 명시합니다. schema누락 버그가 아니라 의도된 coarse attribution입니다.

새 simulator·renderer·LLM·학습·실물 실행은 없습니다. 코드검색에 부수적으로 반환된 공개fixture 출처줄은 분석에서 제외했고, raw/heldout outcome을 의도적으로 열어 결론을 만들지 않았습니다. 실제 시행의 성능·발생빈도·전체 코드/CI완료를 주장하지 않습니다. Mac 증거에는 별도실행 JSON과 정확source/hash를 보존하며 원본결과를 덮어쓰지 않았습니다.

## 연구 source 교차검증

별도 평가 검토자가 P1–P5의 원문에서 핵심 입력·선정조건·별도통신단계를 직접 대조했습니다. 연구용5개 source 사본의 a009 Git object/hash와 PF fractions 수학도 확인했습니다. own_status→own_commands의 의도된 매핑, accepted 예약 의미, 정보가용성≠인과사용의 범위를 재확인했습니다. c_K의 무한극한 표현에는0<rho<1 조건을 명시합니다.
