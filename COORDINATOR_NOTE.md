
## 2026-10-16 사용자 추가: "Mac 디스크는 좀 더 많이 정리해봐; 좀 이상한 규칙으로 남기지 말고"
범위를 넓힌다(사용자 명시 요청 = raw 삭제 승인). 남기는 것은 이것뿐: 각 실행의 summary/판정 JSON, LLM 요청·응답 텍스트, 명령 궤적, 해시 목록, experiments/에 커밋된 것, 열린 PR·진행 중 작업(24h 내 변경·사용 중 프로세스)의 자료, milestone/study로 이미 표시된 실행, 컨트롤러 **버전당** 대표 영상 1개(실행당 1개 아님).
지울 것(휴지통 대신 해시 목록 기록 뒤 바로 삭제해도 됨 — 휴지통은 공간을 안 비움; 기록은 cleanup-records):
- 위 이외 모든 dev 무거운 원본(프레임·이미지·npz·영상·대형 trace), RUN_META 없는 과거 자료도 dev로 간주(“missing RUN_META is preserved” 규칙 적용 안 함), 실행당 대표 mp4 자동 보존 안 함.
- 회수본(gcp1-runs, oracle-runs, azure-runs, retired-worktrees 등)의 무거운 파일 — 원본은 VM/ARM에 있다.
- outputs의 모델 체크포인트 중 configs/model_artifacts.json에 Release URL·sha256이 있는 것(로컬 사본), 없는 것은 목록만 보고.
- 오래된 worktree(최근 24h 무변경, 진행 중 아님): 미병합은 보관 브랜치 push 후 정리.
- Codex /private/tmp 잔여 트리, pip/uv/huggingface 등 재생성 가능한 캐시(경로·크기 보고 후).
- ~/.Trash: 비우지 말고 크기만 보고(사용자가 직접 비움).
정리 전후 여유 공간과 항목별 GiB 표를 보고.
