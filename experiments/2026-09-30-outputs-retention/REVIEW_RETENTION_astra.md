# PR #309 독립 보존 검토

**판정: DO NOT EXECUTE. 현재 manifest로 삭제하면 실제 학습·추론 입력과 이미 보고한 수치의 원본이 사라진다.**

- 검토 대상: `70f2f09c46bdc1e265af70fb44111f5906324dff` (`origin/codex/outputs-retention`).
- manifest SHA-256: `7dae93f5544dba9575048865ccd1ed40e014b30423a949f16f80384976a4a635`.
- 독립 검토 브랜치 기준: `b10907c5f2c84f2712030f48fb38061fd4f51281`, `codex/review-retention`.
- `/Users/changmin/projects/ugrp/outputs/`는 읽기만 했다. 원본 삭제·수정·이동·압축 0회.
- [exclusions.json](exclusions.json): 삭제 목록에서 빼야 할 보수적인 폴더/패턴, **724,107파일 / 18.286400 GiB**. 현재 삭제 후보에 들어 있는 분량만 센 값이다.
- [review-evidence-astra.json](review-evidence-astra.json): 원본 해시·반례·50쌍 D5·10폴더 D1·전체 파일 stat 결과.

제외 뒤 산술상 남는 후보는 **298,446파일 / 5.458538 GiB**다. 이 잔여 목록의 실행 승인도 아니다. 모델 입력 식별과 수치 원본 의존성 누락이 여러 생성기에서 발견됐으므로, 새 목록의 전체 이름·해시·복원 연결을 고정하여 다시 검토해야 한다. 이 리뷰의 제외 목록을 옛 manifest 옆에 놓는 것만으로 실행기가 제외를 적용하지는 않는다.

GiB는 원 PR과 같은 `st_blocks × 512 / 2^30` 할당량이다. APFS에서 실제 반환될 여유 공간을 보장하는 수치는 아니다.

## P1 — 학습된 접근·파지 제어기 입력을 D1/D2로 삭제한다

가장 우려한 `dispatch-action-act-20260924/holdout-{a,b}-candidate-act`는 **폴더 전체를 비모델 프레임으로 판단할 수 없다.**

| 원본 실행 | 명시적 ACT 입력 이미지 | 그중 삭제 | 별도 학습 접근·파지 입력 중 삭제 |
|---|---:|---:|---:|
| holdout-a-candidate-act | 138 | 0 | **359** |
| holdout-b-candidate-act | 51 | 0 | **392** |

189개 ACT 이미지의 실제 파일 해시가 `pair-decisions.json`의 기록과 모두 일치한다. 따라서 ACT 운반 요청 그 자체에 대해서는 우려가 재현되지 않았다. 그러나 같은 실행의 접근·파지에도 학습 모델이 있다.

구체적인 반례:

- `outputs/dispatch-action-act-20260924/holdout-a-candidate-act/rgb/pair-100-phase-1-030-r1.jpg`
- SHA-256 `dae554327749f7a13e365e6ac04051184b66dfa7f7dd431b8a7a399e38ff9ebe`
- `pair-decisions.json:51944`의 `learned_approach.report.approach_calls[].images.own`에 기록된 모델 입력이며 **D1 삭제 대상**이다. 대응 `pair-100-canonical-top.jpg`도 삭제 대상이다.
- 해당 실행의 `result.json` 소스는 `12f8e6dda76e39b3ec612f247deb4835a2ff50bc`. 이 SHA의 `scripts/dispatch_pair_skill.py:725,745,843`은 실제 `predict_student`/`predict_stage`에 own/top JPEG를 넘긴다.
- `harness/camera_varied_start_student.py:135–185`는 학습된 PCA/kernel 계수로 예측한다. 단순 표시용 영상이 아니다.
- `scripts/audit_dispatch_skill_inputs.py:59–66`은 그 이미지를 다시 읽어 학습 모델 예측을 재계산한다. 삭제 후 이 감사가 파일 읽기에서 실패한다.

삭제 후보가 있는 **76개 `rgb` 폴더**의 인접 `pair-decisions.json`/`pair-grasp.json`을 조사했다. 72개 실행에 모델 기록이 있고, 명시적으로 기록된 학습 접근·파지 입력 **32,026개**가 삭제 목록과 겹친다. 11개 실행 계열에서 5장씩, 55장의 실제 SHA-256을 기록 해시와 비교해 모두 일치했다. 실행별 모든 이미지의 의미를 완전히 구분했다는 주장은 아니다. 그래서 E1은 해당 11개 실행 계열 전체를 보수적으로 제외한다.

반대로 `llm-decisions.jsonl`의 `llm_request` 1,292행에 명시된 이미지 2,584개에서는 삭제 교집합이 **0**이었다. 이는 이 형식의 검사 결과이며 모든 세대의 LLM/VLM 저장 형식이 안전하다는 증명은 아니다.

**누락 원인:** PR의 `audit/round2_evidence.py:102–115`는 파일명에 `request|payload|...` 등이 있어야 모델 경로/해시를 수집한다. `pair-decisions.json`은 시각 수집 대상으로만, `pair-grasp.json`과 `combined-dataset.json`은 모델 입력 경로 수집 밖으로 빠진다. `audit/round2_plan.py:35–59`의 이름 기반 보호로도 이를 막지 못한다. 개발 실행 여부는 입력 삭제의 근거가 될 수 없다.

## P1 — 퇴역 realtime 실행이 실제 ACT 학습 데이터다

`outputs/act-action-training-20260924/data/combined-dataset.json`의 `train[].image_hashes`에 들어 있는 **1,155장**이 D2 삭제 대상이다. 1,155장 전부 실제 파일 SHA-256을 데이터셋의 해시와 직접 비교했고 일치했다.

| 학습 원본 | 삭제될 학습 이미지 |
|---|---:|
| simulation-realtime-20260923/native-v19-grasp-full | 251 |
| simulation-realtime-20260923/native-v19-grasp-repeat | 259 |
| simulation-realtime-20260923/native-v19-full | 320 |
| simulation-realtime-20260923/native-v19-repeat | 325 |

예: `native-v19-full/rgb/pair-311-carry-r1.jpg` (`649d0c99084b6868e29a49c22256445250a118433128c8f7194adda4a478f525`).

이것은 쓰지 않은 데이터셋 초안이 아니다. `act-action-training-20260924/train-seed24-managed/artifacts/report.json:2,20,22,503`이 `complete: true`, `completed_steps: 8000`과 이 데이터셋 SHA-256 `9cd42d3b6859fcb1526dab7ee675ba4349cf6fd32537d1c955a696e1e3197a57`을 기록한다. `scripts/build_carry_act_data.py:140–159`는 원본 JPEG 해시와 실제 발행 행동을 데이터셋에 연결하고, `scripts/train_carry_input_act.py:347,378`은 데이터셋 검증·로딩을 수행한다.

`act-*` 이름이 붙은 폴더 안의 이미지만 보호해도 원본이 바깥 `simulation-realtime-*`에 있으면 잃는다. `act-action-training-*` 안에서 이 manifest가 직접 삭제하는 것은 D3/D5 항목이며, 핵심 이미지 손실은 외부 학습 원본에서 발생한다. E1에 realtime 계열을 포함했다.

## P1 — 별도 비전 worker와 정지 화면 모델 입력도 빠졌다

- `vision-worker-closed-loop-20260927/vl3-dev-s942`: worker 측정 기록 1,375건과 자기 프레임 시각을 연결하면 해당 입력 **1,092장**이 D1 삭제 대상이다. 예: `frames/r2/00003.jpg`. 동일하게 반올림된 시각이 있어 고유 시각은 1,370개이고 연결된 프레임은 1,375개다.
- `harness/vision_pose_source.py:193–214`는 RGB→BGR을 만들어 `worker.observe`에 전달한다. `harness/vision_loc_client.py:125–148`은 실제 worker 요청을 전송한다. JPEG 파일 전체 해시와 디코딩한 BGR 해시가 같을 것이라고 가정할 수 없다.
- `experiments/2026-09-27-vision-worker-closed-loop/README.md:52`도 `frames/r*/`가 보존할 모델 요청 이미지라고 명시한다. dev/no-LLM 실행이어도 학습된 분할 모델 입력이다.
- `carry-relocalization-b1-20260929`에서는 정지 RGB 190장과 평가 PNG 190장이 삭제 대상이다. `experiments/2026-09-29-carry-relocalization-b1/segment_frames.py:41–55`가 RGB로 학습된 분할 추론을 하고 PNG로 IoU를 구한다. `docs/current_status.md:31`의 672회 재측위 결과 및 민감도 분석과 이어지는 자료다.

E2로 두 계열 전체를 제외한다.

## P1 — 보고된 수치의 픽셀 원본·평가 라벨·바이트 비교가 손상된다

`sealed-cohorts.json`에 기재한 **8개 경로는 삭제 교집합 0**이다. 하지만 이 목록만으로 보고 근거를 다 보호하지 못한다.

| 보고된 수치/검증 | 삭제되는 근거와 재검증 실패 | 제외 |
|---|---|---|
| 재측위 시야: 정렬 시작 V 중앙값 5.18%, 운반 V 0%, 그립퍼 연 뒤 4.81% | 원본 `relocalization-audit-20260929/frames.jsonl.gz` 67,237행을 경로로 복원하면 **54,594장**이 삭제 목록에 있다. `experiments/2026-09-29-relocalization-audit/audit_run.py:95–110`은 매 4/8번째 원본 JPEG를 읽고, 없으면 조용히 건너뛴다. 재실행하면 분모가 달라진다. | E3 |
| 자기 카메라 위치 추정: test 문 근처 p50 1.9 cm / p90 5.8 cm, 태그 가시율 | `owncam-loc-20260925` D1 **6,476장**. `scripts/eval_owncam_localization.py:68–73`은 모든 `inputs/frames.jsonl` 원본을 읽고 해시 확인 뒤 검출한다. 삭제하면 detect→localize→score 재검증이 끊긴다. `docs/current_status.md:129`에 해당 수치가 있다. | E4 |
| RGB 결과 판정: test 확정 203/204, false-delivered 0 | `zone-rgb-outcome-20260925` D1 **3,449장**. 예: `test/zone-communication-20260925__ZC2-s12-plan_first-graspfail/r1-1/frames/after-00.5s-top-ne.jpg`. 0/0.5/1/2/4/8초 확인 규칙의 0.5/1/2/4초 영상을 삭제한다. 이는 일반 연속 영상의 중간 장면이 아니라 판정 입력이다. 실험 README의 §2–3에 규칙·분모가 있다. | E4 |
| 4색 검출: test 오검출 0/520, 색별 재현율 | `zone-rgb-color-20260925` **평가 segmentation PNG 1,800개**(test 846, dev 954)를 D1로 삭제한다. `scripts/eval_zone_color_detection.py:657–667`이 실제 PNG를 읽어 점수화한다. 정적 장면·카메라별 정답을 프레임 번호처럼 솎으면 score를 재실행할 수 없다. | E4 |
| 렌더 프로필: 프레임 게이트·빔 가시율·JPEG 동일성 | `render-profile-ab-20260929` D1 **18,606장**. `scripts/analyze_render_profile_ab.py:93–129`가 모든 저장 프레임의 픽셀 통계와 해시를 계산하고, 없는 프레임은 조용히 제외한다. | E4 |
| sim-speed: seed 93/95 전체 2,080/2,309장 JPEG 동일, 짧은 구간 비교 | `sim-speed-20260926` D2 **11,445파일**과 비교 기준 `m1-owncam-20260926/dev-a8`의 D1 원본을 삭제한다. `scripts/sim_equivalence.py:216–225`는 원본 바이트를 읽어 비교한다. `experiments/2026-09-26-sim-speed/README.md:38–41`의 검증을 원본으로 다시 확인할 수 없게 된다. | E5 |

재측위 감사 gz 원본의 실제 해시는 README에 기록된 `09cb34c7941818c9eccae8effbbfce05e5dd336329736ad1c8cbcdc4f345e22a`와 일치한다. 삭제되는 예는 `pair-stage-probes-052e3eba-v6d-bound-e2e/cases/grasp_lift_b-v6d_boundary_corner+++_s911_pE2E/frames/r1/00004.jpg`다.

CSV/JSON에 이미 계산된 값을 남기면 그 값의 합산은 가능하다. **픽셀에서 그 값을 다시 측정하거나 입력·출력 관계를 확인하는 검증과는 다르다.** 원본 해시나 대표 영상 한 개도 삭제된 JPEG/PNG의 바이트를 복원하지 못한다. D2의 퇴역 분류와 5 MiB 기록 한도 역시 학습 원본·보고 근거 보존 예외를 대신하지 않는다.

## D5 — 50쌍 실제 바이트 일치, 복원 연결은 전수 확인

- `json-reconstruction/*.csv` 17,523행 모두: 삭제 경로는 D5 목록, 대응 원본은 keep 목록에 있다. 오류 0.
- 표본은 경로순 정렬 뒤 `random.Random(309).sample(rows, 50)`으로 고정했다.
- **50/50**: 삭제 사본과 보존 원본을 실제로 읽어 `bytes == bytes`, 양쪽 SHA-256 및 manifest 기록값, 길이가 모두 일치했다.
- 개별 50쌍의 경로·길이·해시는 증거 JSON의 `d5.samples`에 있다.
- 이 검사는 전체 17,523쌍의 실제 바이트 전수 비교가 아니다. 삭제 후 원래 경로를 요구하는 도구에는 기록된 복사 복원이 먼저 필요하다.

## D1 — 10폴더의 솎기 동작은 확인, 대상 자격은 별개

시간은 실제 `robots.json` 또는 `inputs/frames.jsonl`에서 다시 읽었다. 서로 다른 10폴더를 목적 표본으로 골랐으며 무작위 모집단 추정은 아니다. 표의 전체 파일은 선택한 카메라 스트림 기준이며, 추가 보호 프레임을 포함한다. 전체 경로와 원본 로그 해시는 증거 JSON의 `d1.samples`에 있다.

| 폴더/실행 식별 | 원본 → 보존 | 보존 간격 중앙값 / 최대 SIM초 |
|---|---:|---:|
| zone-own-executor / smoke-s701 / r2 | 4,900 → 990 | 1.00 / 1.20 |
| m1-owncam / dev-a4 / m1devdiag-s94 | 3,870 → 750 | 1.00 / 1.20 |
| vision-worker / vl3-dev-s942 / r2 | 2,375 → 499 | 1.00 / 1.20 |
| zone-pair-dev-v6 / v6-s912-v5h / r2 | 1,812 → 241 | 1.00 / 1.20 |
| owncam-memory / dev-a2 / memory_v2 / s152 | 1,674 → 352 | 1.00 / 1.20 |
| owncam-loop / test-box-s43 | 1,365 → 287 | 1.00 / 1.00 |
| owncam-loc / test-ll-s21 | 743 → 192 | 1.05 / 1.75 |
| pair-stage-probes-3f6ca985-ghR2 / carry hR2_01 L1 / r1 | 276 → 48 | 1.00 / 1.20 |
| zone-owncam-skill / cohort-v8-39f214c / P/583 | 772 → 73 | SIM 시각 불명, eligible 770장 중 71장 + 보호 2장 |
| zone-m2-pair / dev2-801-v2-off / r2 | 992 → 102 | SIM 시각 불명, eligible 981장 중 91장 + 보호 11장 |

- 10/10에서 전체 스트림과 manifest 스트림의 처음/끝이 보존된다.
- 리뷰 기준 HEAD의 docs/experiments/tests/configs에 명시된 정적 이미지 이름과 각 표본을 대조: 참조명 삭제 0. 동적 경로·학습 데이터 의존성 보존의 증명은 아니다.
- 시각 있는 8개: 실제 선택은 대체로 1초 간격이며 보호 영상이 더해진다. 삭제 프레임은 직전 보존 프레임 뒤 1초 미만이다. `test-ll-s21`에는 원래도 최대 1.1초 촬영 공백이 있어 보존 간격 최대 1.75초가 있다. 엄밀한 매초 고정 grid라는 주장은 하지 않는다.
- 시각 없는 2개: 별도 보호분을 제외한 표본 수는 floor(10%) 이하이고 처음/끝을 지킨다.
- **vision-worker 행은 솎기 간격이 맞아도 지우면 안 되는 모델 입력 반례**다. 정적 segmentation PNG와 판정 fixture에 이 일반화된 솎기를 적용한 것도 위 차단 사유다.

## 24시간·잠금·원본 상태

- 삭제 목록의 압축 이름을 모두 풀고, delete/keep shard SHA-256을 모두 확인했다.
- 삭제 후보 **1,022,553개 전부**를 현재 원본에서 `stat(follow_symlinks=False)`했다. 누락 0. 논리 크기 `23,672,815,675` bytes, 할당량 `25,495,932,928` bytes로 manifest와 일치했다.
- 고정 cutoff `1790683918.5392919`보다 새로 바뀐 삭제 파일 0. 가장 최신 mtime은 `1790683914.8143091`이다.
- `scripts/outputs_prune.py:24,136–161`은 24시간 상수와 살아 있거나 상태 불명인 agent lock의 배치 차단을 정의한다. v3 실제 경로 `scripts/outputs_prune_stream.py:129–130,225–242,416–423`이 사전 검증과 각 파일 삭제 직전에 이를 재확인한다.
- 임시 `/private/tmp`의 합성 파일/잠금만으로 6개 단언을 확인했다: 오래된 파일 허용, 최근 파일 거부, 살아 있는 PID 거부, 잘못된 owner 기록 거부, lock 경로 보호, 합성 원본 생존. 실제 outputs에서 prune execute를 호출하지 않았다.
- 검토 중 실제 읽기 전용 lock 확인은 `active agent_lock: physics, pid=77247`이었다. 잠금 해제나 소유 프로세스 변경은 하지 않았다. 현재성은 실행 직전에 다시 확인해야 한다.

## 제외 목록과 다음 검토 조건

| 목록 | 범위 | 현재 삭제 후보에서 제외할 GiB |
|---|---|---:|
| E1 | 학습 접근·파지 입력이 확인된 11개 실행 계열, ACT 학습 원본 realtime 포함 | 10.513195 |
| E2 | vision-worker 폐루프·carry-relocalization 모델 입력/라벨 | 0.080780 |
| E3 | pair-stage-probes의 사례별 frames 폴더 | 6.782104 |
| E4 | 위치 추정·RGB 판정·4색 검출·렌더 프로필 수치 원본 | 0.665756 |
| E5 | sim-speed와 dev-a8 비교 기준 | 0.244564 |
| **중복 제거 합계** | **724,107파일** | **18.286400** |

`exclusions.json`의 folder는 해당 폴더와 자손, glob은 전체 outputs 상대 경로에 대한 Python `fnmatch.fnmatchcase`(`*`가 `/`도 포함)다. 다른 glob 라이브러리의 `*` 의미로 바꾸지 않는다. 실제 매칭한 경로를 정렬해 LF로 연결한 SHA-256은 `59b4eb61c1f8c8c299913e009fe4730d28aec9734cca3ea7e70b79f8d62986a3`이다.

다음 제출에는 (1) 이름이 아닌 생성기·모델/학습 레코드로 입력 연결, (2) RGB와 평가 라벨을 함께 포함한 수치 의존성, (3) 제외 적용 후 새 delete/keep 목록·합계·manifest 해시, (4) 모든 D5 원본의 보존 연결을 다시 확인한 결과가 필요하다. 기존 검증의 “모델 payload 겹침 0”은 검사한 이름/형식 안의 결과이므로 현재 목록을 승인할 근거가 되지 않는다.

이번 작업은 독립 보존 검토다. 새 실험·학습·추론·물리 재생 결과가 없으므로 TensorBoard 변환/뷰어 재시작은 하지 않았다. Google Drive도 접근하지 않았다. PR 병합과 실제 삭제는 수행하지 않았다.
