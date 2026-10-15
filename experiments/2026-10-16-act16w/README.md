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
