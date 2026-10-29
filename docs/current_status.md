# 현재 상태와 실행 경로

## 2026-10-20 현재 상태 — 학습 정책·nav·운반 진단 (18:00 UTC)

> 표기: `learned`=학습된 ACT 학생, `teacher`=학습된 교사 정책, `rule`=학습 없는 검출기/규칙. 수치마다 `sim`·`CPU/GPU`를 붙인다. `outputs/`는 git 제외 경로다.

- **C2c v7 시계 HO4 진단 — PASS(진단 전용)** `learned·sim·GPU(gcp2 L4)·평가 전용`: R8 step-100000으로 HO4 4 seed×3회=12 world-run에서 **과제 성공 6/12, 3초 들기 12/12, 내려놓기 6/12, 집기 완료 11/12**(같은 12회 B0 v6 시계는 과제 0/12). "과제 성공"은 집은 자리(pickup site)에 3초 안정 setdown까지이며 **운반 거리 0 m**다. HO4는 `gate_eligible=false` 진단 holdout이라 승격 관문이 아니고 VAL8·FINAL40·TRAIN4와 합산하지 않는다. PR #615 merge `eaacefd3`. 출처: `experiments/2026-10-20-act18-c2c-v7clock/README.md`·`report-summary.md`.
- **nav v230-r5 — 단일 실행 PASS** `rule·sim·GPU(gcp6 L4)`: 2-robot Step B에서 GT 도착 2/2·claim 2/2·mismatch 0·FP 0·접촉 0, 실행 source `219d0877`. **1회·seed 601·nworld 1**이고 r2/r3/r4는 제외했으므로 반복성 근거가 아니다. 리스크: 문 앞 4.6 cm, r2 yaw 15.6°, stage2 GT 2–6 cm. 출처: `outputs/reports/2026-10-20-nav-stepB-v230-r5-dsh-20261020T0210Z.md`(로컬).
- **nav N1 — 3/3 PASS, 반복성 전용** `rule·sim·GPU(gcp6 L4)`: s601/602/603 모두 PASS(GT/claim 2/2, mismatch·FP·경계·접촉 0, base-box 최소 0.1214/0.1433/0.2358 m, wall 266–279 s). 세 seed의 spawn이 동일해 **repeatability only**이며 독립 seed 강건성 근거가 아니다. 출처: `outputs/e2e18-admin/nav-gate/v230-n1/stepB-20261020T1045Z/nav-v230-n1-evidence/nav-v230-n1-seed-table.json`(로컬).
- **P2 smoke — 교사 운반 2/3** `teacher·sim·GPU(gcp6 L4)`: 3/3 world 실행 — world 1 FAIL `not_through_door`(carried 0.0006 m), world 11 SUCCESS 3.882 m, world 17 SUCCESS 4.423 m → carry 2/3, gate ≥1/6 PASS, wall 1501 s(smoke-1c). 바닥 하강 변형 미실행으로 6-run 계획은 미완이다. `summary.json`의 world1 `success=true`는 파지 gate 필드이지 운반 성공이 아니다. 출처: `outputs/reports/pairact-p2-teacher-clips-20261020.md`(로컬).
- **C4b v3 — Codex hold로 GPU 미실행** `GPU 0`: 사전 등록 부록 v3 `895040936`은 인과 판정·사전성 표기·fresh-out/cohort 보호 지적으로 무조건 OK가 보류됐다. gcp2 실행 0회, 원본·FROZEN 변경 0. 출처: `~/.ductor/codex/workspace/output_to_user/reports/c4b-v3-review-20261020/REVIEW.md`(로컬)·`outputs/reports/2026-10-20-act18-c4-counterfactual.md`.
- **CPU 관문 40/40·13/13 — GPU 운반 계약과 합산 금지**: 40/40은 고정 교사 의존성 기반 파지·ready gate40(pick/ready/command_complete 각 40/40)이고 **CPU MuJoCo(gcp2)**, PR #533 merge다. 13/13은 b-v6e 내려놓기 목적지 13셀(3 nominal seed+10셀)이며 **CPU(Mac)·top RGB+정적 지도·stage probe**이고 13/13 전부 `retreat_bounded` 스윕 거부로 멈춘 통과다. 둘 다 문 통과 운반 계약이 아니므로 GPU 운반 수치와 pooling하지 않는다. 출처: `experiments/2026-10-16-beampair7/README.md`·`experiments/2026-09-29-pair-v6e-carry/README.md:278`.
- **CI 참고** `CPU(GitHub runner)`: 2026-10-20 main run `39420494048`이 workflow "Offline regression tests" shard 2/8에서 실패했다. 실패 테스트는 `tests/test_azure_archive_native.py` 1건·`tests/test_pair_llm_live.py` 3건이며 issue #6의 `test_wrapper_signal_cleans_up_child_process_group`과 무관하다(§`docs/plan.md` 갱신 절).

## 2026-10-18 DSH 조정자 인계 — 진행 중 (결과 미확정)

Claude Code 조정자 세션을 사용자 승인으로 정지하고 DSH 팀(Lead+작업자 4)으로 이어받았다. 원격 실행은 중단 없이 유지했고, 같은 날 **검증 관문**(PR 병합·사용자 보고 전 독립 verifier 재계수·조건 감사)을 사용자 결정으로 도입했다. 기록은 로컬 `outputs/e2e18-admin/ops-alert.md`(gitignore)·`outputs/e2e18-admin/dsh-coord/HANDOVER.md`에 있다.

- **act18**(PR #575): gcp2 L4에서 R8·R100 fp32 100k 학습 진행(01:2x 기준 80,800/100,000, ETA 03:0x KST). 완료 후 TRAIN4 4/4 → VAL8 8/8(후보별) → FINAL40(winner 1개) → 모델 2종 패키징·Release. bf16는 새 학습 기본이고(2,000단계 프로브: 단계 중앙값 1.10배, VAL8 0.7358→0.6448) 이번 fp32 학습과 합산하지 않는다.
- **visgoal**(PR #582): gate-r4(16시작·120 SIM, GT-inside 1/16)를 기준선으로 후보 B(mirror pulse)→C(expanding search) 실행 중. B·C·gate-r4는 서로 합산하지 않는다.
- **beamact5**(PR #585): wide-start 교사 관문 34/40(최소 38 미달) 확인, r3 기본 off 모드 수정 후 6-world 재검증 중. "GO 프레임 band null 70/70"은 선행 관문 탈락의 구조적 결과이므로 색 밴드 검출 실패 근거가 아니다(독립검증 지적, 2026-10-18).
- **egonav**(PR #587): 원거리 검출 진단 — 4.5 m 존 마킹 100/100, 5.0 m 이상은 `downward_min` 바닥투영 유효영역(≈4.8 m) 밖이라 0/100, 4.0 m는 안정 상태 metric_size 거부. far 검출 프로필 미승격·제어 기본 `max_range_m=4.0` 유지.
- 유지 중인 사용자 결정: 2026-10-17 정적 지도 미사용·자기중심 기억, 2026-10-17 bf16 새 학습 기본, 2026-10-18 검증 관문, GCP 메인·Azure 보조, 실행 시간 상한 없음.

## 2026-10-16 ACT16a — 학습 없이 ACT15 실패 분석

GCP2 CPU에서 Release 모델로 같은40회를 재현했고 관문 수·결과 요약40/40과 저장 RGB 지문240/240이 일치했다(원래 전체 궤적 동일성은 미확인, 호스트 간 합산 없음).
최초 탈락은 정렬22/40·접근15/40. 새 추론 첫 행동도 persistence보다 wheel MAE가2.96%만 낮고 교정 필요 바퀴의79.4%가 이전 부호를 유지했다.
이력 마스킹은 PWM 오차를 키워 배포 근거가 아니며 history_causal_split_v1의 동일 조건 재학습 A/B가 첫 후보다. 학습0·계획 미승인, 원래 데이터는 금지된GCP1 디스크에 남아 있다.
[분석·관문표·영상·학습 계획](../experiments/2026-10-16-act16a/README.md).

## 2026-10-15 ACT15 DAgger 1회 — 학생 성공 개선 미확인

초기 시연 선택에서 빠진 시작/접기·접근452행을 복원하고 학생 방문상태6,161행을 추가해 L4에서 고정10,000step을 학습했다.
같은20 완료0/20, 새20 완료0/20(안정 들기0/40), 기본 채택 없음. 관문은 각각20→13→2→2→0,20→12→1→0→0이다.
원본·전체 실패/중단·funnel·모델 Release 검증·비용은 [ACT15 기록](../experiments/2026-10-15-act-train/act15.md)에 있다.
ACT15 L4 두 창은 종료 확인했으며 이후 다른 작업이 같은 VM을 재사용한다. 기존 연구 상태·프로필 결과와 합산하지 않는다.

## 2026-10-01 b-v6h1 분석 봉인 — 독립 검토 필요

PR #292에서 EXECUTION 274파일을 블라인드 기록 소스 `4c6b439f`에, 최종 classifier/adapter/gate를 별도 봉인 커밋에 고정했다. CURRENT_REVISION=v6h, v83/2.16.0 유지. 기록이 봉인보다 앞선 `unsealed_stage_probe`였음을 공개하며 실행 전 등록으로 소급하지 않는다. 이번 작업은 raw·outcome 열람이나 물리/렌더를 하지 않았다. 48/60(941)과 첫12곳 민감도(943), HOST_ERROR/ENOSPC/누락 UNCLASSIFIED를 고정했다. [봉인과 재현 경계](../experiments/2026-09-30-pair-v6h-carry/REGISTRATION_PLAN.md). 독립 검토·개봉·PR 병합은 남아 있다.

아래 첫 절은 2026-09-30 저녁 진행 요약이고, 이전 9/30·9/29 절도 당시 기록 그대로 보존한다. 앞으로의 연구 우선순위와 완료 기준은 [연구 TODO](research_todo.md)(2026-09-26 개정: §0 로드맵, 마일스톤 "E2E 첫 파일럿" 이슈 #216–#226)를 따른다. 통신 효과가 주 질문이며 ACT·Jev·맵 확대는 관련 보조 과제로 구분한다. 아래 검증 수치는 각 기록 당시의 범위를 유지한다.
