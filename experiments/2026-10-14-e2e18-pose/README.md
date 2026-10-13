# E2E18 위치 추정 원인 분해
- summary.json: 시각 정합, 증분/명령 분해, 기본off 후보의 오프라인 판정.
- fetch-lite-manifest.json.zst: 48 실행 1,034 텍스트 파일 원본 위치·SHA-256.
- 시각: physical t = own t − checkpoint cutoff + physics start(1.3).
- GT는 평가에만 사용하며 gain 수치로 제어 계수를 맞추지 않는다.
- 회수 전용 VM3 재시작 후 deallocated 확인: retrieval-vm.json.
- 행동 로직 수정·새 E2E 제출 없음. 기준 미달 후보는 온라인 제출하지 않음.
- 표준 방법·공개 구현: references.md. PR #461에서 분리한 후속 DEV.
