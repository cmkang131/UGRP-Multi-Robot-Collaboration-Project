# ACT16w — MJWarp 재기록·학습

현재는 **2회차 재개 진행 중**이다. warp3 40/40과 RECORD_API_READY `0362037`을
수신했고, 새 시드86820의3 SIM초 기록 warm2회를 실행했다. native JPEG와
자기 발행 이력→교사 표적60/60쌍은 정합한다. 의도한 cap_end2회이며 교사
독립 성공률·완주 데이터·ACT 학습·학생 평가는 아직 없다.
[2회차 요약](resume2/summary.json), [warm 원본 해시/감사](resume2/warm-receipts.json),
[파일럿 대기열](resume2/pilot-queue.json), [관문표](resume2/rejection_table.json).

1회차10시간 대기 종료 기록은 기존 `summary.json`과 `wait-*`에 보존했다.
warp3의40/40은 시드8317100–8317139가 warp1 디버깅과 겹쳐 독립 확증으로
세지 않는다. 새 기록86820–86869와 heldout91620–91659를 분리하며,
기록 단계의 독립 n/N은 별도 집계한다. Refs #523, PR #539 DRAFT.

소스는 교사 라이브러리 `6f057f7e` → 이를 MJWarp·장면·NumPy 실행으로
연결한 관문 controller `f0db6b1a` → controller를 그대로 호출하고 JPEG를
기록하는 API `0362037`로 구분한다. 결과는 gcp2/MJWarp 코호트다.
Mac은 소스·짧은 비물리 검사·요약/몽타주 열람만 한다.

## 실행 순서와 고정 조건

1. 장면 결정, backend SHA, 교사 SHA, 관문 대기열과 실제 존재하는
   `rejection_table`을 확인한다. 시작 시 gcp2 작업 임대를 만든다.
2. 같은 장면의 MJWarp 교사 성공 ≥95%, 최소 40회. 학습 카메라는 끈다.
   원인 분포·관문표·실패 1–2회와 성공 1회 시계열을 먼저 검토한다.
   최대 3라운드, 같은 결함이 3라운드째면 중단한다.
3. 통과한 교사로 학생과 동일한 640×480/10 Hz/고정 화각을 기록한다
   (최종 실제 camera contract와 대조). 실패·HOST_ERROR·cap_end도 분모에 남긴다.
   교사 raw, 학생 입력, 평가 truth를 분리한다. 보이지 않는 대상 및 들고 있는
   대상의 세계 좌표를 행동 입력으로 읽지 않는다.
4. 단일 dataset manifest, 시드, optimizer steps, chunk8/0.1 SIM초를 고정하여
   전체 이력 A와 `history_causal_split_v1` B를 비교한다. B는 16개 발행 이력의
   wheel/pulse만 TRAIN 평균으로 바꾸며 PWM·나이·작업 토큰·clock·RGB는 보존한다.
   같은 변환을 훈련과 추론에 적용하고 adapter에 저장한다.
5. 선택 기준은 별도 개발/validation 집합에 고정한다. h4 커리큘럼,
   h5 DAgger 1–2회는 각각 독립 비교한다. 새 최종 평가 40개는 선택·튜닝에
   사용하지 않는다. h1/h2/h3는 학습 신호 전용 기본 off 옵션이며 실행 경로에
   guard나 손으로 짠 파지 경로를 넣지 않는다.
6. 최종 새 시작 40회 n/N·관문표와 실패2/성공1 몽타주를 gcp2에서 만든다.
   가능한 C CPU 견고성 확인은 별도 분모다. 모델은 Release 재다운로드·전체
   해시·모델 로딩 검증 후에만 배포 완료로 표시한다.

L4 합계 최대 8시간(교사/기록/학습/평가의 GPU 점유 모두 포함).
사용 project/account는 `ugrp-sim-b-1014`/`changmin5781@gmail.com`만 허용한다.
다른 작업의 임대/프로세스가 있으면 VM을 정지하지 않는다.

## 참고 자료

- ACT16a: `../2026-10-16-act16a/` (별도 worktree
  `/Users/changmin/projects/ugrp-wt/act16-analysis/experiments/2026-10-16-act16a/`).
  정렬 탈락22/40·재추론 교정복사79.4%는 이전 분석 수치이며 이번 측정이 아니다.
- [ACT 원 논문](https://arxiv.org/abs/2304.13705): action chunk 학습의 근거.
- [DAgger](https://proceedings.mlr.press/v15/ross11a.html): 학생 유도 상태 분포에서
  교사 라벨을 모으는 반복 학습. 재라벨 교사는 학생 실행에 개입하지 않는다.
- [Causal Confusion in Imitation Learning](https://arxiv.org/abs/1905.11979),
  [Fighting Copycat Agents](https://arxiv.org/abs/2010.14876): 이력 의존성 A/B의
  동기이며 이번 과제에서 인과 효과·성공 개선을 입증한 것은 아니다.
- [Curriculum Learning](https://icml.cc/2009/papers/119.pdf): 쉬운 시작에서
  범위를 넓히는 표집의 근거. 실제 난이도 구간은 TRAIN 분포에서만 정한다.

검증된 실행 결과와 학습 곡선은 실행 후 추가한다. 과거 gcp1 데이터는 접근하지 않는다.


## 대기 중 준비한 코드

- `scripts/act16w_prerequisites.py`: 5분 확인·최대10시간, 조건을 발견해도
  자동 실행하지 않고 실제 대기열 검토 단계로만 넘긴다.
- `scripts/act16w_input.py`: 기본 off, TRAIN 평균 wheel/pulse 마스크를 훈련과
  추론에 공통 적용한다. v3 adapter는 기본 ACT 로더에서 거부된다.
- `scripts/act16w_runtime.py`: gcp2 실제 metadata와 고정 ACT 소스,
  교사 관문·장면·데이터 감사 파일의 해시를 검증한다.
- `scripts/train_act16w.py`: 기존 ACT 라이브러리 `3f99d58c`를 별도 source에서
  재사용하는 유한 학습 실행기. CUDA 실제 학습·저장·로딩 검증은 아직 안 했다.
- `scripts/act16w_curriculum.py`: TRAIN 시작 거리·절대 각도의 종류별 경험
  백분위 순위를 합해 쉬운 에피소드부터 연다. optimizer 진행률에 따라 허용
  에피소드 수를 선형으로 늘리는 조정자 설계다. 기존 표집은 기본값이다.

03:22 KST: 원격 `claude/act16w` push 확인. 기반 `claude/warp-act`가 아직
원격에 없어 해당 base의 draft PR 생성은 실패했다(Branch not found).
warp1이 기반 브랜치를 게시한 뒤 다시 만든다. 다른 작업의 브랜치는 push하지 않는다.


03:49 KST, 조정자의 03:45 장면 결정을 확인했다. ACT는
`walls_floor_contrast_v5_indigo110_s80` + v1 바닥 + `no_mip_v1`이다.
[결정 원문과 SHA](scene-decision.json). scenetex5의 NOT_READY는 경계 알고리즘
포함 관문의 판정이며, 이후 조정자가 선택한 **장면 결정**과 구분한다.
ACT16w의 MJWarp 장면 바인딩·RGB·교사/학생 성공은 아직 측정하지 않았다.

DAgger 표적은 학생이 실제 방문한 상태의 교사 첫 행동이다. 학생 경로의 다음
시점 교사 질의를 현재 상태의 교사 미래 chunk로 이어 붙이지 않는다. 별도 교사
branch rollout이 없으면 h0만 유효하고 미래 7개는 padding 처리한다. 학생의
RGB/발행 이력은 원래 그대로 보존하며 교사의 제안으로 교체하지 않는다.


04:23 KST: `scripts/act16w_dagger.py`에 pre-hover 교사 h0 라벨 수용 검사와
7개 미래 horizon padding을 준비했다. oracle phase/실패/시간 정렬/입력 감사를
검사하고 거부 사유·누적 관문표를 반환한다. 학생의 발행 명령은 수정하지 않는다.
학습 라벨 질의기는 명시적으로 발행한 초기 OPEN PWM보다 낮은 닫기 명령을
하나라도 본 뒤에는 그 에피소드에서 teacher callback을 호출하지 않는다.
측정 관절·접촉·물체 위치 없이 잠재 holding 구간을 학습 수집에서 제외한다.
이 검사는 recorder/actor 통합과 실제 DAgger rollout을 완료했다는 뜻이 아니다.
비물리 검사 총18통과·torch1skip이며 학생 실행/학습 효과는 미측정이다.

`no_mip_v1`은 원본 `sim/camera_render_quality.py`에서 GL_LINEAR min filter다.
[공식 MJWarp render_util 소스](https://github.com/google-deepmind/mujoco_warp/blob/main/mujoco_warp/_src/render_util.py)
의 `create_warp_texture`도 LINEAR Texture2D를 만든다. 웹 main 확인이므로 설치된
MJWarp 소스 SHA와 실제 렌더 sampler 확인은 GCP 실행 전 별도로 한다.


04:56 KST: warp1의 `teacher-gate-queue.json`을 찾았으나 backend_readiness는
NOT_READY, commands는 null, 필수 rejection_table.json은 미작성 상태다.
[대기열 원문·해시·존재 확인](warp1-queue-receipt.json). 장면 결정은 별도로
받았지만 모델 배치 호환성·전체 교사 비용·기록/학생 통합 미완료가 남아 있다.
이 대기열을 실행 승인으로 취급하지 않았고 GPU 사용은0이다.

05:24 KST: 새 비물리 시험5파일을 CI glob에 등록했고8개 shard 목록에서
각각 정확히1회 포함됨을 확인했다. [목록 검증](ci-registration.json).
로컬 전체 suite나 원격 CI를 실행한 결과가 아니다. 학습 감독 중단 파일은
RESOURCE_CAP 대신 SUPERVISOR_STOP으로 구분하도록 보고 분류를 바로잡았다.

06:48 KST: 기반 `claude/warp-act` 게시를 확인하고 `90a25999`를 작업 브랜치에
병합했다. 실제 대기열과 거부 표는 존재한다. backend는 여전히 NOT_READY이고
실행 명령은 없다. 장면 결정은 받았지만 대기열의 장면 미승인 문구는 아직 갱신되지
않았으므로 장면 적용 완료로 간주하지 않는다. 초기 preflight 표는
`preflight-initial.json`, 현재 상태는 `rejection_table.json`에 구분했다.

06:50 KST: [draft PR #539](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/539) 생성.
준비 코드 검토용이며 교사·학습·새40평가·Release는 미실행이다.

07:18 KST: 조정자 [후속 작업 지정](upstream-handoff.json)에 따라 warp1 대신
warp3의 DISTINCT_STARTS PASS·교사≥95%/≥40·RECORD_API_READY를 확인한다.
기존 watcher를 교체했으며 최초 시작 시각과13:14 KST 대기 종료는 유지했다.
현재 서로 다른 시작 검증 보고만 받았고 교사/기록 API는 대기 중이다.
watcher 검사11통과, 전체 신규 비물리 검사 누계25통과·torch1skip이다.

대기 중 [비교 조건](comparison-protocol.json)과 [최종40개 계획](final-eval-plans.json)을
고정했다. act16a가 제안한91620–91659 전체를 최종 평가로 예약하며 그 문서의
개발20/확인20 구분은 사용하지 않는다. TRAIN45·validation5·DAgger TRAIN20은
이전 분석의 시드 범위를 gcp2/MJWarp에서 새로 기록할 계획이고 아직 실행하지 않았다.
DAgger는 같은10000스텝의 새 초기화와 D0 TRAIN 정규화 통계를 써서 추가 업데이트
효과와 분리한다. h1/h2/h3의 손실 결합은 아직 구현하지 않았으며 실제 효과로 보고하지 않는다.
전체 비교가8시간 안에 안 들어가면 미완료로 남기고 상한을 넘기지 않는다.

08:17 KST: warp3은 독립40개 참조를7모델 그룹으로 나눠 첫7개 결과를 기다린다.
API 계약은 설계 기록이며 RECORD_API_READY가 아니다. RUNNING 0/40은 최종
실패율이 아니다. watcher는 실제 RUNNING/PASS 표기를 읽고 RUNNING인 동안
기록을 허용하지 않는다.

## 대기 종료

첫 시작03:14:16 KST, 요청한 종료13:14:16 KST. 마지막 확인13:15:54 KST,
123회 확인 후 watcher exit0. 마지막 확인은 요청 상한보다97.8초 늦었으며 원인은
확인하지 않았다. [최종 대기 증거](wait-final-receipt.json)에 실제 시각을 보존했다.
조건을 갖추지 못해 기록·학습은 시작하지 않았다. GPU0시간·추가 VM 계산비용$0,
자기 원격 프로세스/임대/VM 정지 시도0이다. 타 작업을 건드리지 않았다.

준비 코드: 이력 A/B의 훈련·추론 동일 마스크, TRAIN 커리큘럼, pre-hover DAgger
h0 라벨 검사, 유한 L4 학습기. 비물리25통과·torch1skip, syntax/CLI help 통과.
실제 CUDA·데이터 기록/교사 재라벨 연결·학생 rollout은 검증하지 않았다. h1/h2/h3의
손실 결합도 미구현이다. [학습 곡선](training-curves.json)은 미측정 상태다.
[관문표](rejection_table.json)는 준비 조건의 탈락 표다. 학생 성공0/40이나
A/B·DAgger 효과를 측정한 결과로 해석하지 않는다.

Gemma4-31B@DeepInfra 가격+50% 감시 경보를 사용자에게 알렸다. 새 LLM 배치0이며
[수신 기록](endpoint-alert-receipt.json)은 독립적인 새 가격 측정이 아니다.

## 2회차 warm의 검증 범위

기본 launch는 loop77.88초/3 SIM초=25.96 wall/SIM이었다. 기본 off인
`whole_control_graph_v1`은 같은400 physics ticks를 한 CUDA graph로 기록하는
후보이며 capture가 persistent state를 바꾸지 않은 것은 확인했다. 별도 공유
부하에서46.64 wall/SIM으로 개선은 확인되지 않아 채택하지 않는다.
이 두 측정은3 SIM초 진단이고 정식 첫30 SIM초 속도 관문이 아니다.

원본 JPEG·네이티브640×480/10Hz·K/D·이전 발행 이력·교사 command와
phase-before/after를 별도 CPU 감사기로 확인했다. 학습 승인·40회 독립 관문·
full-skill done 라벨은 아직 검증하지 않았다. 비물리27개 통과이며 CUDA
ACT 학습·저장/재로딩은 아직 미실행이다.

[공식 MJWarp 성능 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/#performance-tuning)는
CUDA graph·용량·solver의 순서로 성능 조사를 안내한다.
[NVIDIA Warp ScopedCapture](https://nvidia.github.io/warp/v1.11/api_reference/_generated/warp.ScopedCapture.html)를
확인하고 launch 횟수만 바꾼 후보를 측정했다. solver·시간 간격·물리와
성공 임계값은 바꾸지 않았다. 공유 부하가 달라 두 속도의 인과 차이는 주장하지 않는다.
