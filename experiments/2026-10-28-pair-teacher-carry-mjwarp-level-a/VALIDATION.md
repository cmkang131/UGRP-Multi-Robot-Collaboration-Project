# 검증 범위

- 기준: `dsh/pairact-p2-carrypath-c4` / `402bbf155ca162da7a74518eab9b8bd98138299a`. main에 없는 evaluator의 파일럿 계보에서 분기했다.
- `/home/ubuntu/ugrp-venv/bin/python -m pytest -q tests/test_pair_carry_teacher_warp.py`: **58 passed in 1.17s**, exit 0. 순수 Python 기하·kinematic fixture·AST/recorder 시험이며 MuJoCo/MJWarp 물리 실행이 아니다.
- 음성 사례: zone B pre-placed 0m (legacy true/strict false), never-grasped placement, early release/missing door despite displacement. 양성 kinematic conjunction, 1m 경계, 비유한 값·누락 근거, 사용자 criteria와 legacy 실패 상속도 확인했다.
- `python3 experiments/2026-10-28-pair-teacher-carry-mjwarp-level-a/seal_level_a.py`: exit 0. 파일럿 15건·독립 1건의 전체 funnel, drop0·로봇 간 접촉 프록시0, weld off·visible_only·입력감사0을 직접 검사했다. 원본 trace에서 보강 수치만 계산했다.
- `sha256sum --quiet -c experiments/2026-10-28-pair-teacher-carry-mjwarp-level-a/artifact-index.sha256`: **181/181**, exit 0. golden carry-eval/result/plan/trace는 기존 manifest 항목과도 일치한다. 봉인 파일을 다시 쓰지 않았다.
- JSON/JSONL 직접 assertion: golden16의 distinct cohort/seed, pilot15, 모든 결합 조건, ledger 420/238·proxy238·ambiguous238, C/S 20개씩 strict0 및 raw carry-eval 재계산0, summary 과대계상 world10/16/18 일치. exit 0. 각 생성 JSON/JSONL은 64KiB 이하다.
- 읽기 전용 보조 검증: golden 분리·원본 181해시·현재 scoped C/S의 경로·ledger `funnel_last`의 비결합 의미·GPU 산식 대조 PASS. 코드·산출물은 주 Codex가 작성했다.
- `git diff --check`: exit 0. 변경은 evaluator, 해당 시험 파일과 새 실험 폴더뿐이다.

이번 검증은 학생 물리 임무 성공, 새 GPU 관문, native 충돌 쌍, 영상 검토 또는 ledger 전체 strict 확정이 아니다. native-contact toggle은 추가하지 않았고 기존 contact proxy를 표시한다. 로컬 분석의 GPU·VM 조작·새 physics step은 모두 0이며, 모델 가중치를 새로 만들거나 선택하지 않았다. 원본·prereg v3·기존 결과 파일은 수정하지 않았다.

PR 자동 CI는 로컬 분석과 별도다. 취소 전 CPU demo 단계가 실행되어 “새 물리 실행 없음” 제약을 위반했다. 해당 run은 completed/cancelled이며 상세는 `CI-CANCELLATION.md`에 기록했다. 전체 CI 통과 주장은 없다.
