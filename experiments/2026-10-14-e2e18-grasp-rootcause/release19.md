# release19 준비 (2026-10-15)

단계 1: 제어 소스 `a3bbc90e07d3d731278cb6c83185687a190e3c6b` 그대로, 새 시드 **110600–110639** 40개를 예약했다.
로컬 vm3-queue와 experiments의 JSON/Markdown/텍스트 7,081파일을 보수적으로 확인했고 중복 0개다.
저장소 전체/원격 브랜치 검색은 하지 않았다. 입력 경로 목록·해시의 digest는 `release18-gate40-seed-audit.json`에 있다.
관문은 **≥38/40**, 인계 실패·HOST_ERROR·timeout은 실패이고 대체 시드를 넣지 않는다. 학습 기록 off·180초 상한·기존 판정 유지.
큐 `20261015-release-gate40-a3bbc90e.json`은 40회 모두 승인·준비·실행 플래그 false이고 제출하지 않았다.

새 입력 계획은 제어 소스와 별개다. 큐는 압축된 계획과 SHA-256을 내장하고 원격 명령 argv로 전달한다.
따라서 a3bbc90e에 새 파일/수정 없이 기존 run()을 호출한다. 조정자는 각 SHA의 깨끗한 별도 source checkout을 지정한다.
활성 worktree를 과거 SHA로 되돌리지 않는다. `--commands`는 argv를 출력만 하고 실행하지 않는다.

```sh
python3 -m scripts.prepare_release_gate40_queue --verify /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate40-a3bbc90e.json
python3 -m scripts.prepare_release_gate40_queue --commands /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate40-a3bbc90e.json --candidate A --source-worktree /path/to/clean-a3bbc90e-source
```

## 참고 자료

- `scripts/make_grasp_act_release_plan.py`: 기존 분포·판정·정적 시작 배치 생성기(물리/렌더 없음).
- `release18-diagnostic-plan.json`, `release18.md`: release18 실행 옵션과 기존 관문.
- 로컬 `outputs/e2e18-admin/gcp-reports/release18-diagnostic-a3bbc90e.json`: 제공된 9/9 진단, 관문과 합산하지 않음.
