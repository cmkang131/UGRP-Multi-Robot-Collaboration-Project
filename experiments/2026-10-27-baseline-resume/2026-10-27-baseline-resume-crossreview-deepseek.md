# Baseline 실행 재개 — DeepSeek 최종 교차검토

모델: `opencode/deepseek-v4.1-flash-free`, variant `max`, Oracle 로컬 CLI. 검토 범위는 동결 문서 및 선행 MiniMax 검토 대조이며 원격 런타임 검증을 대신하지 않습니다. 아래는 반환한 최종 본문을 무수정 이관한 것입니다.

**검증 범위:** 동결본 481행과 MiniMax 검토 전문을 직접 읽었습니다. 로컬 체크아웃에 `baseline-treatment-evidence/package/`와 `future_driver.py`·`audit_cpu.py`·`verify_baseline.py`가 없어 33/33 해시·코드 수준은 독립 재계산하지 못했고, SHA-256도 재계산하지 않았습니다. 판정은 문서 내용·조건 대조에 한정합니다.

**1) 최종 판정: PASS — 사전등록 동결본 한정.**
C-11 본인 서면 확인 인용, C-06 escalation 9,180s 확정, C-07의 동결 차단/실행 직전 조건 분리가 문서상 일관됩니다. 승계 범위 선언과 본문도 일치하며 MiniMax PASS(조건 0)와 충돌하지 않습니다. **GPU 실행 승인은 아니며, 3)을 모두 기록하기 전 실행 금지. runtime PASS도 아닙니다.**

**2) 차단 결함: 0.**
구조적 차단 결함은 없습니다. 비교 정의(동일 정책·다른 감독·달라지는 입력 스트림), “조율 불필요” 금지, release grasp/B 혼입 금지, stage-head 원인확정 금지는 문서에 정확히 등록되어 있습니다. C-07 체크박스 미체크는 미이행 표시이며 동결 결함이 아니고, C-07 미이행 실행은 문서 결함이 아니라 규정 위반입니다. MiniMax의 비차단 잔여 4건(최종 교차검토·RUN_META 봉인·소스 Git 보존·원격 재해시 명시)은 3)에서 실행 전 의무로 흡수했습니다.

**3) 실행 전 필수 확인:**
- **C-07:** 오프피크 KST 01:30–09:30 gcp6 기동 후 `--all-hosts` 실제 대상·연결, gcp6 전체 쓰기 예산·8 GiB 바닥·동시 잔여 쓰기, GPU 원장·크레딧·budget-stop, 예약량을 기록. 기록 전 GPU 시작 금지.
- **원격·봉인:** `verify_baseline.py` 33/33 + S/T/R/A HEAD + tracked clean(L 과거 바이트 미증명 한계 유지), RUN_META(class=study) 기동 전 봉인(실제 commit/PR/batch/source heads), 실행 소스 Git 보존, 최종 교차검토 기록. 최신 원장·중복 작업 확인(E-01/E-02).
- **L4 부족 시:** 동일 리전 다른 존, 동일 g2-standard-8/L4·코드·모델로 디스크 스냅샷 복원. 인프라 변경이며 사전등록 수정 없음. 10분 간격 재시도, ABORTED로 닫지 않음. 새 VM ID를 RUN_META/원장에 기록하고 20개 arm은 한 VM에서 완주(VM 간 부분 결과 합산 금지). 비용 정지 발동 시 다른 VM 우회 금지는 그대로.
- **순서·파일럿:** C 20(파일럿은 별도 4-case가 아니라 완료 순서상 첫 4개) → ① close 거부 0, ② 전체 proposal_rejected 0·비영 wheel·4월드×r1/r2 물리로그 유효·최소 1 robot-world `max_xy_excursion_m > 0.03082987502070276 m`, ③ cadence/HOLD·skill=grasp·state[225]=0, ④ HOST_ERROR 0 + 속도·무결성 명시 통과 → S 20 → 즉시 VM 정지. 파일럿 실패/부재는 fail-closed로 S·C 재시도 예약 취소.
- **재시도·예산:** C 재시도 최대 1회·동일 seed·S 폐기·zstd 무손실 압축/해제 SHA 검증 선행. C wall >9,180s면 S/재시도 취소. 누적 20 GPU-h 상한 유지. 1.70은 보장 상한 아님. 3개 예약 동시 집행은 8 GiB 바닥 미달로 불가.
- **게이트:** 첫 30 SIM초 median >6.0 또는 측정 불가/HOST_ERROR → SPEED_GATE_FAIL. GPU 구간 CPU 분석 비동시. 기동/프로비저닝 실패는 인프라 재시도로 분리하고 에피소드 HOST_ERROR 최대 1회와 섞지 않음.

**4) 비차단 위험 3개:**
- **① 1.70 GPU-h/wall 과소추정.** r2는 71,709/72,000 blocked·비영 wheel 60/72,000의 사실상 정지였고 physics는 wall의 약 34.5%였습니다. Arm C의 실제 이동·접촉·solver 부하가 늘면 wall이 1.70을 넘을 수 있고, 9,180s escalation은 현재 배치를 멈추지 않고 후속 예약만 취소합니다. 근거: §GPU 예산과 재시도(P-22/C-06(a)), E-04.
- **② 파일럿 게이트의 늦은 검출.** 20-lane 병렬에서 4번째 완료가 배치 끝 무렵이면 절약 GPU-h≈0입니다. fail-closed는 정확성을 지키지만 비용·시간을 구하지 못합니다. 근거: §파일럿·계속/중단(P-13/C-04/C-05).
- **③ release/place 교란·stage-head 원인확정 금지·S 취소 시 인과 미시험.** Arm C release 구간은 skill=grasp·destination=B이고 r2는 release 미도달, P5는 동일 구간 입력 기준선이 아닙니다. place 성공/실패를 감독 해제와 분리할 수 없고, stage가 전부 approach여도 stage-head 원인 확정은 금지됩니다. S가 취소·미완료면 인과 루프 가설도 미완료입니다. n=20·보류과제 3회 사용으로 일반화도 제한됩니다. 근거: §사전 해석·통계(C-01(a)/C-02), P-14·P-20, E-07, P-25.

**비차단 문서 흠:** frozen:66의 03:33 인용은 축약형이고 frozen:9·44의 C-07 목록도 축약이나, 권위 체크리스트 frozen:20과 종결부 frozen:449가 5종을 모두 포함하므로 판정에 영향 없습니다.


## 코드 범위 보충 요청 기록

위 판정에서 찾지 못했다고 한 코드 파일은 실제로 `outputs/reports/2026-10-26-baseline-treatment-evidence/package/`에 있습니다. 절대경로로 3파일을 추가 첨부한 보충 요청은 `reason=length`, reasoning 32,000 tokens·output 0으로 종료돼 최종 본문이 없었습니다. 최초 문서 PASS와 이 보충 미완료를 구별하며 원문·SHA를 보존합니다. 사용자 지시에 따라 코드 보충은 MiniMax의 별도 서면 확인으로 대체합니다. 원격33/33·GPU런타임은 어느 문서 검토로도 대신하지 않습니다.
