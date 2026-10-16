# 같은 ledger에서 cohort와 run identity를 구분하기

**새 unconditional P2가 아닌 재현 가능한 운영 제약**이다. #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`의 pair live runner는 condition/seed가 같으면 cohort가 달라도 같은 run key를 만든다. 새 cohort 등록만으로 같은 seed의 실행 identity가 새로 생기지 않는다.

[CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_pair_llm.py#L120-L178)는 cohort-id/seed/budget-db를 따로 받고, [run_pair_live](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_live.py#L221-L271)는 `condition-s{seed}`, [run_attempts](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L565-L592)는 `#a1`을 더한다. SQLite runs.run_key는 전체 DB에서 유일하다. 등록 가능한 cohort가 여럿이라는 사실만으로 현재 pair smoke가 같은 seed 재사용을 허용하는 연구 계약이라고 단정할 수 없다.

| 실제 runner/ledger 합성 호출 | 새 wire send | 결과 |
|---|---:|---|
| A cohort, peer_nl, seed911 | 1 | finished·provider150 tokens 기록 |
| DB reopen, 같은 A/911, 새 출력 폴더 | 0 | duplicate key 거절, 기존 행 그대로 |
| 같은 DB, 등록된 B/911, 새 출력 폴더 | 0 | 같은 duplicate key 거절, B 사용량0 |
| 같은 DB, B/912 | 1 | 별도 run 정상 기록 |

이 스크립트는 원본 live runner/attempt/ledger와 새 임시 SQLite를 사용한다. physical case·bundle·ModelAdapter holder는 synthetic이고 wire도 fake다. 전체 CLI를 실행한 것은 아니다. 직접 runner는 충돌 시 case/attempt 파일을 만들지 않지만 full CLI는 앞서 plan.json을 만들 수 있으므로 “실패한 CLI는 파일이 없다”고 확대하지 않는다.

두 process의 cap1/unknown charge1 경쟁은 하나만 admit하고 하나는 BudgetExceeded였다. request를 commit한 뒤 wire 호출 전 child가 종료한 대조는 reopen 뒤 sent_unknown·pending1·charge7을 보존했다. 이는 좁은 transaction/process 경계이며 실제 provider billing·uncommitted power loss·모든 concurrency schedule의 증명이 아니다. recorder는 최대 응답 토큰을 미리 예약하는 hard budget ceiling도 아니다.

실용적 수용 기준은 지정 ledger의 예정 key를 비싼 실행 전에 대조하고, 충돌을 명확한 identity conflict로 남기는 것이다. 동일 cohort 중복 보호·기존 cost rows·원래 seed plan을 보존한다. 실제로 별도 허가된 cohort의 같은 seed 재사용이 필요하다면 canonical key에 cohort/bundle/run identity를 포함하거나 동등한 composite uniqueness를 정의할 수 있다. 금지된 것이 맞다면 global namespace 계약과 명확한 preflight 오류를 문서화하면 된다. 새 DB·budget·seed를 만들어 우회하라는 제안은 아니다.

원본 상세 감사·source manifest·재현은 Mac의 `runtime-ledger-lifecycle-audit.md`, `runtime-ledger-lifecycle-repro.py/.json`에 있다. POSIX fork가 있는 Python에서 `--repo /path/to/git-clone --output /new/result.json`을 사용하며 frozen R9 Git restore utility가 필요하다. 독립 재실행이 모든 assertion을 통과했다. race 승자와 timestamp는 항상 동일하다고 요구하지 않는다.
