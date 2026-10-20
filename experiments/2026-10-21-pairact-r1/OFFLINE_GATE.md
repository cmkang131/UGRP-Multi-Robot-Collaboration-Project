# pairact-r1 오프라인 gate와 체크포인트 선택 (사전 등록 초안)

- 대상: P4 학습 run의 모든 체크포인트(`step-*`, 1,000 step 간격, 20개)
- 데이터: *validation split만*(seed 8341000–8341019의 teacher 성공 에피소드). TRAIN과 heldout은 쓰지 않습니다.
- 실행: `scripts/pairact_r1_offline.py`. 기준값은 `harness/pairact_r1.py`의 `GATE`, 선택 규칙은 `select_checkpoint`입니다. 결과를 보기 전에 이 문서와 코드를 커밋해 고정합니다.
- 지표는 모두 h0(chunk 첫 행) 기준입니다. clean(기록된 이력)과 dithered(고정 seed 20261021로 이력 PWM에 ±1–6, p=0.5 주입) 두 번 계산합니다.

| ID | 지표 | 기준 | 겨냥하는 실패 |
|---|---|---|---|
| G1 | 단계 macro 정확도(validation에 있는 단계 평균) | ≥ 0.80 | 단계 head 미학습 |
| G2a | 조기 READY: 정답이 접근·정렬·복구인 행에서 `ready`를 예측한 비율 | ≤ 0.02 | 정렬 전 GO 20/20(beamact4 README:9) |
| G2b | 조기 실행: 같은 행에서 실행·운반·하차·완료를 예측한 비율 | ≤ 0.02 | GO 없이 진행 |
| G3a | done 오검출: done 정답 0인 행에서 score ≥ 0.65 비율 | ≤ 0.01 | 조기 done |
| G3b | done 재현율: done 정답 1인 행에서 score ≥ 0.65 비율 | ≥ 0.80 | 한쪽 done 고착 A 11/20·B 9/20 |
| G4 | 전이 재현율: alignment→ready, ready→execute, carry→place, place→complete 각각, 실제 전이 뒤 10행 안에 도착 단계를 예측한 비율 | 각 ≥ 0.80, validation에 전이가 1개 이상 있어야 함 | READY·파지 전환, 하차 시작(단독 release 실패) |
| G5a | dithered 이력에서 단계 macro 정확도 하락 | ≤ 0.05 | 명령 이력 copycat |
| G5b | dithered 이력에서 done 오검출 | ≤ 0.02 | 명령 이력 copycat |

- 측정값이 없으면 실패로 봅니다. 예를 들어 validation에 해당 전이가 없으면 G4는 실패이고, 이 경우 기준을 바꾸지 않고 보고합니다.
- *선택 규칙*: 통과한 체크포인트 가운데 G4 최소 재현율이 가장 높은 것을 고릅니다. 같으면 G1이 높은 것, 그래도 같으면 이른 step을 고릅니다.
- *통과 체크포인트가 0개*면 `NOT_READY_NO_CHECKPOINT_PASSES`입니다. P5는 돌리지 않고 Claude 본체에 보고합니다. 기준 완화나 heldout 확인은 하지 않습니다.
- 기준값은 정답 데이터를 보기 전에 정한 값입니다. 0.80/0.02/0.01은 단독 A-r1 gate(`CARRY_RETRAIN_R1_DRAFT.md` G-r1..G-r6)와 같은 엄격도를 목표로 잡았고, 근거 데이터는 없습니다. Codex 검토 대상입니다.
- 오프라인 gate는 closed-loop 성공을 보장하지 않습니다. beamact3는 오프라인 wheel MAE가 좋아졌지만 0/20이었습니다(beamact3 README:7–12). 그래서 G2·G4처럼 *전이 판단*을 직접 재는 항목을 넣었습니다.
