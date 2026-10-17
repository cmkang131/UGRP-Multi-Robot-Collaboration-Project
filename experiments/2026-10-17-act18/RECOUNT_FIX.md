# act18 원시 재계수 스키마 수정과 TRAIN 기준선

## 요약

기존 F(act17 v7, 10k)의 TRAIN4 폐루프 진단은 물리 실행을 끝냈지만, 새 `act18_recount.py`가
`eval-owner` 결과 스키마에 없는 `result.json:input_audit` 키를 읽어 재계수 단계에서
HOST_ERROR로 끝났다. 학생/교사 입력 경계는 실제 기록된 `actor-inputs.jsonl`의 정확한
화이트리스트(`validate_observation`)로 검사하도록 고쳤다(8d21fbe1a, ab89b3c54).
수정 후 같은 원본을 재계수한 결과 **F 0/4**다: cap_end 2, stable lift 실패 2.
즉 v7 10k 모델은 TRAIN 폐루프 적합도부터 실패한다.

| seed | kind | task | grasp done | lift | release | cap_end | reason |
|---:|---|---|---:|---:|---:|---:|---|
| 88600 | cyan | false | false | false | false | true | cap_end |
| 88601 | red | false | true | false | false | false | lift_not_stable |
| 88602 | green | false | false | false | false | true | cap_end |
| 88603 | yellow | false | true | false | false | false | lift_not_stable |

- 원본 평가: `/home/ugrp/ugrp-sim/runs/act18/baseline-F-TRAIN4-r1/group-000|001/evaluation`
- 수정 재계수: `/home/ugrp/ugrp-sim/runs/act18/baseline-F-TRAIN4-r1/raw-recount-fixed-8d21fbe1a.json`
  (sha256 `95a95ac2425648465ab2d16f8ad133c8f4626e8e9c17354297b3a6720a5c0a1e`, actor inputs 2,209 검증)
- 요청 관문은 requested 4→grasp_done 2→stable_lift 0→release 0→task 0.

## 수정 내용

1. `eval-owner`의 `world-*/result.json`에는 `input_audit`가 없다(스키마: `cap_end`, `evaluation`, `issued_done`, `status`). 없는 키를 요구하지 않고, 모든 `actor-inputs.jsonl` 관측을 정확한 FIELDS 화이트리스트로 검증한 기록을 audit 증거로 쓴다. `world`는 평가기 세계 인덱스이며 정책 입력 필드가 아니다.
2. `eval-owner`에는 세계별 `eval-only.jsonl`이 없고 `owner/evaluation-only.jsonl`에 모인다. 필수 `result.json`/`scene.xml`만 요구하고 선택 추적은 없다고 기록한다(없는 파일을 만들지 않음).
3. owner 재시작 시 lease의 `pid`가 훈련 queue PID가 아닌 이전 owner PID로 덮여 있던 문제를 고쳐, `act18_queue.py`와 정확한 `--out` 훈련 경로가 함께 있는 살아있는 프로세스만 queue로 인정한다(ab89b3c54).

## 실행 소유권

- 학습 queue 2843은 중단하지 않았다. R8/R100 matched 100k는 계속 진행 중이다.
- `finish-r1`(pid 7624)은 위 재계수 결함을 확인한 뒤 정지, `finish-r2`는 lease PID 혼동으로 HOST_ERROR(보존), `finish-r3`(pid 11757, source ab89b3c54)가 같은 학습을 감시한다.
- 다음 관문: 100k 완료 → R8/R100 개루프·TRAIN4(4/4만) → VAL8(8/8만) → FINAL40. VAL/FINAL은 아직 제출되지 않았다.
