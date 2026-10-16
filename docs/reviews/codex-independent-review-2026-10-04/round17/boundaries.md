# 17차 경계 검토 — endpoint 완료와 작은 covariance

## Completion

실제 PairExecution/PairStatusChannel/own-job 종료의 다섯 경계를 독립 재현했다. 시작의 controller done과 issued open은 선언한 prefix이며, [최종 release 제어](release.md)의 물리 결과를 이어 받은 전체 실행은 아니다.

| 입력 경계 | 실제 계약 결과 |
|---|---|
| 양쪽 done | 각 endpoint가 한 번 PAIR_SEQUENCE_DONE/unconfirmed로 종료, holding unknown |
| 자기 done·상대 지연 | 상대의 fresh status를 기다리며 즉시 성공으로 끝내지 않음 |
| 상대 abort | 기존 abort 경로로 종료; 늦은 done이 실패를 되돌리지 않음 |
| 상대 silence | PARTNER_SILENT 및 상대 PARTNER_ABORT |
| 자기 image predicate=False | INVALID_OWN_IMAGE 및 상대 PARTNER_ABORT; done이 검사를 건너뛰지 않음 |

종료 뒤 반복 step/poll에서도 같은 job 종료를 중복 기록하지 않았다. 세 exact source hash와 전체 golden 일치를 확인했다. 절차 완료(C), 허용 관측 확인(K), 별도 task predicate(Y)를 구분하는 [15차 계약](../round15/research.md)과 맞는다. Unconfirmed는 물리 성공이나 실패를 측정했다는 뜻이 아니다. 실제 contact/object placement/전체 guard/physics는 검증하지 않았다. 상세 원고와 재현·독립 QA는 Mac의 `done-endpoint-*`에 보존했다.

## Precision

66ff의 실제 OwnCamLocalizer.estimate는 covariance를 소수8자리로 내보내고 std는 반올림 전 값으로 계산한다. Carry-align은 finite nonnegative cov_yy를 우선하므로, 값이0으로 반올림되면 출력 정밀도가 계산에 영향을 줄 수 있다.

Authored2000입자의 σ_y≈40.01µm, residual50µm 대조에서 emitted covariance는 keep/left≈.000597614를 만들고 같은 cloud의 unrounded covariance는 skip을 만든다. 실제 port/motor setter까지 float 차이가 보존됐지만 physical step은 없다. σ≈400µm 또는 residual0 대조는 두 표현 모두 skip한다.

**현재 지원 prior/scan history가40µm belief에 도달한다는 증거는 없다.** 예정보정 자체도50µm이고 motion profile은 authored 값이다. 실제 운반·안전·성공 효과나 현재 실패 원인으로 확대하지 않으며 새 버그로 세지 않는다. 이 부록은 반올림을 항상 표시 전용이라고 설명할 수 없다는 범위다. 다른 검토자는 단위·수식·source 해석을 확인했으며 그 QA는 추가 재실행이 아닌 범위 검토다. 원고·source/helper hash·재현은 Mac `covariance-precision-*`에 보존한다.
