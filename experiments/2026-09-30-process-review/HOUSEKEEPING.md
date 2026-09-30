# 2026-09-30 작업 폴더와 원격 브랜치 정리

조사 시작: `2026-09-30T19:12:54.448412+09:00` · 파일 조사 종료: `2026-09-30T19:16:44.274132+09:00` · 결과 확인: `2026-09-30T19:24:48.696632+09:00`

실행 소스: `a8094cc14e098a55483f53a3c49bf6a0b116043d` (`codex/housekeeping-0930`). 조사 시작 `origin/main`: `a8094cc14e098a55483f53a3c49bf6a0b116043d`. 최종 확인 `origin/main`: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.

## 삭제 전 원격 브랜치 목록

삭제 전에 아래 66개 이름·병합 PR·전체 커밋 식별값(SHA)을 이 파일에 기록했다. 후보는 `claude/`, `codex/`, `kiro/` 접두사를 가지며, 병합된 PR이 있고, 끝 커밋 전체가 `origin/main`에 포함되며, 등록된 작업 폴더(worktree)가 없는 브랜치로 제한했다. 실행 직전 `gh pr list`, `git ls-remote`, `git worktree list`, `git merge-base --is-ancestor`로 다시 확인했다.

재확인에서 통과한 **24개를 본 작업에서 삭제**했고, 종료 코드 0과 원격 부재를 확인했다. 나머지 **42개는 실행 전 SHA 불일치 또는 원격 부재로 제외**했다. 최종 조회에서는 후보 66개 전부 원격에 없었다. 제외한 42개의 삭제 주체는 이 기록으로 확정하지 않으며 본 작업의 실적으로 합산하지 않는다.

| 원격 브랜치 | 병합 PR | 삭제 전 SHA | 본 작업 결과 |
|---|---|---|---|
| `claude/dev-frame-capture-1hz` | [#241](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/241) MERGED | `56c7f6c93ee48af22ba0508871a6aeba133e6874` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/disk-cleanup-0927` | [#239](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/239) MERGED | `f8f7101e82e7c876f410409d7ea6a3ffd5b0d799` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/docs-0930-status` | [#287](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/287) MERGED | `16eef173dedeb957ebe5483568434d56435ea59f` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/kiro-agent` | [#182](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/182) MERGED | `16d360710a06c188a9b5f4c431b9e18881ff8c3f` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/main-study-prereg-draft` | [#254](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/254) MERGED | `945dc3292ce3b45c125a1667e5b7dd97cadff216` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/nl-dialogue-eval-survey` | [#252](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/252) MERGED | `704d87299107797e1e3c47408fa79fbd5555355e` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/owncam-loc-timestep-fix` | [#198](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/198) MERGED | `09be45c48b5f3f2f9dbf645be321c6c9dbe5b771` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/pair-stage-probes` | [#260](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/260) MERGED | `1e8c62b9a368a0c472d49bf1f42581200fe7b9cc` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/pair-v6c-carry-probes` | [#266](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/266) MERGED | `c6b68c12432bcd4df04eb0c6edd01c984f606326` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/pair-v7-side-grasp` | [#250](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/250) MERGED | `d384159f045397b7b632465ba5127adb4952f356` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/records-0926` | [#180](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/180) MERGED | `db53f3dccc90f3c98733fb38c2716903dddaa517` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/sim2real-protocol` | [#251](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/251) MERGED | `6c91f2ded2181d5022780af411d749826533d9b2` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/todo-dr-sim2real` | [#215](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/215) MERGED | `cd01e170c1602883683c460688e423183333c5c6` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/ultrasonic-range` | [#248](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/248) MERGED | `29fedc3e0638d680da32d4753d645925a20edbef` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/vis6-replay` | [#264](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/264) MERGED | `1dd89c8f4a5d03063388851c9c87ba9b49ddc29c` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-cargo-catalogue` | [#164](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/164) MERGED | `151bcde4f50c7f9b681d05eb515e72b29f0f3fbd` | 삭제·원격 부재 확인 |
| `claude/zone-m1-owncam` | [#201](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/201) MERGED | `1b836a1dc777e5eb8b603fa02ff694593ee53d8b` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-m2-pair` | [#203](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/203) MERGED | `78ef44292f787a71d1cb6308dfcd7750e9055389` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-owncam-loop` | [#178](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/178) MERGED | `71334f18cac5f963cc70e5ae673d8c817ecc2bf2` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-owncam-loop-v2` | [#197](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/197) MERGED | `835f9a4e475d9b1d987cbce605d2da69ead42f16` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-owncam-pair` | [#200](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/200) MERGED | `29700fd08d804e3ed7e8fd6948b03259f19adb3a` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-owncam-skill-v2` | [#181](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/181) MERGED | `6c81e3939f735a8c1a445bc8ecc44205b8af70fc` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-pair-v6-dev` | [#259](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/259) MERGED | `97bcb45faaa95471d720c97860022bebdc882901` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-pair-v6-historical` | [#262](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/262) MERGED | `a7a38f1e5bf6923bdc3273034b5ecfb4ecee016f` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-referee-orders-complete` | [#257](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/257) MERGED | `bead4596de319b93e56a3c11132f73323bbb9e23` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `claude/zone-team-a2` | [#169](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/169) MERGED | `64daf56d936466920ca65147604d06502d98d8ac` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `codex/act-map-generalization-plan` | [#70](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/70) MERGED | `ac20cb281060a09cb2757654d594881de000a636` | 삭제·원격 부재 확인 |
| `codex/act-map-protocol` | [#71](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/71) MERGED | `c6d41c06853bb1e66eaf154bd36b37f8553b0e73` | 삭제·원격 부재 확인 |
| `codex/advanced-rgb-agents` | [#103](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/103) MERGED | `70243c4e6f376624dc538b3e10db36c501397765` | 삭제·원격 부재 확인 |
| `codex/advanced-rgb-skill-execution` | [#102](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/102) MERGED | `da18a7b8984fd1404aa03864ade3b0dfa2cd9694` | 삭제·원격 부재 확인 |
| `codex/advanced-scenarios-audit` | [#100](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/100) MERGED | `ca32f280a77b484f299059f381e7ea2c8926850d` | 삭제·원격 부재 확인 |
| `codex/advanced-study-runner` | [#101](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/101) MERGED | `d9b602be499ade024c056a72ed37f8556a0af320` | 삭제·원격 부재 확인 |
| `codex/carry-input-ablation` | [#82](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/82) MERGED | `c378fedbdf515093c7fe7652a9bbf715c6e988f4` | 삭제·원격 부재 확인 |
| `codex/carry-resolution-sweep` | [#85](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/85) MERGED | `c9b60b759531d89b9bfddd3ef39933a1f530c1e2` | 삭제·원격 부재 확인 |
| `codex/colab-carry-training` | [#84](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/84) MERGED | `f249d4d04b374580fced5615f4e1037f74d42f2c` | 삭제·원격 부재 확인 |
| `codex/colab-simulation` | [#86](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/86) MERGED | `bad9332051d5201c583d06e4c1984802120b9e0d` | 삭제·원격 부재 확인 |
| `codex/experiment-review` | [#81](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/81) MERGED | `174a33b0b6024b3fe45eb87b8db7f7e8ea2797c6` | 삭제·원격 부재 확인 |
| `codex/jev-direct-motion` | [#80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/80) MERGED | `ed4b21b45cb2458728cea3460fd66d85e44e1ea7` | 삭제·원격 부재 확인 |
| `codex/jev-execution-shadow` | [#77](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/77) MERGED | `821be3bc904b04c8f17957f62863de6bd3991c4c` | 삭제·원격 부재 확인 |
| `codex/merge-approved-prs-20260921` | [#87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/87) MERGED | `547b91988354ff39c5a97e5cfd4fa52e6f05dae4` | 삭제·원격 부재 확인 |
| `codex/multi-object-rgb-execution` | [#74](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/74) MERGED | `e64ef6cc80b71f9c04ae2dd3bd707354376b31d5` | 삭제·원격 부재 확인 |
| `codex/multi-object-scene-admission` | [#73](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/73) MERGED | `cc2a69a7090ad007bb76bf306e1fedd4783c1fb5` | 삭제·원격 부재 확인 |
| `codex/multi-object-task-protocol` | [#72](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/72) MERGED | `ec793c89062d1afd04b363ac7eb5c17110a4b53b` | 삭제·원격 부재 확인 |
| `codex/r0-r1-information-boundary-audit` | [#94](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/94) MERGED | `5f4a7ef98423fc35696198a2d1157ff3b364a237` | 삭제·원격 부재 확인 |
| `codex/r2-rgb-execution-port` | [#95](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/95) MERGED | `79f026261892dba84cbf81ae014b2212ec8927db` | 삭제·원격 부재 확인 |
| `codex/r3-rgb-communication-runtime` | [#97](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/97) MERGED | `3d13485be9eca77a10602f1969d60c6f8e0fc129` | 삭제·원격 부재 확인 |
| `codex/r4-r6-rgb-communication-evaluation` | [#96](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/96) MERGED | `b1f1d9f7ba16c82c05c70f0d6b21143e6391031a` | 삭제·원격 부재 확인 |
| `codex/research-advanced-integration` | [#99](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/99) MERGED | `6588dafc78e7ad8b70868b00611782b6a6379584` | 삭제·원격 부재 확인 |
| `codex/research-todo-20260922` | [#93](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/93) MERGED | `e4c5d96d79cbe24db6d79f9a0a991a31ef089448` | 삭제·원격 부재 확인 |
| `kiro/decisions-0926` | [#204](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/204) MERGED | `0d3eef1886f6888e3909f3ccaa4759307894b21d` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/disk-apply-0926` | [#231](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/231) MERGED | `207586fc6ee554f55e8f43265ba376b1242ecb11` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/markerless-research` | [#210](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/210) MERGED | `9a725092be29d538d08efdf0788986fb276a7a4c` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/memory-literature` | [#230](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/230) MERGED | `3174c2f8882bf3dfbfb211be64f3f02023d762d8` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/records-owncam-review` | [#196](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/196) MERGED | `6a7442c30720b264af13bca62e0da10fd9895467` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/references-0926` | [#228](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/228) MERGED | `bdcaf2a3aed229f7eb270b2e7a7ca5099d349439` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/tb-0925` | [#183](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/183) MERGED | `8527b864c622bdb8707d1835c977c5aa6359305b` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-eval-topcam` | [#232](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/232) MERGED | `f5ae83a3c795f84d94145821396a06c627d547a9` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-m2-pair-v3` | [#205](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/205) MERGED | `6990a6ed6654277747490979c35c6e4736fe6bec` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-noslip-audit` | [#189](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/189) MERGED | `63ad9da318a9a0861ffd2df9b2cd176c8a31fc52` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-pilot-records` | [#238](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/238) MERGED | `2ff15d93abfe8e0ad5ad286f6541fd798c5e3fa4` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-scenario-feasibility` | [#202](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/202) MERGED | `8f2aa31db53e4c65990e3ee82e764060edfd6ff4` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-sim-cost` | [#186](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/186) MERGED | `6be139590336bf281af912145740c9766a180019` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-study-contract` | [#187](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/187) MERGED | `8587bb9017c035ab2a043194ccd7b2e656bfb232` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-study-eval` | [#185](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/185) MERGED | `a68ce05683cd2c530c9b7ac34e2b1223ba4fea00` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-study-protocol` | [#184](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/184) MERGED | `e8c80eb093d66c99b35a49b3f030869ad1819abf` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |
| `kiro/zone-vision-loc-v3` | [#233](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/233) MERGED | `35890c55c4bf26d2e158481ff8ca8d492847c491` | 실행 전 제외(SHA 불일치/부재)·최종 부재 확인 |

## 결과와 확인 범위

| 항목 | 결과 |
|---|---|
| 등록 작업 폴더 | 시작·최종 모두 82개(기본 체크아웃 포함) |
| 정리 시도 | 보호·열린 PR·미병합·사용·최근 수정·미커밋 조건을 먼저 제외한 49개 |
| 정리 완료 | 0개 |
| 무시된 자료 이동 | 0파일·0바이트. 이동한 `outputs/` 경로 없음 |
| 원격 브랜치 삭제 | 본 작업 24개. 별도 제외 42개도 최종 부재만 확인 |
| 원시 자료(raw) | 삭제·덮어쓰기·압축·외부 이동 없음 |
| 물리·시뮬레이션·모델 호출 | 실행하지 않음 |
| PR | 이 기록만 초안(draft)으로 제출. 병합하지 않음 |

샌드박스에서 `lsof -n -P -w -F pcfn`은 성공했고 `ps -ww -Ao pid=,command=`는 `PermissionError: [Errno 1] Operation not permitted: 'ps'`로 차단됐다. 따라서 열린 파일·현재 폴더 사용을 발견하지 못한 경로도 명령줄 사용 여부는 **미확인**이다. 지정된 정리 명령 49회 모두 이 검사에서 종료 코드 1로 중단됐고, `retire_checks` 단계에서 실패해 자료 이동과 작업 폴더 제거까지 진행하지 않았다. 처음 같은 후보에 시행한 진단 1회도 같은 오류였다. 안전 검사를 끄거나 도구를 수정하지 않았다.

사용자 보호 목록 11개는 모두 유지했다: `v6h-register`, `v6h-fixcls`, `stall-d1`, `proc-measure`, `proc-research`, `e2e-readiness`, `housekeeping`, `replay-v6h1`, `rev292`, `rev293`, `b-v6h-gain`. 폴더의 PR이 닫혔더라도 아직 미병합인 `claude-claudemd`(#247), PR 없는 미병합 `b-v6h-gain-run`은 보고만 하고 보관 브랜치(archive)를 만들지 않았다.

이 기록은 시점이 있는 조사다. 다른 작업이 병행되므로 파일 시각·프로세스·PR·원격 상태의 측정 시점이 다르다. PR 표는 결과 확인 직전 재조회 상태를 사용한다. `lsof`와 파일 목록은 시작~파일 조사 종료 구간의 관측이며, 경과 시간은 파일 조사 종료를 기준으로 계산했다. 마지막 수정 시각은 파일·디렉터리의 수정 시각(mtime)과 해당 작업 폴더의 Git index·HEAD·logs/HEAD 중 최댓값이다. Git 상태 조회는 `--no-optional-locks`를 사용했다.

## 전체 작업 폴더 결과표

경로 축약: `ugrp`는 `/Users/changmin/projects/ugrp`, 나머지는 `/Users/changmin/projects/ugrp-wt/<이름>`이다. `lsof`의 사용 수는 해당 경로 안에 현재 폴더(cwd)나 열린 파일(open file)을 가진 프로세스(PID) 수다. 대표 PID 세 개까지만 표에 적고 전체 PID·실행 파일명은 로컬 조사 JSON에 보존했다. 사용 수 0은 명령줄까지 포함한 유휴 판정이 아니다. 모든 행의 `ps` 검사는 미확인이다.

| 작업 폴더 | 브랜치 / HEAD | PR 상태 | 마지막 수정(KST) / 경과 분 | lsof 사용 | 무시된 outputs/ 비어 있지 않음 | 처리 / 유지 이유 |
|---|---|---|---|---|---|---|
| `ugrp` | `main` | 없음 | 09-30 19:14:59 / 1.7 | 35개; PID 28231, 28468, 30464 등 | 예; 2,541,673파일 / 76,007,201,022 B | 유지; 기본 체크아웃; 최근 60분 내 수정; lsof에서 사용 확인 |
| `b-v6h-gain` | `claude/b-v6h-gain` | [#285](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/285) OPEN | 09-30 16:08:54 / 187.8 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 열린 PR; 미병합: 보고만 |
| `b-v6h-gain-run` | `claude/b-v6h-gain-run` | 없음 | 09-30 09:17:02 / 599.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 미병합: 보고만 |
| `carry-relocalization-b1` | `claude/carry-relocalization-b1` | [#279](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/279) MERGED | 09-29 22:41:24 / 1235.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `carry-relocalization-design` | `claude/carry-relocalization-design` | [#277](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/277) MERGED | 09-29 20:21:00 / 1375.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `carry-x-bias` | `claude/carry-x-bias` | [#284](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/284) MERGED | 09-30 05:15:04 / 841.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `chainfix-0930` | `claude/chain-hardlimit-order` | [#288](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/288) MERGED | 09-30 11:13:09 / 483.6 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `claude-claudemd` | `claude/claude-md-reference-first` | [#247](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/247) CLOSED | 09-28 10:36:25 / 3400.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 미병합: 보고만 |
| `claude-flaky-guard` | `claude/fix-flaky-worker-guard` | [#268](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/268) MERGED | 09-29 11:06:45 / 1930.0 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 미커밋/미추적 1항목 |
| `claude-llm-driver` | `claude/zone-llm-driver` | [#256](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256) MERGED | 09-29 03:56:34 / 2360.2 | 11개; PID 58297, 58321, 58811 등 | 예; 2파일 / 2,805 B | 유지; lsof에서 사용 확인 |
| `claude-masterpi-v3` | `claude/masterpi-visual-v3` | [#249](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/249) MERGED | 09-29 07:00:24 / 2176.3 | 11개; PID 13800, 13802, 13803 등 | 예; 10파일 / 1,268,574 B | 유지; lsof에서 사용 확인 |
| `claude-v6-boot` | `claude/zone-pair-v6-boot` | [#261](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/261) MERGED | 09-29 02:48:56 / 2427.8 | 11개; PID 12243, 12244, 12245 등 | 아니오(비어 있음) | 유지; lsof에서 사용 확인 |
| `claude-v6c` | `claude/zone-pair-v6c` | [#263](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/263) MERGED | 09-29 07:40:56 / 2135.8 | 15개; PID 16154, 16171, 16505 등 | 아니오(폴더 없음) | 유지; lsof에서 사용 확인 |
| `claude-v6d-align` | `claude/pair-v6d-align` | 없음 | 09-29 08:42:35 / 2074.1 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 미커밋/미추적 11항목 |
| `claude-v6d-reg` | `claude/pair-v6d-reg` | [#265](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/265) MERGED | 09-29 10:44:53 / 1951.8 | 없음(명령줄 미확인) | 아니오(비어 있음) | 유지; 미커밋/미추적 1항목 |
| `claude-v6e-carry` | `claude/pair-v6e-carry` | 없음 | 09-29 17:25:01 / 1551.7 | 없음(명령줄 미확인) | 아니오(비어 있음) | 유지; 미커밋/미추적 3항목 |
| `claude-v6e-place` | `claude/pair-v6e-place` | 없음 | 09-29 11:16:47 / 1919.9 | 없음(명령줄 미확인) | 예; 10파일 / 1,271,788 B | 유지; 미커밋/미추적 1항목 |
| `claude-v6g-dev` | `claude/pair-v6g` | [#278](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/278) MERGED | 09-29 22:06:36 / 1270.1 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `claude-vis6` | `claude/vis6-recipe1` | [#253](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/253) MERGED | 09-28 14:46:44 / 3150.0 | 7개; PID 12661, 12782, 13547 등 | 예; 2파일 / 188,486 B | 유지; lsof에서 사용 확인 |
| `codex-ci-split` | `codex/ci-offline-split` | [#267](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/267) MERGED | 09-29 10:42:39 / 1954.1 | 7개; PID 36760, 36777, 37129 등 | 예; 5파일 / 70,722 B | 유지; lsof에서 사용 확인; 미커밋/미추적 2항목 |
| `codex-masterpi-specs` | `codex/masterpi-public-specs` | [#258](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/258) MERGED | 09-29 00:13:02 / 2583.7 | 7개; PID 46002, 46017, 46345 등 | 아니오(폴더 없음) | 유지; lsof에서 사용 확인 |
| `codex-memory-v3` | `codex/zone-owncam-memory-v3` | [#234](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/234) MERGED | 09-27 12:14:28 / 4742.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `codex-multiturn` | `codex/zone-study-multiturn` | [#245](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/245) MERGED | 09-28 08:22:23 / 3534.3 | 71개; PID 456, 458, 459 등 | 예; 42파일 / 5,323,022 B | 유지; lsof에서 사용 확인 |
| `codex-pair-beamrel` | `codex/zone-pair-beam-relative` | [#246](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/246) MERGED | 09-28 16:01:25 / 3075.3 | 35개; PID 2753, 2754, 2755 등 | 아니오(비어 있음) | 유지; lsof에서 사용 확인 |
| `codex-pair-executor` | `codex/zone-pair-executor` | [#235](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/235) MERGED | 09-27 16:09:15 / 4507.5 | 없음(명령줄 미확인) | 예; 5파일 / 637 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `codex-pair-grasp` | `codex/zone-pair-grasp-relook` | [#240](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/240) MERGED | 09-28 11:16:29 / 3360.2 | 120개; PID 4532, 4533, 4534 등 | 예; 9파일 / 1,159 B | 유지; lsof에서 사용 확인 |
| `codex-pair-parity` | `codex/zone-pair-parity` | [#244](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/244) MERGED | 09-28 00:34:14 / 4002.5 | 34개; PID 44612, 44614, 44615 등 | 아니오(폴더 없음) | 유지; lsof에서 사용 확인 |
| `codex-probe` | `codex/sandbox-probe` | 없음 | 09-30 15:04:24 / 252.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `codex-sim-speed-fix` | `codex/sim-speed-fix` | [#236](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/236) MERGED | 09-27 11:36:20 / 4780.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `codex-vision-loc-v4` | `codex/vision-loc-v4` | [#242](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/242) MERGED | 09-28 10:04:50 / 3431.9 | 19개; PID 40982, 40997, 41333 등 | 예; 145파일 / 67,557,060 B | 유지; lsof에서 사용 확인 |
| `codex-vision-loc-v5` | `codex/vision-loc-v5` | [#243](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/243) MERGED | 09-28 10:07:44 / 3429.0 | 19개; PID 2444, 2460, 2794 등 | 예; 76파일 / 44,258,791 B | 유지; lsof에서 사용 확인 |
| `docs-0930` | `claude/docs-0930-fix` | [#289](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/289) MERGED | 09-30 11:13:57 / 482.8 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `door-guard-relax` | `claude/door-guard-relax` | [#281](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/281) MERGED | 09-30 03:21:01 / 955.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `door-relax-envelope` | `claude/door-relax-envelope` | [#283](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/283) MERGED | 09-30 04:48:34 / 868.2 | 3개; PID 26578, 26580, 26582 | 아니오(폴더 없음) | 유지; lsof에서 사용 확인 |
| `door-ultrasonic-sweep` | `claude/door-ultrasonic-sweep` | [#280](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/280) MERGED | 09-29 23:06:19 / 1210.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `e2e-readiness` | `codex/e2e-readiness` | 없음 | 09-30 19:07:19 / 9.4 | 7개; PID 79380, 79382, 79733 등 | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 최근 60분 내 수정; lsof에서 사용 확인 |
| `followup-docs` | `codex/followup-docs` | [#274](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/274) MERGED | 09-29 17:04:33 / 1572.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `housekeeping` | `codex/housekeeping-0930` | 없음 | 09-30 19:15:04 / 1.7 | 8개; PID 79408, 79409, 79737 등 | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 최근 60분 내 수정; lsof에서 사용 확인; 미커밋/미추적 1항목 |
| `kiro-final-map` | `kiro/final-map-scenario-v2` | [#255](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/255) MERGED | 09-28 13:33:00 / 3223.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-ko-pilot-fix` | `kiro/zone-ko-pilot-fixes` | [#188](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/188) MERGED | 09-27 22:57:57 / 4098.8 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-m2-pair-s2c-frozen` | 분리 HEAD(detached) `ca44f66f555d` | 없음 | 09-27 16:06:16 / 4510.5 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-map-v3` | `kiro/zone-map-v3` | [#208](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/208) MERGED | 09-27 15:33:51 / 4542.9 | 없음(명령줄 미확인) | 아니오(비어 있음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-own-executor` | `kiro/zone-own-executor` | [#206](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/206) MERGED | 09-27 11:49:47 / 4766.9 | 없음(명령줄 미확인) | 아니오(비어 있음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-own-perception` | `kiro/zone-own-perception` | [#193](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/193) MERGED | 09-27 22:24:10 / 4132.6 | 없음(명령줄 미확인) | 예; 13,497파일 / 259,124,954 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-owncam-memory` | `kiro/zone-owncam-memory` | [#211](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/211) MERGED | 09-27 15:50:11 / 4526.6 | 없음(명령줄 미확인) | 예; 4파일 / 1,072,846 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-records-0926b` | `kiro/records-0926b` | [#192](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/192) MERGED | 09-27 22:24:23 / 4132.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-report-draft` | `kiro/report-draft` | [#191](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/191) MERGED | 09-27 22:24:24 / 4132.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-sim-speed` | `kiro/sim-speed` | [#209](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/209) MERGED | 09-27 08:59:43 / 4937.0 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-study-core` | `kiro/zone-study-core` | [#194](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/194) MERGED | 09-27 16:03:24 / 4513.3 | 없음(명령줄 미확인) | 예; 35파일 / 2,475,713 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-study-integration` | `kiro/zone-study-integration` | [#229](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/229) MERGED | 09-27 15:48:37 / 4528.1 | 없음(명령줄 미확인) | 아니오(비어 있음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-study-scenarios` | `kiro/zone-study-scenarios` | [#190](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/190) MERGED | 09-27 16:06:17 / 4510.5 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-tb-loop` | `kiro/tb-owncam-loop` | [#195](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/195) MERGED | 09-27 22:41:47 / 4115.0 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-tb-perc` | `kiro/tb-perception-noslip` | [#199](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/199) MERGED | 09-27 22:23:57 / 4132.8 | 없음(명령줄 미확인) | 예; 92파일 / 1,694,543 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-teacher-fix` | `kiro/zone-teacher-fix` | [#207](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/207) MERGED | 09-27 22:23:15 / 4133.5 | 없음(명령줄 미확인) | 예; 1,615파일 / 293,164,190 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-vision-loc` | `kiro/zone-vision-loc` | [#227](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/227) MERGED | 09-27 15:23:04 / 4553.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `kiro-vision-worker` | `kiro/zone-vision-worker` | [#237](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/237) MERGED | 09-27 12:22:24 / 4734.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `l1-axial-offset` | `claude/l1-axial-offset` | [#286](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/286) MERGED | 09-30 09:13:48 / 602.9 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `merge-229` | 분리 HEAD(detached) `6a9b680b5645` | 없음 | 09-27 22:16:37 / 4140.1 | 없음(명령줄 미확인) | 예; 8파일 / 2,300,264 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `merge-235` | 분리 HEAD(detached) `8120aa47a94d` | 없음 | 09-27 21:24:31 / 4192.2 | 없음(명령줄 미확인) | 예; 8파일 / 2,278,669 B | 유지; 정리 명령 거부: ps 권한 오류 |
| `pair-chain-probe` | `claude/pair-chain-probe` | [#270](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/270) MERGED | 09-29 13:02:04 / 1814.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `pair-passage-map` | `claude/pair-passage-map` | [#271](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/271) MERGED | 09-29 14:29:08 / 1727.6 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `probe-videos` | `claude/probe-videos` | [#273](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/273) MERGED | 09-29 16:12:31 / 1624.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `proc-measure` | `codex/process-measure` | [#296](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/296) OPEN | 09-30 19:16:07 / 0.6 | 6개; PID 73296, 73712, 73713 등 | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 최근 60분 내 수정; lsof에서 사용 확인; 미커밋/미추적 185항목 |
| `proc-research` | `codex/process-research` | [#295](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/295) OPEN | 09-30 19:00:26 / 16.3 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 열린 PR; 미병합: 보고만; 최근 60분 내 수정 |
| `relocalization-audit` | `claude/relocalization-audit` | [#276](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/276) MERGED | 09-29 19:54:08 / 1402.6 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `render-profile` | `claude/render-profile` | [#272](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/272) MERGED | 09-29 16:01:35 / 1635.1 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `replay-v6h1` | `claude/v6h1-acceptance-run` | 없음 | 09-30 19:08:08 / 8.6 | 6개; PID 81180, 81182, 82123 등 | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 미병합: 보고만; 최근 60분 내 수정; lsof에서 사용 확인 |
| `rev292` | `codex/review-292` | 없음 | 09-30 18:04:35 / 72.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 미병합: 보고만 |
| `rev293` | `codex/review-293-294` | 없음 | 09-30 18:02:01 / 74.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 미병합: 보고만 |
| `seg-lightfloor` | `claude/seg-lightfloor` | [#282](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/282) MERGED | 09-30 03:19:12 / 957.5 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `stall-d1` | `codex/stall-d1-prereg` | [#293](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/293) OPEN | 09-30 18:45:34 / 31.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 열린 PR; 미병합: 보고만; 최근 60분 내 수정 |
| `stall-research-0930` | `claude/stall-detect-research` | [#291](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/291) MERGED | 09-30 15:51:03 / 205.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `status-refresh` | `claude/status-refresh` | [#269](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/269) MERGED | 09-29 12:55:32 / 1821.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `ultrasonic-input` | `claude/ultrasonic-input` | [#275](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/275) MERGED | 09-29 19:40:00 / 1416.7 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `v6h-classify` | `codex/v6h-classify` | [#290](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/290) MERGED | 09-30 15:36:34 / 220.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `v6h-fixcls` | `codex/v6h-classifier-fixes` | 없음 | 09-30 19:15:54 / 0.8 | 7개; PID 79393, 79395, 79730 등 | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 미병합: 보고만; 최근 60분 내 수정; lsof에서 사용 확인; 미커밋/미추적 7항목 |
| `v6h-prereg-upd` | `codex/v6h-prereg-update` | [#294](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/294) MERGED | 09-30 17:15:34 / 121.2 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `v6h-register` | `codex/pair-v6h-register` | [#292](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/292) OPEN | 09-30 18:44:50 / 31.9 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 사용자 보호 대상; 열린 PR; 미병합: 보고만; 최근 60분 내 수정 |
| `zone-m2-pair-s1-frozen` | 분리 HEAD(detached) `3fdf0112f7e9` | 없음 | 09-27 16:06:17 / 4510.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `zone-m2-pair-s2-frozen` | 분리 HEAD(detached) `fa682a6d9c6d` | 없음 | 09-27 16:06:17 / 4510.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `zone-m2-pair-s2b-frozen` | 분리 HEAD(detached) `ed15489ab5e8` | 없음 | 09-27 16:06:18 / 4510.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |
| `zone-m2-pair-s3-frozen` | 분리 HEAD(detached) `5f748734fc8f` | 없음 | 09-27 16:06:18 / 4510.4 | 없음(명령줄 미확인) | 아니오(폴더 없음) | 유지; 정리 명령 거부: ps 권한 오류 |

## 정리 명령 거부 기록

각 후보에 `python3 scripts/agent_worktree.py retire <전체 경로> --execute`만 실행했다. 모두 자료 이동 전 같은 `ps` 권한 오류로 종료했다. 이동 영수증(RETIRED.json)과 이동 목록(MANIFEST.tsv)은 본 작업에서 생성하지 않았다.

| 작업 폴더 | 실행 시각(KST) | 종료 코드 | 자료 이동 경로 | 거부 사유 |
|---|---|---|---|---|
| `carry-relocalization-b1` | 19:18:28 | 1 | 없음 | `ps` 실행 권한 오류 |
| `carry-relocalization-design` | 19:18:32 | 1 | 없음 | `ps` 실행 권한 오류 |
| `carry-x-bias` | 19:18:35 | 1 | 없음 | `ps` 실행 권한 오류 |
| `chainfix-0930` | 19:18:39 | 1 | 없음 | `ps` 실행 권한 오류 |
| `claude-v6g-dev` | 19:18:42 | 1 | 없음 | `ps` 실행 권한 오류 |
| `codex-memory-v3` | 19:18:44 | 1 | 없음 | `ps` 실행 권한 오류 |
| `codex-pair-executor` | 19:18:48 | 1 | 없음 | `ps` 실행 권한 오류 |
| `codex-probe` | 19:18:51 | 1 | 없음 | `ps` 실행 권한 오류 |
| `codex-sim-speed-fix` | 19:18:54 | 1 | 없음 | `ps` 실행 권한 오류 |
| `docs-0930` | 19:18:57 | 1 | 없음 | `ps` 실행 권한 오류 |
| `door-guard-relax` | 19:18:59 | 1 | 없음 | `ps` 실행 권한 오류 |
| `door-ultrasonic-sweep` | 19:19:02 | 1 | 없음 | `ps` 실행 권한 오류 |
| `followup-docs` | 19:19:06 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-final-map` | 19:19:09 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-ko-pilot-fix` | 19:19:12 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-m2-pair-s2c-frozen` | 19:19:14 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-map-v3` | 19:19:17 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-own-executor` | 19:19:20 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-own-perception` | 19:19:23 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-owncam-memory` | 19:19:26 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-records-0926b` | 19:19:29 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-report-draft` | 19:19:32 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-sim-speed` | 19:19:35 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-study-core` | 19:19:38 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-study-integration` | 19:19:41 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-study-scenarios` | 19:19:44 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-tb-loop` | 19:19:47 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-tb-perc` | 19:19:50 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-teacher-fix` | 19:19:53 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-vision-loc` | 19:19:56 | 1 | 없음 | `ps` 실행 권한 오류 |
| `kiro-vision-worker` | 19:20:00 | 1 | 없음 | `ps` 실행 권한 오류 |
| `l1-axial-offset` | 19:20:05 | 1 | 없음 | `ps` 실행 권한 오류 |
| `merge-229` | 19:20:09 | 1 | 없음 | `ps` 실행 권한 오류 |
| `merge-235` | 19:20:14 | 1 | 없음 | `ps` 실행 권한 오류 |
| `pair-chain-probe` | 19:20:19 | 1 | 없음 | `ps` 실행 권한 오류 |
| `pair-passage-map` | 19:20:24 | 1 | 없음 | `ps` 실행 권한 오류 |
| `probe-videos` | 19:20:29 | 1 | 없음 | `ps` 실행 권한 오류 |
| `relocalization-audit` | 19:20:34 | 1 | 없음 | `ps` 실행 권한 오류 |
| `render-profile` | 19:20:39 | 1 | 없음 | `ps` 실행 권한 오류 |
| `seg-lightfloor` | 19:20:44 | 1 | 없음 | `ps` 실행 권한 오류 |
| `stall-research-0930` | 19:20:49 | 1 | 없음 | `ps` 실행 권한 오류 |
| `status-refresh` | 19:20:54 | 1 | 없음 | `ps` 실행 권한 오류 |
| `ultrasonic-input` | 19:21:00 | 1 | 없음 | `ps` 실행 권한 오류 |
| `v6h-classify` | 19:21:06 | 1 | 없음 | `ps` 실행 권한 오류 |
| `v6h-prereg-upd` | 19:21:16 | 1 | 없음 | `ps` 실행 권한 오류 |
| `zone-m2-pair-s1-frozen` | 19:21:24 | 1 | 없음 | `ps` 실행 권한 오류 |
| `zone-m2-pair-s2-frozen` | 19:21:34 | 1 | 없음 | `ps` 실행 권한 오류 |
| `zone-m2-pair-s2b-frozen` | 19:21:39 | 1 | 없음 | `ps` 실행 권한 오류 |
| `zone-m2-pair-s3-frozen` | 19:21:43 | 1 | 없음 | `ps` 실행 권한 오류 |

## 남아 있는 원격 브랜치

다음은 최종 `git ls-remote --heads origin`에서 확인한 에이전트 접두사 브랜치다. 조사 이후 다른 작업이 정리한 브랜치는 이 표에 넣지 않고, 본 작업의 삭제 수에도 합산하지 않았다. 기본 `main`과 기타 접두사 브랜치는 정리 범위 밖이다. 작업 폴더가 연결된 브랜치는 `ps` 확인 실패 또는 사용·보호 조건 때문에 이 작업에서 삭제하지 않았다.

| 원격 브랜치 | PR 상태 | 유지 이유 |
|---|---|---|
| `claude/archive-v6c-fixtest-0929` | 없음 | MERGED PR 없음 |
| `claude/b-v6h-gain` | [#285](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/285) OPEN | MERGED PR 없음; 열린 PR; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `claude/busy-pasteur-lioq74` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `claude/claude-md-reference-first` | [#247](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/247) CLOSED | MERGED PR 없음; origin/main에 전체 포함되지 않음; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `claude/team-recovery-longer-backoff` | [#153](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/153) MERGED | origin/main에 전체 포함되지 않음 |
| `claude/zone-dispatch-validation` | [#152](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/152) MERGED | origin/main에 전체 포함되지 않음 |
| `claude/zone-team-a2-dev` | 없음 | MERGED PR 없음 |
| `codex/act-render-speed` | 없음 | MERGED PR 없음 |
| `codex/advanced-rgb-clock-validation` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/advanced-rgb-validation` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-a3-fresh-audit-755dca3-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-a3-fresh-audit-de69eb3-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-communication-observer-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-dispatch-process-perception-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-dispatch-top-pipeline-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-pr137-main-integration-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-realtime-owner-commit-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-realtime-stage-continuity-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/archive-rgb-common-physical-recovery-0926` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/d3-local-validation` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/direct-gemini-api-key` | [#17](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/17) CLOSED | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/dispatch-adaptive-recovery` | [#67](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/67) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/local-gemini-proxy` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/pair-grasp-endurance` | [#52](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/52) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/pair-grasp-spacing` | [#48](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/48) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/pair-loaded-navigation` | [#44](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/44) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/pair-terrain-examples` | [#45](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/45) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/pair-transport-robustness` | [#47](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/47) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/pair-v6h-register` | [#292](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/292) OPEN | MERGED PR 없음; 열린 PR; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `codex/pair-vision-recovery` | [#46](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/46) MERGED | origin/main에 전체 포함되지 않음 |
| `codex/process-measure` | [#296](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/296) OPEN | 조사 시작 이후 나타난 브랜치: 건드리지 않음 |
| `codex/process-research` | [#295](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/295) OPEN | MERGED PR 없음; 열린 PR; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `codex/repository-organization` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/review-292` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `codex/review-293-294` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `codex/rgb-common-physical-recovery` | [#120](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/120) CLOSED | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/rgb-varied-start-tolerance` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |
| `codex/stall-d1-prereg` | [#293](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/293) OPEN | MERGED PR 없음; 열린 PR; origin/main에 전체 포함되지 않음; 사용자 보호 대상 worktree; ps 차단으로 연결된 worktree 사용 여부 미확인 |
| `codex/v6h1-acceptance` | 없음 | MERGED PR 없음; origin/main에 전체 포함되지 않음 |

## 검증과 남은 문제

문서와 조사 자료를 대조하는 검사 10개(표준 라이브러리 unittest)가 모두 통과했다. 전체 작업 폴더 표의 누락·중복, 삭제 전 목록 66개, 무시된 outputs/ 표시, 보호 목록 보존, 미병합 폴더 보존, 시도 후보의 병합·유휴 조건, 자료 이동 전 정리 중단과 등록 경로 보존, 원격 삭제 조건, 삭제 후 실제 원격 부재, 원본 해시와 보고 수치를 확인했다. `git diff --check`와 `python3 scripts/check_media_size.py --base origin/main`도 통과했다. 검증은 이 관리 기록과 실제 원격 상태에 한정되며 정리 도구 회귀시험 통과를 뜻하지 않는다. 검사 스크립트와 출력은 로컬 원본 폴더의 `validate.py`, `validation.txt`에 보존했다.

공용 시험 잠금은 다른 에이전트의 `claude/v6h1-acceptance-run`이 사용 중이다. 기존 정리 도구 회귀시험(pytest)은 시작하지 않았다. 새 시뮬레이션·학습·평가 결과가 없는 관리 기록이므로 TensorBoard 변환·서버·새 화면을 만들지 않았다. Google Drive는 프로젝트 예외에 따라 사용하지 않았다.

남은 작업: `ps`를 허용하는 작업 환경에서 49개 후보의 PR·사용 여부·수정 시각을 다시 확인한 뒤 동일 정리 명령을 시행해야 한다. 본 작업에서는 작업 폴더 디스크 절감량이 0이며, 자료 보존 위치도 그대로다. 원격 브랜치 삭제를 로컬 작업 폴더나 원시 자료의 절감량으로 환산하지 않는다.

## 로컬 원본과 해시

조사와 명령 출력은 `/Users/changmin/projects/ugrp/outputs/housekeeping-0930/`에 저장했다. 원본은 로컬 보관이며 원격 백업으로 표시하지 않는다. 아래 해시는 기록 작성 시점의 파일 바이트 전체에 대한 SHA-256이다. 명령줄 전체나 인증정보는 수집·기록하지 않았다.

| 원본 | SHA-256 |
|---|---|
| `inventory-before.json` | `b1978d77df543977e92258694dcc94cee04f06fc97e2d4e9dc5fb78a096067f6` |
| `branch-deletions.json` | `a07b7c5a0f52b7cd4763f44b8abf4a944dcc8a5e3624232f7ab76a20ead2a90b` |
| `branch-delete-push.txt` | `41891e80858a0d3b05abaa641ef3b28a78cf280d17dcfff2e8be85faa6750908` |
| `retire-attempts.json` | `ba6013148ead184f7abc4cf10ddbd7b02170d5ca64825d928f7a84d1933b6a4a` |
| `worktrees-after.txt` | `b5d391bbca8fd3b1438a9999aeb8c4efa36eb78ad5b7f6d139c5db4ac0c3779d` |
| `remote-heads-after.txt` | `44fca40c0b4f4a724d78925d1b4f5e837c56b065426d96cf9f51a76c141c835c` |
| `prs-after.json` | `8ed29db5f1507240b8626d6cbbf82c425a11e2ce3aa9ad9c90140dd51ec3d740` |

## 참고 자료

- [작업 지침](../../AGENTS.md): 디스크 사용, 결과 보존, 병행 작업.
- [개발·검증 절차](../../CONTRIBUTING.md): 검증·공용 시험 잠금.
- [디스크 관리](../../docs/disk_management.md): §7 안전한 정리 절차와 보존 경로.
- [정리 도구](../../scripts/agent_worktree.py): `retire_checks`, `move_verified`, `cmd_retire`.
- [사용 여부 검사](../../scripts/worktree_guard.py): `processes_using`, `processes_naming`, `recent_activity`.
- [관련 자동 검사](../../tests/test_agent_worktree.py)·[디스크 보고 검사](../../tests/test_disk_report.py): 이번에 코드 변경 없음, pytest 미실행.

Generated with Codex

## Claude-side retire results (2026-09-30)

위 49개 후보를 Claude 쪽(`ps` 사용 가능)에서 `python3 scripts/agent_worktree.py retire <경로> --execute`로만 다시 정리했다. `git worktree remove`·`rm -rf`는 쓰지 않았고, 프로세스 종료·물리 실행·원격 브랜치 push는 없다.

| 항목 | 결과 |
|---|---|
| 정리됨(retired) | 49개 (거부 0, 건너뜀 0) |
| 병합 확인 | 47개는 HEAD가 `origin/main`의 조상, `v6h-classify`(#290)·`v6h-prereg-upd`(#294)는 `--pr`로 병합 PR 머리 커밋 일치를 확인(스쿼시/리베이스 병합) |
| 이동한 무시 자료 | 31,380개 / 688,865,284 B (아래 표) |
| 추정 checkout 해제 | 약 19.8 GiB (스크립트 추정합 21,259,223,040 B) |
| 프로젝트 합계(`disk_report.py`) | 109.44 GiB → 90.54 GiB, worktree 28.63 → 9.02 GiB, 볼륨 여유 53 → 71 GiB |
| 보호 목록·최근 60분·열린 PR 폴더 | 후보에 없었고 건드리지 않음 |

이동한 자료는 `same-path`면 기본 체크아웃의 같은 상대 경로로, 아니면 `outputs/retired-worktrees/<라벨>/` 아래로 갔다. 영수증(RETIRED.json)·MANIFEST.tsv는 각 `outputs/retired-worktrees/<라벨>/`에 있다.

| 작업 폴더 | 결과 | 병합 근거 | 이동 자료 | 이동 경로 | 영수증 |
|---|---|---|---|---|---|
| `carry-relocalization-b1` | 정리됨(retired) | HEAD 6966fa0b88dc is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-carry-relocalization-b1` |
| `carry-relocalization-design` | 정리됨(retired) | HEAD 9973a68279d8 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-carry-relocalization-design` |
| `carry-x-bias` | 정리됨(retired) | HEAD fc1b39a5654b is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-carry-x-bias` |
| `chainfix-0930` | 정리됨(retired) | HEAD 8e07eb96d70b is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-chainfix-0930` |
| `claude-v6g-dev` | 정리됨(retired) | HEAD 8def4da14cb7 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-v6g-dev` |
| `codex-memory-v3` | 정리됨(retired) | HEAD ad8b9babdd87 is an ancestor of origin/main | 1개 / 136 B | `outputs/retired-worktrees/codex-memory-v3/MUJOCO_LOG.TXT` | `outputs/retired-worktrees/codex-memory-v3` |
| `codex-pair-executor` | 정리됨(retired) | HEAD 07953a2fbc32 is an ancestor of origin/main | 5개 / 637 B | `outputs/retired-worktrees/codex-pair-executor/outputs/simulation-runs` | `outputs/retired-worktrees/codex-pair-executor` |
| `codex-probe` | 정리됨(retired) | HEAD f06d1a7a0805 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/codex-probe` |
| `codex-sim-speed-fix` | 정리됨(retired) | HEAD 92041cdbe017 is an ancestor of origin/main | 9787개 / 2,562,978 B | `outputs/retired-worktrees/codex-sim-speed-fix/tmp` | `outputs/retired-worktrees/codex-sim-speed-fix` |
| `docs-0930` | 정리됨(retired) | HEAD 0abf52528fca is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-docs-0930` |
| `door-guard-relax` | 정리됨(retired) | HEAD 953caa24db0e is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-door-guard-relax` |
| `door-ultrasonic-sweep` | 정리됨(retired) | HEAD ad4441c52087 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-door-ultrasonic-sweep` |
| `followup-docs` | 정리됨(retired) | HEAD 09eec0725a00 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/codex-followup-docs` |
| `kiro-final-map` | 정리됨(retired) | HEAD 4c448f673ed2 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-final-map` |
| `kiro-ko-pilot-fix` | 정리됨(retired) | HEAD 3c9323f0878c is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-ko-pilot-fix` |
| `kiro-m2-pair-s2c-frozen` | 정리됨(retired) | HEAD ca44f66f555d is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-m2-pair-s2c-frozen` |
| `kiro-map-v3` | 정리됨(retired) | HEAD f3edeb967287 is an ancestor of origin/main | 1개 / 107 B | `outputs/retired-worktrees/kiro-map-v3/MUJOCO_LOG.TXT` | `outputs/retired-worktrees/kiro-map-v3` |
| `kiro-own-executor` | 정리됨(retired) | HEAD 7a3d4c85ab17 is an ancestor of origin/main | 1개 / 136 B | `outputs/retired-worktrees/kiro-own-executor/MUJOCO_LOG.TXT` | `outputs/retired-worktrees/kiro-own-executor` |
| `kiro-own-perception` | 정리됨(retired) | HEAD a019d55747a9 is an ancestor of origin/main | 13497개 / 259,124,954 B | `outputs/2026-09-26-held-can`, `outputs/2026-09-26-zone-own-perception`, `outputs/2026-09-26-zone-own-perception-v2`, `outputs/2026-09-26-zone-own-perception-v3`, `outputs/2026-09-26-zone-own-perception-v3-1` | `outputs/retired-worktrees/kiro-own-perception` |
| `kiro-owncam-memory` | 정리됨(retired) | HEAD 00682ef6a2bc is an ancestor of origin/main | 5개 / 1,073,220 B | `outputs/retired-worktrees/kiro-owncam-memory/MUJOCO_LOG.TXT`, `outputs/retired-worktrees/kiro-owncam-memory/outputs/simulation-runs` | `outputs/retired-worktrees/kiro-owncam-memory` |
| `kiro-records-0926b` | 정리됨(retired) | HEAD 71eb25532b8d is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-records-0926b` |
| `kiro-report-draft` | 정리됨(retired) | HEAD 1453a96dad58 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-report-draft` |
| `kiro-sim-speed` | 정리됨(retired) | HEAD 325559eb59f0 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-sim-speed` |
| `kiro-study-core` | 정리됨(retired) | HEAD 71b3dcd13d54 is an ancestor of origin/main | 6117개 / 119,709,984 B | `outputs/proxy-log-exclusive-window-review`, `outputs/retired-worktrees/kiro-study-core/.tmp`, `outputs/retired-worktrees/kiro-study-core/MUJOCO_LOG.TXT`, `outputs/retired-worktrees/kiro-study-core/experiments/2026-09-26-zone-study-offline-smoke/review-r12/preflight-01-readonly/000001-proxy-window.log`, `outputs/retired-worktrees/kiro-study-core/outputs/real_traces`, `outputs/retired-worktrees/kiro-study-core/outputs/sim_traces`, `outputs/retired-worktrees/kiro-study-core/outputs/simulation-runs` | `outputs/retired-worktrees/kiro-study-core` |
| `kiro-study-integration` | 정리됨(retired) | HEAD 059468bbce97 is an ancestor of origin/main | 239개 / 6,953,756 B | `outputs/retired-worktrees/kiro-study-integration/MUJOCO_LOG.TXT`, `outputs/retired-worktrees/kiro-study-integration/tmp` | `outputs/retired-worktrees/kiro-study-integration` |
| `kiro-study-scenarios` | 정리됨(retired) | HEAD 3186100117c4 is an ancestor of origin/main | 2개 / 78 B | `outputs/retired-worktrees/kiro-study-scenarios/.venv-sim`, `outputs/retired-worktrees/kiro-study-scenarios/.venv-sim-worker-mac` | `outputs/retired-worktrees/kiro-study-scenarios` |
| `kiro-tb-loop` | 정리됨(retired) | HEAD d2bf3fa14139 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-tb-loop` |
| `kiro-tb-perc` | 정리됨(retired) | HEAD f6d57383865e is an ancestor of origin/main | 92개 / 1,694,543 B | `outputs/tb-perception-noslip-20260926` | `outputs/retired-worktrees/kiro-tb-perc` |
| `kiro-teacher-fix` | 정리됨(retired) | HEAD 2bada98e9d16 is an ancestor of origin/main | 1615개 / 293,164,190 B | `outputs/tb-teacher-fix-20260926`, `outputs/zone-teacher-fix-20260926` | `outputs/retired-worktrees/kiro-teacher-fix` |
| `kiro-vision-loc` | 정리됨(retired) | HEAD ae3bdb9db592 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-vision-loc` |
| `kiro-vision-worker` | 정리됨(retired) | HEAD ca88782cf1f7 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/kiro-vision-worker` |
| `l1-axial-offset` | 정리됨(retired) | HEAD f0399e458d9b is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-l1-axial-offset` |
| `merge-229` | 정리됨(retired) | HEAD 6a9b680b5645 is an ancestor of origin/main | 9개 / 2,301,148 B | `outputs/retired-worktrees/claude-merge-229/MUJOCO_LOG.TXT`, `outputs/retired-worktrees/claude-merge-229/outputs/simulation-runs` | `outputs/retired-worktrees/claude-merge-229` |
| `merge-235` | 정리됨(retired) | HEAD 8120aa47a94d is an ancestor of origin/main | 9개 / 2,279,417 B | `outputs/retired-worktrees/claude-merge-235/MUJOCO_LOG.TXT`, `outputs/retired-worktrees/claude-merge-235/outputs/simulation-runs` | `outputs/retired-worktrees/claude-merge-235` |
| `pair-chain-probe` | 정리됨(retired) | HEAD 156e31ce7140 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-pair-chain-probe` |
| `pair-passage-map` | 정리됨(retired) | HEAD 7ae944afbc62 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-pair-passage-map` |
| `probe-videos` | 정리됨(retired) | HEAD 09e455d933fe is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-probe-videos` |
| `relocalization-audit` | 정리됨(retired) | HEAD dba562466d1a is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-relocalization-audit` |
| `render-profile` | 정리됨(retired) | HEAD 105e0e8e381a is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-render-profile` |
| `seg-lightfloor` | 정리됨(retired) | HEAD 8bbcab6e2d14 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-seg-lightfloor` |
| `stall-research-0930` | 정리됨(retired) | HEAD ea3c83d02435 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-stall-research-0930` |
| `status-refresh` | 정리됨(retired) | HEAD 485a734a63a2 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-status-refresh` |
| `ultrasonic-input` | 정리됨(retired) | HEAD 859522749e86 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-ultrasonic-input` |
| `v6h-classify` | 정리됨(retired) | PR #290 MERGED with head af6bcdb81b1c (squash or rebase merg | 0개 / 0 B | 없음 | `outputs/retired-worktrees/codex-v6h-classify` |
| `v6h-prereg-upd` | 정리됨(retired) | PR #294 MERGED with head 9a63140edfaa (squash or rebase merg | 0개 / 0 B | 없음 | `outputs/retired-worktrees/codex-v6h-prereg-upd` |
| `zone-m2-pair-s1-frozen` | 정리됨(retired) | HEAD 3fdf0112f7e9 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-zone-m2-pair-s1-frozen` |
| `zone-m2-pair-s2-frozen` | 정리됨(retired) | HEAD fa682a6d9c6d is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-zone-m2-pair-s2-frozen` |
| `zone-m2-pair-s2b-frozen` | 정리됨(retired) | HEAD ed15489ab5e8 is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-zone-m2-pair-s2b-frozen` |
| `zone-m2-pair-s3-frozen` | 정리됨(retired) | HEAD 5f748734fc8f is an ancestor of origin/main | 0개 / 0 B | 없음 | `outputs/retired-worktrees/claude-zone-m2-pair-s3-frozen` |
