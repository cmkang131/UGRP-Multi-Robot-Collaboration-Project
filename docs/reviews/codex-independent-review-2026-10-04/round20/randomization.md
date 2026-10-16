# R20 — #213 도메인 랜덤화의 실제 구현과 최종 경로 적용 범위

**판정: 새 결함을 추가하지 않는다. 기존 시각 랜덤화의 부분 구현은 존재하지만, 최종 OpenCV 선택 이후 #213의 학습·단계별 인수 계약은 재연결이 필요하다.** optional RL의 dynamics reset, 정지 렌더의 외형 변화, 학습 시 이미지 증강, 현재 고정 화면 실험을 하나의 “randomization”으로 묶으면 잘못된 완료·인과 주장이 된다.

기준은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, PR #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, PR #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`다. 코디네이터가 2026-10-04 09:02 UTC에 공식 head를 재확인했다. 로컬 checkout HEAD는 이전 `f2577bb5`이므로 현재 source는 checkout 내용 대신 위 Git object에서 필요한 `.py`만 읽었다. 이 보고서는 실행 성능을 새로 측정하지 않았다.

## 1. 이슈가 실제로 요청한 것

[#213 공식 본문](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/213)은 VIS2 깨끗한 렌더링 결과 이후의 **비전 모델 학습 전용** 후속 작업이다. 조명 밝기·방향, 벽·바닥 색·질감, 카메라 노이즈·흐림·노출을 일부 학습 자료에 약하게 섞고 단계별로 올리되, 깨끗한 화면 성능의 사전 허용폭을 지키도록 요구한다. 30–50%는 예시이며 강제 확률로 읽지 않았다. 4조건 통신 비교 화면은 고정, clean/변형/향후 실물 평가는 분리, 변형 종류·범위·단계 기준 사전등록, 새 seed, 시험 세트 한 번 평가가 명시돼 있다. 전체 댓글은 sim2real #214 연결 한 개이며 이 요구를 OpenCV용으로 바꾸는 승인 내용은 없다.

반면 [#216의 10/3 사용자 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5965712469)은 최종 위치 추정을 OpenCV로 정하고 학습 분할망을 비교 기록으로 보존한다. main의 [`docs/research_todo.md` S4](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/research_todo.md#L172-L178)는 여전히 VIS2 학습 후속 문구다. 이것은 OpenCV에 새 학습을 요구하는 승인으로 해석할 수 없다.

## 2. 이미 구현된 PR #282를 빠뜨리면 안 된다

[#282 공식 PR](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/282)은 2026-09-29 병합(`b10035db293289205b7618d62b4baf749e6503d1`), `seg-lightfloor`의 외형 랜덤 정지 렌더와 VIS3 분할망 미세조정을 담는다. [#216의 공개 9/30 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5902438931)에도 연결돼 있다. 이 PR의 공식 설명은 정지 렌더·오프라인 B1 비교이며 물리 E2E·실제 카메라 검증이 아니라고 한계를 명시한다. 이번 검토는 공개 설명을 확인했을 뿐 그 점수, 결과 JSON, 실제 이미지, 체크포인트, 원본/heldout 자료를 재평가하지 않았다.

모든 아래 `seg-lightfloor` source 링크의 기준은 main `b23fc087`이다.

| 경로 | 실제로 무작위화하는 분포와 적용 시점 | 고정되거나 범위 밖인 것 |
| --- | --- | --- |
| [`floors.train_looks`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/floors.py#L34-L56) | 기본 seed 4242로 24개 외형. 아래 U/log-U는 **거절 전 proposal**이며 최종 24개는 반올림·RGB 거리 거절 후 선택한 값이다. HSV 밝기 U(.18,.80), 20% 대비 1/나머지 U(1.08,2.0), 색상 U(0,1), 채도 U(0,.40), 두 색의 hue 차 ±.03; 광량 log-U(.22,.45), 벽 RGB gain log-U(.8,1.7), 반올림. 코드에 선언한 held-out 외형 평균 RGB와 거리 .10 미만 후보 거절 | held-out은 코드의 설계 상수다. 그 외형 결과를 읽지 않았다. 평균 RGB 배제는 임의 영상·질감·물리 상태의 독립성 증명이 아니다 |
| [`render_static_set`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/render_static_set.py#L82-L133) | 각 look마다 새 scene/world 구성 시 XML의 ground checker RGB, light RGB gain, wall RGB gain 적용. 이후 별도 RNG로 자기·짝 pose/팔 명령/빔 pose 샘플. frame 루프는 time 불변을 assert | 조명 **방향**, 카메라 FOV·왜곡, 질감의 패턴 자체, motion blur를 무작위화하는 구현은 이 경로에 없다. renderer는 실행하지 않았다. 코드 주석의 build 중 초기 settle과 per-frame physics advance 없음은 구분한다 |
| [`seg_ft.CacheDataset`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/seg_ft.py#L160-L200) | 학습 sample 읽기마다 flip(0.5), replay에 한정한 label-guided floor recolor, 채널 cast, gamma, gain U(.75,1.3), bias U(-.06,.06), Gaussian RGB noise σ=.01. `C_mix_rgb` recolor 확률 .3은 **replay 중 floor recolor 확률** | .3을 전체 자료 중 변형 비율로 읽으면 안 된다. augment=True인 sample에는 기본 gain/bias/noise도 적용된다. 이 image augmentation은 물리 episode reset 함수가 아니다 |
| [`train_run`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/train_run.py#L28-L109) → [`seg_ft.train`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/seg_ft.py#L203-L262) | 명명된 후보마다 seg-v2에서 시작해 정해진 epochs로 학습한다. 공통 cache 전체에서 3% frame를 먼저 뽑고 해당 후보 kind와 교차하여 내부 validation으로 분리. validation·precise BN은 augment=False, BN 기본 입력은 train_idx | inspected caller에는 clean 허용폭을 통과하면 다음 강도를 자동 승인하는 단계 machine이 없다. 후보별 내부 validation은 새 외형/새 trajectory 일반화 증명이 아니다. 실제 데이터 누수를 발견했다는 뜻도 아니다 |

## 3. seed, reset, identity와 train/eval 분리

- **외형 seed와 pose seed가 다르다.** `render_static_set.all_looks()`는 `train_looks(24)`의 기본 seed 4242를 쓴다. CLI `--seed`는 SHA256(`seed|split|look`에 farwall mode를 추가)의 앞 8 hex로 pose RNG를 만든다. 따라서 CLI seed만 바꾸면 다른 pose draw를 얻지만 기본 24개 외형 자체는 같다. “새 seed”가 곧 새 appearance distribution이라는 주장을 지지하지 않는다. 이것은 분리된 stream의 설계이며 새 결함이 아니다.
- **정지 렌더의 적용 경계:** look마다 fresh world를 한 번 만들고 frame별로 pose를 배치한다. optional RL처럼 reset마다 dynamics에 배율을 곱하는 경로가 아니다. 렌더러는 look dict·look hash·실제 derived seed·split·map ID·row RGB SHA를 출력하도록 작성돼 있다([source](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/render_static_set.py#L194-L252)). 이 writer 계약을 읽었으며 실제 manifest는 열지 않았다.
- **학습 identity:** checkpoint에 input normalization·초기 checkpoint identity가, train_info에 seed·epochs·recolor/cast/gamma·frame 수 등이 기록된다. 내부 shuffle/augmentation seed는 학습 seed·worker initial seed·sample index에 의존한다. 코드에 존재하는 기록과 실제 산출물 보존·등록 완료를 구분한다.
- **평가 분리:** validation과 BN은 증강을 꺼서 읽는다. [`eval_dev.py`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/eval_dev.py)는 별도 DEV 디렉터리의 외형별 지표를, [`b1_eval.py`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/experiments/2026-09-29-seg-lightfloor/b1_eval.py)는 기존 B1 frame/시작오차/seed/필터를 유지한 checkpoint 비교를 제공한다. 이 caller를 VIS2 원래 clean test의 재인수나 #213의 시험 1회 실행 증거로 바꾸어 읽지 않는다. 기존 실제 split·시험 호출 횟수·후보 선택 이력은 이번 범위 밖이다.

## 4. 현재 실행 caller와의 정확한 연결

| 경로/기준 pin | 실제 consumer·reset/화면 정책 | #213에 주는 근거 |
| --- | --- | --- |
| PR #363 `66ff0978`: `run_pair_highpose` → HIGH Runtime → HighPoseSource | [`Runtime`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_runtime.py#L475-L480)이 HIGH provider를 명시 주입. [`HighPoseSource`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/vision_pose_source_highpose.py#L26-L85)는 OpenCVObserver, learned_segmentation=False. PF seed는 전달하되 segmentation checkpoint를 만들지 않음. calibration/gates/profile/detector를 runtime identity에 기록 | PR282의 학습된 robustness가 현재 HIGH에 옮겨졌다는 근거가 없다. OpenCV 결정이 학습망 증강 효과를 상속시키지 않는다 |
| 동일 PR #363의 `sim.final_pair_v3.PhysicsBackend` | [`make_scene`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/sim/final_pair_v3.py#L15-L41)는 `floor_light_v1` 고정 적용. [`reset`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/sim/final_pair_v3.py#L67-L77)은 reset 후 같은 profile을 검증·기록 | 현재 episode reset이 무작위 조명·색 draw를 적용한다고 볼 근거 없음. 공통 렌더 조건의 고정이며, arm별 행동이 달라도 픽셀 시퀀스가 동일하다는 보장은 아님. 고정 profile의 named/hash/XML provenance는 [`render_profile.install`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/render_profile.py#L99-L165)에 존재 |
| PR #371 `a009112f`: `run_pair_llm` → `pair_llm_case` → v88 Runtime | [`CLI`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_pair_llm.py#L119-L146)는 일반 경로에서 provider_factory=None, synthetic 경로에서는 blind provider. [`Runtime`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_final_pair_runtime.py#L16-L36) 기본은 `vision_pose_source_pair_v3`→VisionWorkerClient. PhysicsBackend는 별도의 동일 고정 floor_light_v1 경로 | HIGH OpenCV와 동일 provider라고 쓰지 않는다. 이 차이는 **R12에 이미 확인**된 경계다. 여기서 PR282의 C_mix_rgb checkpoint 채택·#213 단계 인수를 증명하지 않았다. 세 arm viability이며 #213의 네 조건 본실험 완료가 아님 |
| main `b23fc087`: `train_masterpi_v2` → `MasterPiTrainingEnvV2` | optional `--domain-randomization` 기본 0, 0~.30에서 dynamics 수치별 U(1−s,1+s) 배율; reset의 RNG로 world 재구성 | **기존 O11** `dynamics=None` baseline 누적 코드는 현 pin에도 존재. **기존 R13** 보정 21→6 consumer 경계도 별도. 양쪽 모두 비전 학습 appearance 랜덤화가 아니므로 #213 해결·현재 OpenCV 실패 원인으로 합산하지 않음 |

seed routing의 일반적인 paired design/CRN 제한은 기존 연구 검토를 유지한다. 이번에는 environment/PF seed와 appearance-generation seed의 서로 다른 역할만 보강했다. runner의 seed·source/bundle hash 기록은 존재하지만 그것만으로 독립 split·새 지도·실물 분포를 인증하지 않는다.

## 5. 지금 필요한 설계 기록과 허용되는 주장

이슈를 닫거나 OpenCV 과제로 전환하려면, 먼저 기존 결정을 바꾸지 않는 범위에서 **대상 consumer를 명시**해야 한다. 현재 소스·공개 결정을 기준으로 합리적인 두 갈래는 (a) 학습망 증강을 legacy 비교 연구로 보존하고 #213의 현재 적용을 보류하거나, (b) 별도 승인된 OpenCV 영상 스트레스 검증 계약을 만드는 것이다. 후자는 학습 randomization 효과와 다른 질문이므로 clean/변형 frame의 gate reject·유효 관측률·위치 오차 등을 구분할 수 있지만, 이를 이번 검토에서 새 구현·평가·실물 촬영 요청으로 승격하지 않는다.

필요한 계약은 선택 consumer/version, 외형·pose·센서 중 실제 변화 축과 고정 축, train/development/test의 분리 단위, 단계별 clean 허용폭과 변형 개선 기준, 사전 동결·시험 소모 기록, 통신 arm 공통 fixed scene/profile이다. 기존 PR282 외형·seed·hash 기록은 재사용할 수 있으며 “아무 provenance가 없다”거나 “randomization 코드를 새로 만들어야 한다”는 결론이 아니다.

현재 확인한 source만으로 허용되는 주장은 **특정 legacy 분할망의 합성 외형 학습을 위한 도구가 존재하고, 현재 HIGH는 그 학습망을 소비하지 않으며, inspected 현재 물리 caller는 고정 render profile을 적용한다**는 것이다. OpenCV robustness 향상, 깨끗한 화면 비열등성, sim2real 성공, 네 조건 통신 효과는 입증하지 않았다. 공식 PR의 과거 수치는 작성자가 명시한 정지·오프라인 범위로만 남는다.

## 6. 한정 검증과 coverage

`randomization-scope-repro.py`는 exact source의 `train_looks`와 `look_xml_transform`만 stdlib/NumPy로 실행했다. 후자는 검토자가 작성한 작은 XML에만 적용했다. 24개 외형 동일-seed 결정성, 다른 appearance seed의 draw 변화, 선언된 held-out 평균 RGB와 최소 간격 `0.112042403 ≥ .10`, same-base XML 결정성, light 방향·camera 속성 보존을 확인했다. source AST로 `all_looks`가 appearance seed를 CLI로 받지 않고 기본값을 쓰는 것도 확인했다. 물리 모델·렌더러·torch·실제 이미지·데이터는 실행/열람하지 않았다. 이 값은 실제 영상 분포 거리나 성능 효과가 아니다.

수동으로 읽은 범위는 `floors.py`, `render_static_set.py`, `seg_ft.py`, `train_run.py`, `eval_dev.py`, `b1_eval.py`, `test_seg_lightfloor.py`의 해당 caller 전체, HIGH provider/observer와 runtime construction, 두 runner의 provider/backend 선택·reset·기록, fixed render profile 및 optional RL randomizer의 관련 구간이다. 아래 파일 기반 provenance는 읽기용 source snapshot 26개를 exact Git blob과 대조한다. 저장소 전체 augmentation·모든 실험 caller·실제 등록 파일·결과의 전수 감사가 아니다.

기존 참고: [R19 issue map](../round19/issues.md), [O11](../publication/final-optional-issue.md), R4 학습/평가 경계 (Mac: `evidence/review-notes/round4-training-eval-boundaries.md`), [R12 현재 v88 worker caller](../round12/runtime.md), [R13 calibration consumer](../round13/consumer.md). 이들의 기존 문제 수를 다시 늘리지 않는다.

독립 QA: 평가 검토자가 공식 #213 요구와 #216 최종 결정, 26개 snapshot의 Git bytes/hash 및 별도 임시 복사본의 합성 재현을 확인했다. 합성 출력은 저장 golden과 byte 동일(`229196f0258598afd8ce6f3ae091c34dfb7720c150bf7eca483918d654a9b40d`)이었다. proposal/accepted-look 분포 표현을 보강했으며, 새 P2 없이 위 범위로 보고 가능 판정을 받았다. [독립 검토 기록](validation.md#randomization).
