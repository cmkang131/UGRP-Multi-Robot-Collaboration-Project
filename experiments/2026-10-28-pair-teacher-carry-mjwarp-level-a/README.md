# HAN-32 — Level-A golden teacher carry record

**teacher-level / HOLD_SCENE / not a gate / new cohort / do not pool**

이 기록은 저장된 MJWarp 교사 장면의 Level A 검증이다. **학생 연구 마일스톤 Level B는 달성하지 않았다.** 로컬 분석은 새 물리·GPU·렌더·모델 호출과 VM 조작 없이 Oracle의 회수 원본을 읽었다. PR 자동 CI 예외는 아래에 별도로 기록한다. 폴더의 `2026-10-28`은 요청된 기록 ID이며 실제 작성 환경 날짜는 2026-10-27 UTC다.

## 판정과 적용 범위

```text
success_strict = success
                 AND funnel.carried_1m
                 AND funnel.door_passed
                 AND carried_max_m >= criteria.carried_min_m (1.0 m)
Level A record additionally requires:
  funnel.zone_inside_final AND funnel.lowered_resting
  AND funnel.released AND funnel.still_1s AND drop_events == []
  AND weld == "off" AND teacher_profile == "visible_only"
  AND input_audit.invisible_measurements == 0 AND held_world_reads == 0
```

기존 `success`가 목적지 배치·정지·방출, 낙하 없음, 로봇 간 접촉 프록시 0을 결합한다. 위 추가 funnel은 기록에서도 명시적으로 검증했다. `carried_min_m=1.0`은 기존 funnel 값과 HAN-32 사용자의 운영 정의를 그대로 사용한 것으로 실기 사양에서 추정한 허용 오차가 아니다. 기존 정지 1초·5mm, 바닥 6mm·기울기 5도, 방출 0.5N·문 여유 0.2m는 이번 작업에서 조정하지 않았다.

`harness/pair_carry_eval.py`는 `success_strict`를 진단 필드로 항상 반환한다. **관문·prereg 판정으로 선택하는 기능은 기본 비활성**이며 어떤 소비자도 새 필드를 채택하도록 바꾸지 않았다. 기존 `success`, `failure`, schema와 봉인 판정은 그대로다. strict helper는 수송 근거 누락·비유한 이동량을 실패로 처리한다. 이 판정은 경로·파지의 모든 시간 순서를 새로 증명하는 판정기가 아니며, 거리 측정도 handover 이후 최대 순변위다.

`visible_only`는 원본 교사 프로필과 입력 감사의 주장이다. 근거리 교사의 관측 제한과 이후 중앙 GT 운반 교사는 구분한다. 이를 자기 RGB만 쓰는 분산 학생 성공으로 해석하지 않는다. GT 판정은 제어 입력으로 보내지 않았다.

## Golden 원본

- `golden-cases.jsonl`: 파일럿 15건과 독립 seed 8340211을 개별 기록. seed·world·이동량·문 통과 시각·전체 funnel·SIM시간·교사 SHA·carry-eval/result/plan/trace 절대경로·SHA-256·기존 manifest 항목 포함.
- `artifact-index.json`, `artifact-index.sha256`: `sha256sum`으로 원본을 해시했다. Golden 핵심 파일은 기존 world manifest와, 해당 항목이 있는 파일럿 batch manifest와도 일치한다. raw는 로컬에 있으며 해시 색인은 원격 백업이 아니다.
- `physical-corroboration.json`: 저장 10Hz trace에서 빔 XY 경로와 handover→lower 시작 사이의 양쪽 jaw 힘을 계산했다. 모든 golden에서 그 구간 각 로봇의 양쪽 힘은 기존 0.5N 이상이고 구간 경로는 4.177m 이상이다. 이는 샘플링된 힘의 보강 근거이며 native 충돌 쌍의 완전 감사나 영상 재검토가 아니다. 별도 60% 같은 수용 상수를 만들지 않았다.
- 대표 파일럿: seed **8343020**, world-000, `carried_max_m=4.171676887536326`; 독립 기록: seed **8340211**, world-011, `4.7776570567111225`.

파일럿은 `mjwarp_batch_v1` / `warp_native_contact_v1` / noslip 0 / weld off, GCP6 `g2-standard-8`, `asia-northeast3-a`다. source contract의 teacher/certification SHA는 **402bbf155ca162da7a74518eab9b8bd98138299a**, adapter SHA는 **2e4460ee618894542e73e164f9f814a50426b3f8**이며 runner source SHA는 별도 summary에 남아 있다. 이번 코드도 파일럿 evaluator가 존재하는 이 c4 SHA에서 분기했다. 독립 seed의 result source SHA는 **75929e7719ad98a089e3dda5251f4249d8bae511**다.

파일럿·P3 ledger/독립 사례·현재 C/S scoped cohort는 서로 다른 집단이다. Golden 목록 16행은 사례 색인이지 16회 신규 관문이나 합산 성공률이 아니다. 현재 C/S 호스트 지역은 `asia-northeast1-c`이며 과거 지역·stack·backend 결과와 합산하지 않는다. CPU 결과·noslip10 결과·학생 결과와도 합산하지 않는다. 새 strict 기준의 별도 분석 기록이며 과거 prereg를 소급 수정하지 않는다.

## 파일럿 요약 과대계상

`summary.json.success_n=18`은 개별 carry 판정과 다르다. 요청 20 → carry-eval 존재 18 → legacy carry 성공 15 → 수송/문/최종배치 결합 15다. 다음 세 world는 batch 성공이지만 carry-eval 자체도 실패한다. 0m pre-placed의 evaluator loophole과 별개의 batch/개별 판정 불일치다.

| world / seed | carried_max_m | carry-eval failure | 빠진 strict funnel |
|---|---:|---|---|
| 010 / 8343030 | 0.000328983451096721 | not_through_door | carried_1m, door_passed, zone, resting, released |
| 016 / 8343036 | 0.00047950476774747487 | not_through_door | carried_1m, door_passed, zone, resting, released |
| 018 / 8343038 | 0.00021076766235535922 | not_through_door | carried_1m, door_passed, zone, resting, released |

나머지 제외는 world-001 seed8343021 `cap_end`와 world-019 seed8343039 교사 실패로, 둘 다 carry-eval이 없다. 모든 20회와 제외 사유·누적 통과/거부 수는 `rejection_table.json`에 기록했다. 물체·최소 틈은 근거가 없어서 `UNKNOWN:not_observed` / null이다.

## 재현과 검증

원래 `pilot-8343000-b/rejection_table.json`의 `reproduce` 배열을 `pilot-reproduce-excerpt.txt`에 shell 인용까지 보존했다. 그 명령은 역사 기록이며 실행하지 않았다. 선행 setup funnel의 원래 VM 절대경로도 `rejection_table.json`에 보존했다. 새 실행 대기열은 만들지 않았다.

현재 체크아웃에서 다음 명령은 로컬 파일 분석만 한다. 입력이 없는 clone에서는 원본 부재 오류가 나며 성공을 대체하지 않는다.

```sh
python3 experiments/2026-10-28-pair-teacher-carry-mjwarp-level-a/seal_level_a.py
sha256sum --quiet -c experiments/2026-10-28-pair-teacher-carry-mjwarp-level-a/artifact-index.sha256
/home/ubuntu/ugrp-venv/bin/python -m pytest -q tests/test_pair_carry_teacher_warp.py
```

검증 결과는 `VALIDATION.md`, 원장·학생 재채점은 `strict-rescore-20261028.{json,md}`, 실행하지 않은 다음 단계는 `ALIGNMENT-FIX-PLAN.md`에 있다.

## 자동 CI 제약 위반과 취소

PR 생성으로 자동 시작된 [CI run 40531267967](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/40531267967)에서 취소 요청이 적용되기 전에 `ubuntu-simulation-scenarios`의 `Render and move without a model or GPU` CPU demo 단계가 실행·완료됐고 다음 단계는 취소됐다. **새 물리 실행 없음이라는 사용자 제약을 CI까지 지키지 못했다.** 로컬 physics 0과 전체 physics 0을 구분해야 한다. GPU·GCP VM 조작은 없었다. 이 run은 `completed/cancelled`로 확인했고 전체 CI 통과를 주장하지 않는다. 후속 문서 정정 커밋은 `[skip ci]`로 만들어 재실행을 막았다. 기존 sealed results/prereg는 그대로다. 상세는 `CI-CANCELLATION.md`.
