# UGRP 디스크 사용 관리

2026-09-26 사용자 요청 "남은 게 중요한 게 아니라 이 프로젝트 자체가 너무 많이 잡아먹고 있다"에 따라 작성했다. 목표는 여유 공간 경보가 아니라 **프로젝트 자체의 사용량을 줄이고 작게 유지하는 것**이다. 수치는 `du` 기준 할당 크기(GiB)다. APFS clone은 전체 크기로 세므로 물리 사용량보다 클 수 있다. 측정 원본은 [사고 기록 폴더](../experiments/2026-09-26-disk-incident/footprint/)에 있다.

## 1. 한눈에 보기

| 구분 | 측정 (09-26 15:26) | 적용 뒤 측정 (16:05) | 제안 예산 |
|---|---|---|---|
| 기본 체크아웃 `outputs/` | 66.74 | 67.98 (Codex 은퇴분 0.82 유입, 다른 작업의 새 실행) | ≤ 40 |
| worktree | 78.07 (69개) | 63.04 (57개. 이 PR의 worktree 등 2개는 sparse) | ≤ 10 |
| 기본 체크아웃 나머지(`experiments/` 1.01, `.git` 0.96, `work/` 1.13 등) | 3.47 | 3.46 | ≤ 6 |
| 가상환경(`Project-Runtimes/ugrp`) | 1.12 | 1.12 | ≤ 2 |
| **프로젝트 합계** | **149.4** | **135.6** | **≤ 60** (58 + 여유 2) |
| 에이전트 상태(`~/.codex` worktree 제외, `~/.kiro`, `~/.claude`) | 6.55 | 6.77 | 예산 밖, 보고만 |

- 2026-09-26 18:24–18:54 사용자 승인 4항목을 적용했다. 결과·제외 목록·검증은 [적용 기록](../experiments/2026-09-26-disk-apply/README.md)에 있다. 아래 1–2절 수치는 그 전 측정이다.
- 처음 적용은 두 가지다.
  - 병합된 Codex-app worktree 14개를 은퇴시켜 checkout 14.38 GiB(추정)를 확보했다. 파일시스템 여유는 32.47 → 46.88 GiB로 늘었는데, 이 값에는 다른 작업의 쓰기가 섞여 있다.
  - 이 PR의 worktree를 sparse로 바꿔 1.05 GiB → 0.13 GiB가 됐다.
- 두 측정 사이에도 다른 에이전트의 새 실행·worktree가 늘었으므로, 차이 13.8 GiB는 순수 절감량이 아니다.
- 예산에 도달하려면 아래 3절의 사용자 결정이 필요하다. 가장 큰 두 가지는 worktree를 sparse로 바꾸는 것과 오래된 raw를 외부로 옮기는 것이다.
- `outputs/`는 하루 5–15 GiB씩 늘었다(폴더 이름 날짜 기준 09-24 8.3, 09-25 15.1 GiB). 보관 주기 없이 정리만 하면 며칠 안에 다시 찬다.

## 2. 측정 결과 (09-26 14:42–15:49, 적용 전)

### 2.1 기본 체크아웃 `outputs/` (66.74 GiB, 497항목)

- 파일 종류별: 이미지 46.06 GiB(JPEG 106만 장, 평균 약 16 KB), JSON 11.42, 압축 3.91, 모델·배열 2.50, 영상 1.37, 기타 1.49.
- 큰 폴더: `retired-worktrees` 12.25, `simulation-realtime-20260923` 3.69, `jev-semantic-motion-20260921-v1` 3.52, `zone-rgb-outcome-v2-20260925` 3.42, `plan-guidance-20260925` 2.93, `experiment-archives-20260907` 2.71, `act-action-training-20260924` 2.60, `dynamic-team-recovery-20260925` 2.33.
- 연구 줄기별 분류(폴더 이름 기준 추정, 합계는 반올림):

| 줄기 | GiB | 비고 |
|---|---|---|
| `retired-worktrees` (9/7–9/20 worktree 보관분) | 12.25 | 9/23에 프레임 23.4 GiB 삭제 뒤 남은 결과·영상·모델 |
| 현재 연구: zone·owncam·M1·M2 | 10.74 | dev 4.23 / test 2.92 / 미분류 3.60 |
| Jev (9/21) | 10.49 | 보조 과제 |
| 계획·동적 협업·재파지·지도 (9/24–25) | 9.25 | |
| 실시간·시뮬레이션 속도 (9/23–24) | 5.92 | 현재 연구 대상 아님(사용자 방침) |
| RGB·파지 (9/10) | 5.71 | |
| dispatch·ACT·markerless·nav·pair | 8.18 | 9/8–9/24 |
| 9/7 실험 ZIP 보관분 | 2.71 | 9/22 정리로 비압축본을 지운 뒤 남은 **유일 사본** |
| TensorBoard·기타 | 1.49 | 스냅샷 98개 0.10 GiB + archive 0.26 GiB |

### 2.2 worktree (69개, 78.07 GiB)

| 위치 | 개수 | 합계 | 추적 checkout | 무시 `outputs/` | 캐시 |
|---|---|---|---|---|---|
| `~/.codex/worktrees` | 23 | 27.08 | 23.52 | 3.50 | 0.07 |
| `ugrp-wt/` | 42 | 44.54 | 43.86 | 0.58 | 0.10 |
| `ugrp-worktrees/` | 3 | 5.40 | 3.14 | 2.24 | 0.02 |
| 기타(`ugrp-kiro-agent`) | 1 | 1.04 | 1.04 | 0 | 0 |

- 전체 checkout 1개는 약 1.03 GiB다. 그중 0.93 GiB가 `experiments/`의 추적 미디어다(아래 2.3).
- 주인별: Claude 20개 23.19 GiB, Codex 23개 27.08 GiB, Kiro 26개 27.79 GiB.
- 15:49 기준 56개: 병합됐고 열린 PR 없음 19개(22.14 GiB), 열린 PR 22개(23.53 GiB), 미병합이며 열린 PR 없음 15개(18.14 GiB).
  - 미병합 15개는 Codex 9개(PR 없는 브랜치 6, detached 감사 2, 닫힌 PR #120 1)와 동결 소스 detached 6개다.

### 2.3 추적 `experiments/` (origin/main, 1.00 GiB)

- 종류별: zip 0.69 GiB(51개), gz 0.11(680), mp4 0.06(129), json 0.06(1,673), jpg 0.05(627), png·jsonl·xml 각 0.01.
- 무거운 미디어(sparse에서 빼는 종류) 합계는 0.93 GiB다. 대부분 9/10–9/17 증거 ZIP이다: `2026-09-10-rgb-short-approach` 347 MiB, `2026-09-10-rgb-varied-start` 157 MiB, `2026-09-13-rgb-short-transport` 111 MiB, `2026-09-13-pair-carry-sync` 76 MiB.
- 최근 기록은 작다. 9/20 이후 기록의 미디어는 실험당 최대 5.7 MiB(`2026-09-25-zone-cargo-catalogue`, 파일당 최대 0.5 MiB)다.
- 실행 코드가 읽는 추적 압축 파일은 두 개뿐이다: `experiments/dispatch-skill-integration-20260917/models.zip`, `experiments/2026-09-10-rgb-varied-start/models.zip`(`tests/test_agent_worktree.py`가 소스를 검사한다).

### 2.4 `.git`과 기타

- `.git` 0.96 GiB(pack 931 MiB). 과거 증거 ZIP이 이력에 있어 줄이려면 이력 재작성과 강제 push가 필요하다. 금지된 작업이므로 제안하지 않는다. sparse checkout은 `.git`을 줄이지 않는다(worktree끼리 공유).
- 새 clone에서는 `git clone --filter=blob:none --sparse`(partial clone)에 같은 sparse 패턴을 쓰면, 제외한 과거 증거 ZIP을 내려받지 않는다. 절감량은 측정하지 않았다.
- 기본 체크아웃의 무시 폴더: `work/` 1.13 GiB(Raspberry Pi 이미지 작업 공간), `.venv-dev` 0.26 GiB, `작업 증거/` 0.04 GiB.

### 2.5 실행 1회 크기

| 실행 | 크기 | 구성 |
|---|---|---|
| M1 자기 카메라 1대 에피소드 (`m1-owncam-20260926/test`) | 25–48 MiB (6회 평균 36) | wrist JPEG q90 640×480 5 Hz 1,414–2,748장(장당 약 16 KB) 23–43 MiB, `eval_only/` 0.9–2.1 MiB, 영상 1.8–2.8 MB는 별도 |
| 3대 dispatch LLM 실행 (`plan-guidance-20260925/legacy-1`) | 224 MiB | RGB 스킬 프레임 3,406장 187 MiB, LLM 요청·결정 61개 18 MiB, result.json 3.2 MB, 영상 1.9 MB |
| M2 2대 운반 단계 (`zone-m2-pair-20260926`) | 단계당 159–363 MiB | 프레임 76k장 1.36 GiB |
| 인식 평가 렌더 (`zone-rgb-outcome-v2-20260925`) | 3.42 GiB | JPEG 63k장 |
| TensorBoard 스냅샷 | 98개 106 MiB | 평균 1.1 MiB, 최대 38 MiB |
| 영상 | mp4 2,361개 1.37 GiB | 평균 0.6 MB |

### 2.6 중복

- **worktree마다 들어 있는 추적 미디어 사본이 가장 큰 중복이다.** 전체 checkout 68개 × 0.93 GiB ≈ 63 GiB다. Git은 같은 내용을 `.git`에 한 번만 압축해 둔다.
- `outputs/`와 큰 worktree의 1 MiB 이상 파일 중 내용이 같은 파일: 논리 2.70 GiB, 물리 추정 2.50 GiB. 종류별로 JSON 0.90, 재생용 `model.mjb` 0.76, ACT `model.safetensors` 0.34, zip 0.24, mp4 0.10이다. `retired-worktrees`와 다른 위치 사이의 중복은 논리 1.26 GiB다.
- TensorBoard는 raw 사본이 아니다. 스칼라·텍스트와 결정당 이미지 표본(최대 8장)만 담아 합계 0.36 GiB다.

## 3. 감축 계획 (조치별 GiB)

| # | 조치 | 절감 | 상태 |
|---|---|---|---|
| 1 | 병합된 Codex-app worktree 14개 은퇴(무시 자료 0.82 GiB 이동) | 14.38 | **적용함** |
| 2 | 새 worktree는 sparse checkout (`agent_worktree.py new`) | 개당 0.92 (실측 134 MiB 대 1,077 MiB) | **도구·규칙 적용**, 이후 생성분부터 |
| 3 | 병합됐고 열린 PR이 없는 다른 에이전트 worktree 은퇴 | 22개 23.01(추정), 무시 자료 0.24 이동 | **적용함**(09-26 사용자 승인, 사용 중 5개 제외) |
| 4 | 열린 PR·동결 소스 worktree를 sparse로 전환 (`sparsify`) | 17개 15.59(18.09 → 2.50) | **적용함**(09-26 사용자 승인, 사용 중 7개 제외) |
| 5 | Codex 미병합 9개: HEAD를 `codex/archive-<이름>-0926`에 올리고 SHA 확인 뒤 은퇴 | checkout 9.20(추정), 무시 자료 2.60 이동 | **적용함**(09-26 사용자 승인) |
| 6 | 에이전트당 동시 worktree 8개 상한 | 안정 상태 24개 × 0.14 ≈ 3.4 | **도구 적용**(초과 시 거부) |
| 7 | `experiments/`에 무거운 미디어 커밋 중단(파일당 1 MiB, 실험당 5 MiB) | 이후 checkout·`.git` 증가 방지 | **경고 적용**(pre-commit·CI) |
| 8 | raw 보존 등급(4절)에 따른 외부 보관 | 21.7–46 | 사용자 결정 |
| 9 | 기록된 dev·진단 raw 프레임 솎기(1 Hz + 결정 프레임) | 논리 추정 4.74 (중복 제거 뒤 실제는 더 작음) | **보류**: 삭제 조건(재생성·파생본) 미확인, 목록만 제시 |
| 10 | 앞으로의 캡처 설정(5절) | dev 실행당 60–80% | 러너 주인·사용자 결정 |
| 11 | 같은 내용 파일의 APFS clone 중복 제거 (4 KiB 이상, fclones) | 26.50 계획, `df` +26.77 | **적용함**(09-26 사용자 승인, 해시 재검증) |
| 12 | `.venv-dev` 0.26, `work/` 1.13 | 최대 1.4 | 사용자 결정 |

- 1–7을 모두 적용하면 worktree는 약 10 GiB 이하가 된다.
- `outputs/` 40 GiB 예산에는 8의 앞 세 등급(21.7 GiB)과 오래된 보조 연구 raw 일부의 외부 보관이 필요하다.

## 4. raw 보존 등급 (사용자가 등급마다 결정)

AGENTS.md에 따라 raw 삭제·압축·이동은 사용자가 정한다. 크기는 16:05 측정이다(줄기별 T4–T7만 15:26). 폴더 이름 기반 분류라 추정치다. "기록 참조"는 origin/main의 `experiments/`·`docs/`·`configs/`가 그 폴더를 가리키는지를 뜻한다. `python3 scripts/disk_report.py --sections outputs,retention`이 최신 목록과 참조 여부를 보여 준다.

| 등급 | 대상 | GiB | 제안 |
|---|---|---|---|
| T0 기반 자료 | `tensorboard*`, `agent-locks`, 모델 설치본 | 0.47 | 유지 |
| T1 test 코호트 raw | 이름에 test·final·holdout·cohort가 있는 폴더 | 8.53 (기록 참조 6.11, 참조 없음 2.41) | **기존 raw는 그대로 유지**(봉인 inventory 고정). 앞으로의 코호트는 5절 정책 |
| T2 dev·진단 raw | 이름에 dev·diag·pilot·probe·smoke·sweep이 있는 폴더 | 12.07 (기록 참조 6.63, 참조 없음 5.45) | 기록 참조분은 솎기 또는 외부 보관. 참조 없음분은 열린 PR의 기록인지 먼저 확인 |
| T3 이전 worktree 보관분 | `retired-worktrees/` | 13.07 (오늘 이동분 포함) | 외부 보관 뒤 로컬 삭제 |
| T4 퇴역 연구 raw | 실시간·시뮬레이션 속도 (9/23–24) | 5.92 | 외부 보관 또는 삭제 |
| T5 9/7 실험 ZIP | `experiment-archives-20260907/` | 2.71 | 유일 사본이므로 외부에 두 벌 보관 뒤에만 로컬 삭제 |
| T6 보조 연구선 (9/8–9/22) | Jev, RGB·파지, markerless·nav, pair, ACT, dispatch | 24.4 | 외부 보관 (기록 해시 대조 뒤) |
| T7 현재 연구 | zone·owncam·M1·M2, 계획·동적 협업 (9/24–) | 20.0 | 연구 종료까지 유지. dev만 T2 규칙 |

- 외부로 옮기기 전에 해당 기록의 `raw_index`·manifest 해시와 대조한다. 옮긴 뒤 새 위치를 기록에 추가한다. 로컬 사본만으로는 백업이 아니다.
- T1–T7은 겹칠 수 있다(T6·T7 안에도 test·dev 폴더가 있다). 결정은 폴더 목록 단위로 한다.

## 5. 프레임 저장 (2026-10-01 정책)

2026-10-01 사용자 지시("80기가가 쌓이는 게 말이 안 된다")로 **원본 JPEG 프레임 보존 의무를 어떤 등급에도 두지 않는다.** 확증 코호트도 예외가 아니다. 삭제한 문장과 사유는 AGENTS.md의 "지침 변경 이력"에 있다. 이 절이 2026-09-27의 옛 5절(프레임 용도별 표, dev 1 Hz 솎기 결정)을 대체한다. `dev_1hz_decisions_v1`은 과거 실행의 재현용으로 코드에 남아 있다.

### 5.1 등급별로 남기는 것

| 남기는 것 | 확증·봉인 코호트 | dev·smoke·진단 |
|---|---|---|
| 결과 JSON, 모델 요청·응답 텍스트 | 전부 | 전부 |
| 프레임별 sha256 목록 (`frames.sha256.jsonl`) | 전부 | 전부 |
| 실행 영상 (`execution.mp4`) 등 mp4 | 유지(약 2 MB) | 유지 |
| 프레임 묶음 mp4 (`mp4_v1`) | 필요할 때 선택 | 필요할 때 선택 |
| 원본 JPEG 프레임 | **저장하지 않는다.** 필요한 실행만 `all_v1`을 명시하고 상한을 적는다 | 저장하지 않는다 |
| 쓰기 상한 (실행당) | 기본 64 MiB(프레임 쓰기), 번들·설정에 명시 | 같음 |

- 프레임 sha256이 있으면 나중에 같은 이미지가 다시 나왔는지 대조할 수 있다. 이미지 자체를 복원하지는 못한다. 복원이 필요한 분석은 같은 소스·seed로 재생성한다.
- **이미 봉인된 코호트가 고정한 inventory(sha256/size/mtime)는 과거 증거다.** 이 정책은 그 목록과 원본 파일을 바꾸지 않는다. 이미 쌓인 `outputs/`의 정리는 이 정책과 별개로 사용자 결정이며(AGENTS.md "보존"), 아래 5.4의 도구는 새 실행에만 쓴다.
- TensorBoard 변환(`scripts/tensorboard_tools/zone_study.py`)은 요청 이미지 파일이 없어도 요청 행과 이미지 해시만으로 통과한다(`request_images_hash_only`로 개수 기록). 파일이 있는데 해시가 다르면 여전히 거절한다.

### 5.2 프로필 (`harness/frame_storage.py`)

| 프로필 | 쓰는 것 | 비고 |
|---|---|---|
| `none_v1` (**기본값**) | 프레임 바이트 없음. 프레임마다 `{stream, index, t, sha256, bytes}` 한 줄 | 모든 split |
| `mp4_v1` | 스트림마다 H.264 mp4 하나(원본 JPEG을 ffmpeg로 보냄, crf 28) + 같은 해시 목록 | 시청용(손실 압축). 해시는 원본 JPEG의 것 |
| `all_v1` | 원본 JPEG 전부 (09-27 이전 러너의 동작) | **명시 선택만.** 상한은 그대로 적용 |
| `dev_1hz_decisions_v1` | 1 Hz 표본 + 결정 프레임 JPEG | 과거 재현용, `dev`·`diag`만 |

- `FrameSink(out_dir, profile, split=, cap_mib=, fps=)`가 프로필 적용·해시 목록·상한을 한곳에서 처리한다. `add(stream, t, jpeg, decision=, reason=)`로 프레임을 넣고 `close()`가 mp4를 마무리하며 manifest 블록(`ugrp.frame-storage.v2`: 프로필, 상한, 쓴 바이트, 상한 초과 여부)을 돌려준다. 러너는 이 블록을 실행 기록에 넣는다. 프로필 이름과 상한은 실행 번들 조건의 일부다([실행 버전 관리](execution_versioning.md)).
- 상한 초과는 `FrameWriteCapExceeded`(OSError 하위, errno 없음)로 실행을 멈춘다. 과제 실패도 ENOSPC(HOST_ERROR)도 아니고 **설정된 상한 때문에 중단한 실행**이다. 사전 등록에는 이 종류를 따로 적는다(8절의 `host_error`와 구분).
- 상한은 "무제한" 모드가 없다. 더 필요하면 번들·설정에 새 값을 적고 PR 본문과 기록에 이유를 남긴다.
- 예(러너에 연결할 때): `sink = FrameSink(run_dir / 'frames', 'none_v1', split='dev', cap_mib=64)`; 캡처마다 `row = sink.add(rid, now, jpeg)`; 종료 시 `manifest['frame_storage'] = sink.close()`.

### 5.3 러너와 무관한 안전망

`scripts/write_cap_guard.py`는 어떤 명령이든 감싸서 감시 폴더의 **증가분**(할당 바이트)이 상한을 넘으면 프로세스 그룹에 SIGTERM(그레이스 뒤 SIGKILL)을 보내고 `write-cap.json`을 남기며 종료 코드 3으로 끝난다. 상한 기본 512 MiB이며 무제한은 없다.

```sh
python3 scripts/ugrp_session.py run m1-dev -- \
  python3 scripts/write_cap_guard.py --watch /Users/changmin/projects/ugrp/outputs/<run> --max-mib 256 -- <실행 명령>
```

`ugrp_session.py`·`harness/zone_own_team_host.py` 등 봉인된 의존성에 들어 있는 파일은 고치지 않았다(번들 해시·봉인 보존). 그래서 안전망이 별도 스크립트다.

### 5.4 묶기 도구 (`scripts/pack_frames.py`)

```sh
python3 scripts/pack_frames.py <실행 폴더>                       # 계획만 (프레임 수·크기)
python3 scripts/pack_frames.py <실행 폴더> --execute              # mp4 + sha256 목록 쓰고 검증
python3 scripts/pack_frames.py <실행 폴더> --execute --remove-originals   # 검증된 폴더의 JPEG만 삭제
```

- `*.jpg`가 있는 폴더마다 옆에 `<폴더명>.mp4`와 `<폴더명>.sha256.jsonl`을 쓴다. 검증은 목록 행 수 = 파일 수, ffprobe가 읽은 프레임 수 = 파일 수다. 검증을 통과한 폴더만 `--remove-originals`로 지운다.
- 삭제는 raw 삭제이므로 **사용자가 정한 대상에만** 쓴다(AGENTS.md "보존"). 봉인된 과거 코호트에는 쓰지 않는다.

### 5.5 측정 (2026-10-01, 실제 프레임 묶음 1회씩)

| 표본 | 원본 JPEG | `mp4_v1` (mp4 + 목록) | `none_v1` (목록만) |
|---|---|---|---|
| M1 dev 에피소드 `m1-owncam-20260926/dev-a1/m1dev-s91/frames` (1,214장, 자기 카메라 5 Hz) | 18.7 MiB(`du`) / 16.38 MiB(논리) | 2.19 MiB (mp4 1.99 + 목록 0.18) → **88% 감소** | 0.18 MiB → **99% 감소** |
| 3대 dispatch 실행 `plan-guidance-20260925/legacy-1/rgb` (3,406장, 자기·TOP 섞임) | 187.3 MiB(`du`) / 181.30 MiB(논리) | 24.19 MiB (mp4 23.6 + 목록 0.52) → **87% 감소** | 0.52 MiB → **99.7% 감소** |

- 원본은 읽기만 했고 복사본(스크래치)에서 묶었다. 두 표본 모두 `pack_frames.py --execute` 검증이 통과했다(목록 행 수·디코딩 프레임 수 일치). 표의 수치는 `FrameSink`(실제 구현)에 같은 프레임을 넣어 잰 폴더 합계다(`pack_frames.py`의 목록은 필드가 적어 더 작다). 감소율은 `du` 기준이다.
- 이 수치는 프레임 파일만이다. 같은 실행의 결과 JSON·모델 요청 텍스트·영상은 그대로 남는다(옛 5절 기준 dev M1 36 MiB 중 프레임이 약 23–43 MiB).
- 러너 연결 전에는 위 효과가 자동으로 나타나지 않는다. 아래 5.6 참고.

### 5.6 러너 연결 상태

공용 프레임 기록 계층은 main에 없고 러너마다 JPEG을 직접 쓴다. 아래 러너는 봉인된 실행 번들·의존성 해시에 들어 있어, 고치면 새 번들 ID와 재검증이 필요하다. 이 PR은 번들 ID를 쓰지 않았고 러너 동작을 바꾸지 않았다. 각 러너의 주인이 다음 새 번들 등록 때 `FrameSink`를 연결한다.

| 러너 (프레임을 쓰는 곳) | 연결 방법 |
|---|---|
| `harness/zone_own_team_host.py` `_capture_raw` (5 Hz, M2는 `frames_dir` 필수 검사 포함) | `FrameSink.add`로 교체, M2의 "frames_dir 필수" 검사를 "FrameSink 필수"로 바꾼다 |
| `scripts/run_m1_owncam.py` | 위와 같음 |
| `harness/rgb_skill_execution.py` `save_observation`, `harness/task_stage_execution.py`, `harness/rgb_communication_runtime.py` | 모델 요청 이미지도 원본 JPEG 의무가 없다. 요청 텍스트·해시 목록은 유지 |
| `scripts/eval_zone_*`, `probe_*` | 평가 렌더도 기본은 `none_v1`/`mp4_v1`; 평가 표본 이미지가 필요한 분석은 `all_v1`과 상한을 명시 |

그때까지 새 dev·smoke 실행은 5.3의 안전망으로 실행당 쓰기량을 막고, 끝난 실행은 5.4로 묶는다.

## 6. 예산 (제안, 사용자 확정 필요)

- 프로젝트 합계 ≤ 60 GiB: `outputs/` ≤ 40, worktree ≤ 10, 기본 체크아웃 나머지 ≤ 6, 가상환경 ≤ 2, 여유 2.
- 실험 ID당 raw ≤ 2 GiB가 기본이다. 더 필요하면 사전 등록에 예상 크기(에피소드당 × 수)를 적고 사용자 승인을 받는다. 예를 들어 3대 자기 카메라 5 Hz 주 연구는 에피소드당 약 150 MiB라 test 48회에 약 7 GiB다.
- Git 미디어: `experiments/`에 파일당 1 MiB, 실험당 5 MiB. 20 MiB 초과 파일은 기존 hook이 거부한다.
- 세션 시작 하한: 여유 공간 10 GiB(`ugrp_session.py run`).
- 보관 주기: 기록이 병합되고 7일이 지난 dev·진단 raw는 주 1회 보관 후보로 올린다. 실제 이동·삭제는 사용자 결정이다.

## 7. 에이전트 규칙

1. **worktree 생성:** `python3 scripts/agent_worktree.py new <이름> --branch <kiro|claude|codex>/<주제>`를 쓴다.
   - sparse checkout이며 `experiments/`의 zip·gz·영상·이미지·pdf·html·npz를 빼고, 실행에 쓰는 `models.zip` 두 개는 남긴다.
   - 동결 소스는 `--detach --owner <에이전트>`로 만든다.
   - 에이전트당 등록 worktree가 8개 이상이면 거부한다. 넘겨야 하면 `--allow-over-cap --reason "<이유>"`를 쓴다.
   - sparse worktree에서 뺀 종류의 새 파일을 커밋하려면 `git add --sparse <경로>`가 필요하다. 크기 제한을 지킨다.
   - 기존 worktree는 주인이 `python3 scripts/agent_worktree.py sparsify <경로>`로 바꿀 수 있다.
2. **raw 위치:** 실행 raw는 기본 체크아웃의 `outputs/`(절대 경로 `/Users/changmin/projects/ugrp/outputs/...`)에 쓴다. worktree 안의 `outputs/`는 worktree와 함께 사라질 수 있다.
3. **병합 뒤 정리:** `python3 scripts/agent_worktree.py retire <경로>`로 계획을 본 뒤 `--execute`를 붙인다.
   - 무시된 `outputs/<이름>`은 기본 체크아웃의 같은 상대 경로로 옮긴다. 그 경로가 이미 있거나 `outputs/` 밖의 무시 파일(`MUJOCO_LOG.TXT` 등)은 `outputs/retired-worktrees/<주인>-<이름>/`으로 옮긴다(`--archive-layout`이면 전부 이쪽).
   - 옮기기 전후 모든 파일의 개수·바이트·sha256을 비교하고 같을 때만 `git worktree remove`를 실행한다. 목록은 `outputs/retired-worktrees/<주인>-<이름>/MANIFEST.tsv`, 영수증은 같은 폴더의 `RETIRED.json`이다. 불일치면 worktree를 남기고 실패 영수증을 쓴다.
   - 프로세스 cwd·열린 파일·명령줄이 그 경로를 가리키거나 60분 안에 바뀐 파일·git index가 있으면 거부한다(`--idle-minutes`). `sparsify`도 같다.
   - 미병합 작업은 HEAD를 원격 `codex/archive-<이름>-0926` 같은 보관 브랜치에 올리고 `--archive-ref <브랜치>`를 준다. `ls-remote`로 원격 SHA가 HEAD와 같을 때만 진행한다.
   - `git worktree remove`를 직접 쓰지 않는다. `--force`는 쓰지 않는다. `git status --porcelain`만 보고 지우지 않는다(무시 파일이 안 보인다).
   - 다른 에이전트의 worktree는 주인이나 사용자가 정한다.
   - Codex-app worktree(`~/.codex/worktrees/<이름>/ugrp`)도 같은 절차이며, 은퇴 폴더 이름은 `codex-<이름>`이다.
4. **Git 미디어:** `experiments/`에는 기록(JSON·Markdown·작은 그림)만 둔다. 영상·큰 로그는 `outputs/`에 두고 sha256을 기록한다. 원본 JPEG 프레임은 기본으로 저장하지 않는다(5절). 경고는 `scripts/check_media_size.py`(pre-commit·CI)가 낸다.
5. **확인:** `python3 scripts/disk_report.py`(읽기 전용, 약 2–3분)로 사용량·예산·은퇴 후보를 본다.

## 8. 사전 등록 지침: 디스크 부족은 HOST_ERROR

2026-09-26 M1 test에서 s103·s104가 디스크가 가득 차 카메라 프레임을 쓰다 멈췄다(`OSError [Errno 28] No space left on device`). 예외 처리기가 `result.json`을 남겨, 사전 등록 문구대로라면 과제 실패로 집계된다. **M1 사전 등록은 소급해 고치지 않는다.** s103·s104 처리는 사용자·코디네이터 결정으로 남는다. 앞으로의 사전 등록에는 다음을 넣는다.

- 실행 중 `ENOSPC`(errno 28), `EDQUOT`(errno 122) 또는 "No space left on device"로 끝난 에피소드는 과제 결과가 아니라 **HOST_ERROR**다. `result.json`을 썼는지와 무관하다.
- HOST_ERROR는 공간을 확보한 뒤 같은 동결 소스·seed로 1회 재실행한다. 원 시도의 raw·로그는 지우지 않고 보고한다. 재실행도 HOST_ERROR면 결측으로 보고하고, 분모 처리 규칙을 미리 정한다.
- 시작 전 여유 공간 검사와 에피소드당 raw 예상 크기를 적는다. 집계기는 HOST_ERROR를 성공·실패와 다른 열로 센다.

```json
"host_error": {
  "match": ["OSError errno 28 (ENOSPC)", "OSError errno 122 (EDQUOT)", "No space left on device"],
  "applies_even_if_result_json_written": true,
  "action": "rerun once on the same frozen source and seed after freeing space; keep and report the failed attempt",
  "second_host_error": "report as missing; use the pre-registered denominator rule",
  "free_space_floor_gib": 10,
  "expected_raw_mib_per_episode": 150
}
```

## 9. 보관 대상 비교 (Google Drive는 사용하지 않는다)

| 방식 | 비용 | 장점 | 단점 |
|---|---|---|---|
| GitHub Release asset (모델과 같은 방식) | 무료. 릴리스당 asset 1,000개, 파일당 2 GiB 미만, 전체 크기·대역 제한 없음([GitHub 문서](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)) | 원격 보관. 기존 모델 배포 절차(manifest·재다운로드·해시 검증) 재사용 | **저장소가 PUBLIC이라 raw가 공개된다.** 업로드 시간이 걸리고 2 GiB 분할이 필요하다. 올린 뒤 회수를 보장할 수 없다 |
| 외장 디스크 | 1회 구매. 2026년 시세 1 TB 휴대용 SSD 약 $150–200(메모리 가격 상승기), HDD는 TB당 더 쌈. 구매 시점 가격 확인 필요 | 비공개. 빠름(USB 3.2 SSD 약 1 GB/s). 대용량 | 한 벌은 백업이 아니다(두 벌 권장). 수동 관리, 분실·고장 위험 |
| Git LFS | Free/Pro 계정에 저장 10 GiB·월 다운로드 10 GiB 포함, 초과분은 사용량 과금([GitHub 문서](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)) | Git 기록과 연결 | clone·fork·GitHub Actions의 다운로드가 모두 소유자 대역으로 계산된다. 공개 저장소에서 빠르게 소진된다. raw에는 권장하지 않는다 |

- 권장: raw 보관은 외장 디스크 두 벌(비공개)로 한다. GitHub Release는 공개해도 되는 선별 묶음(모델, 대표 영상)에만 쓴다.
- 어느 쪽이든 옮긴 뒤 해시를 대조하고 새 위치를 기록에 적은 다음에만 로컬 삭제를 사용자에게 제안한다.

## 10. 도구

```sh
# 새 sparse worktree (fetch 후 origin/main에서)
python3 scripts/agent_worktree.py new kiro-topic --branch kiro/topic
python3 scripts/agent_worktree.py new zone-x-s1-frozen --detach --owner claude --base <SHA>
# 기존 worktree 줄이기 (주인만)
python3 scripts/agent_worktree.py sparsify /Users/changmin/projects/ugrp-wt/<이름>
# 병합 뒤 정리: 먼저 계획, 그다음 실행
python3 scripts/agent_worktree.py retire /Users/changmin/projects/ugrp-wt/<이름>
python3 scripts/agent_worktree.py retire /Users/changmin/projects/ugrp-wt/<이름> --execute
# 미병합 작업: HEAD를 보관 브랜치에 올린 뒤
python3 scripts/agent_worktree.py retire <경로> --archive-ref codex/archive-<이름>-0926 --execute
# 읽기 전용 보고서
python3 scripts/disk_report.py --json /tmp/disk.json
# 미디어 경고 (pre-commit hook이 자동 실행; 기존 worktree는 한 번 설정)
git config --worktree core.hooksPath .githooks
python3 scripts/check_media_size.py --base origin/main
# 여유 공간 하한 무시(사유를 기록할 것)
python3 scripts/ugrp_session.py run --allow-low-disk <이름> -- <명령>
```

- `new`는 새 worktree에 `core.hooksPath=.githooks`를 worktree 설정으로 넣는다. 공유 설정과 다른 worktree는 바꾸지 않는다.
- `retire`의 영수증은 각 은퇴 폴더의 `RETIRED.json`과 `outputs/retired-worktrees/retirements.jsonl`이다.
- `ugrp_session.py run`의 하한은 `--min-free-gib` 또는 환경 변수 `UGRP_MIN_FREE_GIB`로 바꾼다. GitHub Actions에서는 기본으로 끈다.
