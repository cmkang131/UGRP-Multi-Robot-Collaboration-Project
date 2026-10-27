# HAN-32 — pair student alignment fix 제안 (실행 안 함)

**teacher-level / HOLD_SCENE / not a gate / new cohort / do not pool**

## 원인 우선순위

- **EVIDENCE:** 현재 scoped `C-audit.json`: 성공 0/20, 정렬 0/20, READY 0/20. `S-audit.json`: 성공 0/20, 정렬 1/20, READY 0/20. 가장 큰 관문 탈락은 정렬이다. 정책 stage 이름의 carry/place 출현을 실제 정렬·파지·운반으로 해석할 수 없다.
- **EVIDENCE:** 과거 baseline-resume S world9의 별도 진단은 정렬 후 665 tick 동안 r1 READY 109·r2 READY 0, r2 execute 598·GO/ACK 0이다. 근거: `/home/ubuntu/ugrp-wt/codex-arm-s-post-render-20261027/experiments/2026-10-27-arm-s-post-render/DIAGNOSIS-ready-w9.md`. 현재 scoped S와 같은 실행으로 합산하지 않는다.
- **INFERENCE:** 인터페이스에서는 READY mutual-wait와 일치하지만, r2가 READY를 선택하지 않은 인과는 stage_logits 부재로 **UNKNOWN**이다. barrier·stage-head·영상 분포·done 전환 중 어느 것이 주원인인지 아직 판정하지 않는다.
- **EVIDENCE:** frozen controller `_sequence`의 `release_instruction`은 own/both done 유지시간을 따른다. **INFERENCE:** release-transition만 고치는 GPU 실험은 앞선 정렬 병목을 해결할 근거가 없다. 그 수정만을 위한 GPU 지출은 하지 않는다.

## 다음 후보의 정확한 계측 (모두 INFERENCE: 제안, 미구현·미실행)

기존 봉인 controller/worker를 수정하지 않고 새 후보 복사본과 해시를 만든다. 대상은 candidate `controller.py`, actor의 `pairact_r1_student.py` stage/done 출력, worker 응답 직렬화, `StudentBarrier`와 `StudentEpisode` trace다. actor의 정확한 파일·함수·config가 회수되지 않았으면 먼저 확정하고 그 부재를 UNKNOWN으로 기록한다.

매 actor forward 및 로봇별 발행 tick을 `episode_id, world, seed, robot_id, tick, sim_t, inference_id, frame_sha256, checkpoint_sha256, source_sha`로 연결하고 다음을 보존한다.

- `stage_logits`: stage head의 전체 원시 출력 벡터, `stage_labels`의 정확한 순서, argmax index/label, 선택 stage, 선택 확률, stage-head config/temperature/mask. 로그에는 로봇별 자기 입력만 연결한다.
- `done_logit`, 적용 activation/threshold, raw done·선택 done·issued done, done 유지 시작 시각·누적 SIM시간. 기존 상수 값을 읽어 기록하며 계측 단계에서 조정하지 않는다.
- `transition`: 이전/제안/수락 stage·skill·segment, 전환 여부, `reason_category`와 구체 guard 이름, 각 guard의 입력 boolean/값/기존 threshold. 같은 stage 유지도 `stay:...` 사유를 기록한다. READY 상승·철회, rearm epoch, GO 시각·ACK·permit·TTL·delay·chunk discard/decode·software hold/차단 전후 command를 연결한다.
- 물체 이름·최소 틈이 관측되지 않았다면 `blocked_object=UNKNOWN:not_observed`, `min_gap_m=null`, 측정 상태를 기록한다. 비어 있는 거부 사유는 허용하지 않는다.
- GT 정렬 오차·접촉·funnel은 별도 eval-only 파일에서 tick으로 대조한다. GT·정적 지도·top camera·실측 관절을 학생 제어/전환에 주입하지 않는다. 계측 후보는 own RGB와 own issued history를 그대로 사용한다.

**INFERENCE:** CPU에서는 직렬화와 synthetic unit test만 검증한다. GPU 승인 후 먼저 계측된 기존 후보를 실행해 실제 탈락표와 원본을 수집한다. stage와 기하 정렬 불일치, r2 READY 미선택을 구별한 뒤 가장 큰 원인 하나에 대한 수정 후보를 만든다. 근거 없이 alignment 허용 오차·READY threshold를 느슨하게 만들지 않는다. 이후 수정 후보도 별도 cohort로 평가하고 단일 수정 후 학생 독립 carry까지 다시 검증해야 한다. 재학습 필요성과 그 비용은 아직 UNKNOWN이며 아래 예산에 포함하지 않는다.

## 자원·GPU-h 산식

- **EVIDENCE:** 파일럿 `pilot-8343000-b/summary.json`은 planned_N=20, 전체 wall_s=3545.132712425, loop_wall_s=3407.207480722, setup_compile_s=133.7540292929998이다. 따라서 당시 단일 L4 전체 할당 시간은 **0.9847590868 GPU-h**다. 이전 리뷰의 3144.9초 대신 실제 파일을 쓴다. 동시 world 수로 나눈 per-world wall/SIM을 GPU-h로 오인하지 않는다.
- **INFERENCE:** 다음 계측 진단은 **N=4** 설계로 제안한다. 진단용 원본이 있는 정렬 실패·성공 경계 사례와 과거 world9에 대응하는 seed를 고정하고 해당 actor/model/scene가 같은지 먼저 확인한다. 이 seed 선택은 gate나 확증 표본이 아니다. 작은 배치의 시간 선형 감소를 가정하지 않고 파일럿 전체 N=20 시간 한 번을 배정한다.
- **INFERENCE:** 부팅·종료·로그 준비 할당 여유를 **600초/배치**로 계획한다(실측 아님). 전체 wall에는 기존 setup이 이미 포함된다. 1차 예상 = `(3545.132712425 + 600) / 3600` = **1.1514257535 GPU-h**; 제안 승인 상한 **1.2 GPU-h**. 성능 보장이나 실제 사용량이 아니다.
- **INFERENCE:** 원인 확인 후 별도 수정 N=4 비교를 승인한다면 같은 배정 한 번을 더 써 총 **2.3028515069 GPU-h**, 합계 제안 상한 **2.4 GPU-h**다. 진단 후 수정이 정당화되지 않으면 두 번째 배치는 실행하지 않는다. 재학습·전체 학생 관문·solo·교사 재실행은 이 제안에 포함되지 않는다.

## 기존 호스트와 승인 경계

- **EVIDENCE:** 사용자가 지정한 재사용 호스트는 기존 **`ugrp-act-l4-gcp6` (`g2-standard-8`, L4)**, 프로젝트 `ugrp-sim-f-1016`, 계정 `kcm5781kcm5781@gmail.com`이다. 현재 scoped 기록 지역은 `asia-northeast1-c`, 과거 파일럿은 `asia-northeast3-a`이므로 결과를 합산하지 않는다.
- **INFERENCE:** 현재 closeout 담당자가 아카이브 회수·해시·임대 해제·정지를 마친 뒤에만 이 기존 VM을 검토한다. 새 VM을 만들지 않는다. 이 문서는 시작/정지/예약 명령이 아니다. 실행 전 실제 호스트·소유 작업·budget-stop·idle guard·디스크·최신 stack 관문과 재현 funnel을 별도로 확인한다.
- **EVIDENCE:** `results/GPU_CAP_RAISE_APPROVAL.json`의 기존 누적 상한은 **25.3 GPU-h**로, 현재 closing batch에 대한 승인이다. 남은 수치를 새 실험 허가로 전용할 수 없다.
- **INFERENCE / 승인 필요:** 새 GPU 사용은 **별도의 사용자 승인**이 있어야 한다. 승인에는 목적, 프로젝트·계정·지역·VM, 새 cohort, 1차 **1.2 GPU-h**와 조건부 추가 **1.2 GPU-h**의 범위를 명시해야 한다. 이 작업에는 그러한 승인이 없으며 GPU 사용·VM 조작을 전혀 하지 않았다. 이번 0 GPU 범위에서는 이 계획만 작성한다.
