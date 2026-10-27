# HAN-21 D0·D1·D2 진단 후속 정리

기존 MJWarp Arm C/S 자료의 CPU 진단과 MiniMax 서면 검토를 보존한다. SIM 결과이며 REAL 검증이 아니다. 이 후속 작업은 문구 정리·기존 산출물 대조·Git 보존만 수행했고 GPU 사용, VM 기동, 새 실행, 학습, 임계값 변경, 수치 재산출은 없다.

- [기존 진단 요약](summary.json)은 최초 계산 산출물 그대로 보존한다. 파일 안 scope·analysis_attempts는 최초 진단의 이력이며 이번 후속 실행을 뜻하지 않는다.
- [수정 보고서](../../outputs/reports/2026-10-27-d0d1d2-diagnostic-report.md)와 [수정 전 원본](../../outputs/reports/2026-10-27-d0d1d2-diagnostic-report-original.md)을 구분한다. 모든 표는 동일하며 추가 권고·정의·해석 경계·변경 이력만 보완했다.
- [MiniMax 검토 정리](../../outputs/reports/2026-10-27-d0d1d2-minimax-review.md)는 원문 최종 판정 “부분 동의, 수치 수정 0건, D1 8/8 일치”와 당시 D2 최종 VERIFICATION 미수령을 기록한다. 정리 말미의 전체 원문은 바이트 그대로 보존했다.
- [별도 D2 최종 검토](../../outputs/reports/2026-10-27-d0d1d2-minimax-review-d2-final.md)는 이번 읽기 전용 요청의 결과와 검증 범위를 기록한다. 최초 검토의 미완료 상태를 소급 변경하지 않는다.
- [기존 증거](../../outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/) 중 summary·verification·episodes·D0·funnel·source/artifact manifest 및 정의 확인용 analyze.py·verify.py를 내용 변경 없이 Git에 보존했다. 스크립트는 이번에 실행하지 않았다.
- 최초 `artifact-sha256.json`은 수정 전 보고서와 최초 summary의 기록이다. 후속 보고서의 해시를 뜻하지 않는다. 대량 프레임 CSV와 다른 raw는 로컬 보존이며 이 PR이 모든 원본의 원격 백업을 뜻하지 않는다. 원본 경로·해시는 기존 summary/source manifest에 있다.

D0 교사 궤적 적합도 및 기록 없는 D2 true stage·확률 지표는 미완료 상태를 유지한다. 프록시는 성급 READY 정답·arm 우열 비교·인과 증거가 아니며, run 간 독립성도 미검증이다. 다음 단계는 HAN-17 중간보고서 반영 대기다.
