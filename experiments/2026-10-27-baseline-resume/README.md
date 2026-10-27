# 동결 Baseline C/S 실행 재개 결과

사용자 2026-10-27 03:45 KST 지시에 따라 L4 용량 부족을10분 간격으로 재시도하고 서울a 원본 스냅샷을 도쿄c에 복원했습니다. 존 이동은 실행 인프라 변경이며 동결 프로토콜은 유지했습니다.

Arm C20 정상완료 성공0/20, 파일럿·무결성·속도 PASS 뒤 Arm S20 정상완료 성공0/20입니다. 개별 arm의 CP95%는[0,16.843347%], 등록 C 대 r2 exact McNemar p=1.0입니다. S는 기술통계이며 합산하지 않습니다. C의 학습 stage는 approach 밖으로 진행했지만 물리 성공으로 이어지지 않았습니다. S 전체프로토콜 일부 READY/GO/ACK는 열렸으므로 누적 funnel READY0을 전체 handshake 부재로 해석하지 않습니다.

VM09:01:51KST TERMINATED, 이번4.422834GPU-h·이전 근사 포함 누적약17.522834/20입니다. 67,165개 raw/파생 파일의 ARM 사본 전체SHA를 확인했고 원본 디스크를 보존했습니다. 고정 step-011000은 새 Release 공개 재다운로드13파일 및 새 고정소스 CPU로딩 PASS입니다. forward/학습/재선택은 수행하지 않았습니다.

- [최종 보고](execution-report.md): 동결 해석표·검증 범위·누락 공시·재현 명령.
- [전체40개 실행 요약](summary.json): 실패 포함 원본 경로/해시와 관문별 funnel 연결.
- [C 결과](results-C/C-audit-v1.json), [S 결과](results-S/S-audit-v1.json).
- [보관 검증](study-archive-verification.json), [GPU 원장](gpu-ledger-final.json).
- [모델 검증](model-artifact-verification.json), [C-07](preflight-c07.md).

동일 heldout20 세 번째 사용·n20·입력피드백/release토큰 confound·호스트 렌더 동등성 미측정 한계를 유지합니다. C 스택 검사파일 사전 누락은 사후 공개했고 S는 사전 점검했습니다. 기존 child dev/pr484 메타는 고치지 않고 실제 부모study/pr621 및 정상종료 sidecar로 보존했습니다. 이 결과는 일반화·개별 장벽 필요성·stage-head 단일원인을 확정하지 않습니다.
