# CHECKPOINT (PR #265, claude/pair-v6d-reg) - 커밋하지 않는 파일

시각: 2026-09-29 (사용자 외출로 중단)

## 상태
- 브랜치 HEAD = origin/claude/pair-v6d-reg = 198279c2 (origin/main 1e7bdfe0 병합 커밋). 푸시 완료, 작업 트리 깨끗(이 파일 제외).
- PR #265 본문 갱신 완료(정정 섹션, 버전/ID, 검증 범위, 후속 확인 근거, 참고 자료).
- CI(run 36508173930): 22 통과, `offline-regressions` 1개만 진행 중. 실패 없음. 끝나면 `gh pr checks 265`로 확인.
- 병합하지 않음(사용자 승인 필요).

## 끝난 수정 (코드 동작 변경 없음)
1. 플래그 설명·docstring 정정(`scripts/zone_pair_v6_contract.py`, `harness/owncam_align_motion_v6d.py`, `harness/zone_pair_v6_policy.py`)
2. README/PR 본문의 "동결 파일 그대로" 정정(M2 동결 파일 16줄 변경, 허용 목록 sha 추가 명시)
3. 운동 재생 축별 보고(중앙값, 독립 이력 36건): `diagnosis/motion_replay_axes.{py,txt}`
4. `PROBE_VERSION` 0.5.0 (0.4.x = #266 raw가 쓴 값이라는 메모 포함)
5. 버전 표 설명(v76 = 25셀 기록, v80 = 병합 트리 기록)
6. README 깨진 링크 3개 수정
7. 오프라인 hue 25 vs 36 확인: `diagnosis/hue_mask_check.{py,txt}` (음성 대조 아님, 판정에 쓰지 않음)
- 재봉인 1회: `prereg_v6d.json` sha256 cbdb4b25...9972, registration_sha256 1a152963...90e3. 병합 뒤 재생성해도 바이트 동일, 2차 재봉인 불필요.

## 남은 일
- `offline-regressions` 완료 확인(초록이면 보고, 실패면 로그 확인).
- 이후 사용자 승인 뒤에만 병합. 병합 후 worktree 정리는 `python3 scripts/agent_worktree.py retire <경로> --execute`만 사용
  (`claude-v6d-reg`, `claude-v6d-align` 둘 다 아직 미정리).
- 열린 항목: 플래그별 물리 ablation 없음, r2 p45/inspect 재생 없음, held-out 없음, 단계 4/5는 b-v6d로 안 돌림.

## 프로세스
- 내가 시작한 실행 중 프로세스 없음(물리·모델 호출 0).
