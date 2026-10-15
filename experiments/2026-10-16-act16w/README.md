# ACT16w — MJWarp 재기록·학습

상태: 시작 조건 대기. 교사 관문·학습 데이터·학습·학생 평가·Release는 아직 실행하지 않았다.
작업 브랜치 `claude/act16w`, 초기 backend `06870b6d1ad9233c6e5d63eee2c8c7b81efc66f5`.
Refs #523. 결과는 gcp2/MJWarp 코호트로 구분한다.

사용자 지시(2026-10-16): `warp1:` 준비 결과와 교사 관문 대기열,
조정자의 `SCENE_DECISION:`을 5분 간격으로 최대 10시간 확인한다.
NOT_READY 원인을 보존하고 기다린다. 두 조건 전에 GPU를 임대하거나 실험을 시작하지 않는다.
Mac에서는 소스 작업·짧은 비물리 검사·요약/몽타주 파일 열람만 한다.

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
