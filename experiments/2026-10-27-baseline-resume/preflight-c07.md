# Baseline 실행 재개 C-07 및 GPU 전 봉인

**PASS — 2026-10-27 04:56 KST Arm C 제출 전 완료.** 원래 동결본은무변경(043b9583427d845e08c19bb63448f779e4f33913a858b7ad4f8590f7f0e8dafb)입니다.

| 항목 | 실제 확인 |
|---|---|
| 대상 | project ugrp-sim-f-1016 / ugrp-act-l4-gcp6 / asia-northeast1-c / id2102818194467198298 / g2-standard-8·L4 |
| 원본33 | 33/33·4개HEAD일치·tracked clean, 존어댑터후재확인도PASS |
| 처치10 | 현재C-08 10/10해시일치 |
| CPU모델 | step-011000 원래로더PASS, CUDA초기화false·forward0·시뮬레이터모듈0 |
| 저장 | GCP free14,811,398,144 B, C1GiB차감후13,737,656,320 B > 8GiB. 실제Oracle ARM·Mac도각25/20GiB바닥충족 |
| all-hosts | 기본alias oracle-x86 접속실패원문보존. 실제실행GCP·제어/보관Oracle ARM·실제Mac을직접조회해기존storage_budget.check로동일계산; storage-all-hosts-final.json |
| 동시쓰기·임대 | 새VM의다른GPU/user작업0, 동시잔여쓰기0. snapshot의옛e2ewarp 임대는프로세스없는과거메타로보존, 우리임대별도등록 |
| 비용 | 이전원장약13.1/20은근사. 최신budget이벤트19:48:17UTC 순비용0 KRW/예산1000 KRW, INCLUDE_ALL_CREDITS. 실시간크레딧잔액은미제공이며순비용을잔액으로표현하지않음 |
| 정지장치 | budget-stop ACTIVE, 실제함수원본/이벤트/IAM확인. aggregated_list로모든존VM정지대상, instanceAdmin권한유지. VM유휴20분timer active·서비스계정없음 |
| 소스Git | 고정S/T/R/A4커밋완전bundle생성·verify·SHA보존. 동결처치/운영소스commit22fc786b5813e9139bb58d790a98e984e33d03e8 push, draft PR621 |
| 검토 | MiniMax선행PASS, DeepSeek동결문서PASS. 코드보충응답길이종료원문보존후MiniMax서면CONDITIONAL_PASS·구조차단0. 존어댑터도별도MiniMax조건부확인·구조차단0, 남은배포/봉인/33조건실측충족 |
| AST/정리 | L원본main의a/report/results/i scope와main finally의lane.close/hooks.close 확인. C/S계획AST훅completion1·progress1. 외부존어댑터→원future_driver계획실행도PASS |
| 메타 | RUN_META class=study·PR621·실제SHA·host/source heads/wrapper/원host SHA/예산/분기봉인. revision1은GPU0상태에서존어댑터전봉인으로보존, 최종revision2를GPU전확정 |

존이동은사용자직접승인된 **실행인프라변경이며사전등록프로토콜변경이아닙니다.** 원host확인기는서울a만허용해CPU검사에서거절했습니다. 원본을고치지않고 `--restore-host-zone-v1` 기본off 외부어댑터를선택했습니다. 원host모듈SHA·정확한실제VM ID를검사한뒤프로세스내gcp6승인행zone만대체하고원래Linux/project/name/machine/account검사를호출합니다. 실제Tokyozone을보고하며입력/정책/물리/평가/seed/모델/cadence는바꾸지않습니다. 실제VM ID통과·틀린ID거부·배포SHA·원33해시를확인했습니다.

최종RUN_META SHA256 `519723dcdaff812373da9628e8d13a23a119b742217fba5856e1d20d073e9507`. 원격 `/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z/RUN_META.json`. C20만제출하며S·재시도는미승인후속상태로유지합니다. C20→파일럿/무결성/속도명시PASS→디스크/예산재확인→S20 순서, C>9180s면후속취소, 신규전체5.3·전역20 GPU-h를유지합니다.
