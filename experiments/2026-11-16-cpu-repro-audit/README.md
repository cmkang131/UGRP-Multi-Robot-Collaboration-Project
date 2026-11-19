# 새 체크아웃·CPU 환경 재현 점검 — 2026-11-16

## 결과

**설치용 물리·렌더링 데모는 CPU에서 실행했다. Solo v1 대표 평가와 최신 2대 LLM–MuJoCo 결과는 현재 공개 진입점만으로 재현하지 못했다.** 실패한 명령과 원인을 아래에 구분했다.

- 검사한 커밋: `ca954d9fa64f94303a3f645c265aff85e2af2fce`.
- 검사 중 소스 파일을 수정하지 않았다. 기준 체크아웃의 `git status --porcelain`은 비어 있었고 표준 실행 결과도 `source_dirty: false`를 기록했다. 수정은 별도 `codex/cpu-repro-20261116` worktree에서 했다.
- 출발 문서: 루트 README → `docs/ubuntu_quickstart.md`, `docs/local_simulation.md` → README가 연결하는 Solo 구조·코드·모델 배포 문서.
- [명령·실제 출력 전문](command-log.md)에 시작 시각, 작업 폴더, 명령, 종료 코드, wall 시간, 시간 상한을 남겼다. 패키지 전체 버전은 같은 파일의 `23-pip-freeze`에 있다.
- 이 보고서의 실행은 개발용 설치·재현성 점검이다. 새로운 연구 코호트나 성공률 측정이 아니다.

## 환경과 검사 경계

| 항목 | 실제 확인한 환경 |
|---|---|
| OS | Debian GNU/Linux 13.6, x86_64, glibc 2.41 |
| Python | 3.12.14; 새 `.venv-dev`, `include-system-site-packages = false`; 최초 설치 패키지는 pip 25.0.1뿐 |
| 설치 | pip 26.3으로 갱신; `requirements-sim.txt` + `requirements-test.txt` 그대로 설치; `pip check` 통과 |
| 주요 패키지 | MuJoCo 3.12.0, NumPy 2.5.2, OpenCV headless 5.0.0.93, Pillow 12.3.0, pytest 9.1.1 |
| CPU 확인 | `/dev/nvidia*`, `/dev/dri/renderD*` 없음; `CUDA_VISIBLE_DEVICES=`; 실제 GL renderer는 `llvmpipe (LLVM 19.1.7, 256 bits)` |
| 렌더러 | EGL + `LIBGL_ALWAYS_SOFTWARE=1`; Mesa 25.0.7-2+deb13u1 |
| OS 준비 한계 | `sudo`, Docker, Podman, OSMesa 라이브러리 없음. 문서의 Ubuntu apt 설치를 완료한 환경이 아님 |
| 계정·외부 서비스 | GitHub 공개 clone과 Release 다운로드 사용. 개인 개발자 환경, 모델 키, 실행 중 프록시, 원격 연구 서버를 재사용하지 않음 |

**깨끗한 가상환경과 새 체크아웃에서 수행했지만, 새 Ubuntu 24.04 VM을 만든 검사는 아니다.** 기존 호스트의 Python·시스템 EGL을 사용했다. OSMesa 단계 실패는 이 호스트의 준비 미완료이며, 프로젝트 자체 결함으로 분류하지 않았다. CPU EGL 실행은 README 그대로 실행한 결과와 구분되는 진단이다.

## 단계별 실제 결과

| 단계 | 명령·증거 | 결과와 해석 |
|---|---|---|
| 저장소 접근 | 문서의 `gh repo clone kcm0127-dotcom/ugrp` | 로그인되지 않은 gh에서 exit 4. 문서의 대화형 로그인은 수행하지 않고 공개 HTTPS clone으로 진행 |
| 정규 URL clone | `git clone --depth 1 --branch main --single-branch https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git ugrp-clean` | exit 0, 지정 SHA의 새 소스 확보 |
| 예전 URL 재확인 | `GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/kcm0127-dotcom/ugrp.git HEAD` | exit 0, 동일 SHA. 예전 주소가 깨졌다고 판정하지 않음 |
| Python 환경·설치 | 문서의 venv, pip 갱신, 두 requirements 설치, `pip check` | 모두 exit 0; `No broken requirements found.` |
| README OSMesa 데모 | `06-quickstart-readme` | exit 1, `AttributeError: 'NoneType' object has no attribute 'glGetError'`; 호스트의 libOSMesa 부재 |
| CPU 대체 렌더 진단 | `08-quickstart-egl` | exit 0, `ok=true`, 12프레임, 1.5 SIM초, 이동 0.138548 m |
| 기본 CLI 실행 | `10-cli-headless` | exit 0, `sim_limit`, 약 3 SIM초, 명령 3개, 모델 호출 0, 시작·종료 RGB 저장 |
| GUI 명령에 headless만 추가 | `14-headless-paused` | exit 2, `--paused requires the native viewer`. `--paused`를 빼는 별도 서버 명령 필요 |
| 관련 짧은 검사 | `21-quickstart-tests` | 29 passed in 0.35s. 전체 회귀나 연구 성능 검증 아님 |
| Solo 실행기 사용법 | `04-solo-help` | exit 1, argparse 전에 `solo_appearance_v1.py` 누락 |
| Solo Release 다운로드 | `11-solo-release-download` | 코드 ZIP·모델 ZIP·체크섬 파일 모두 HTTP 200 |
| Release 무결성 | `15-release-checksums` | 두 ZIP의 배포 SHA-256 일치·CRC 통과. 코드 ZIP에도 같은 helper가 없음 |
| Gemini 프록시 안내 | `19-proxy-guide-path` | 연결된 `docs/gemini_subscription_proxy.md`가 파일·Git 목록 모두에 없음 |
| Gemini 검증 계약 | `12-verifier-contract` | 실행 모델/물리값과 검증기 기대값의 불일치 확인. 모델 호출 없음 |
| Gemini 실패 종료 전파 | `16-cohort-exit-diagnostic` | 합성 `infrastructure_blocked` 상태를 출력하고 exit 0. 실제 연구 실행과 구분한 오프라인 진단 |

### 전체 회귀 검사와 Git 이력

README의 `scripts/run_ci_tests.py`는 693개 테스트 모듈을 선택했다. 최초 실행은 240초 기록기 상한에서 종료했다(exit 124). 약 10%까지 진행하면서 실패·오류 표시가 있었지만 전체 집계는 완료하지 못했다. 이때 렌더러를 지정하지 않았고 얕은 단일 브랜치 clone이었으므로, 그 표시만으로 저장소 결함을 단정하지 않았다.

`git fetch --unshallow origin main` 후 CPU EGL을 지정하고 `PYTEST_ADDOPTS=-x`로 첫 실패를 확인했다. 결과는 **1 failed, 288 passed, 17 skipped**였고 실패 위치는 다음과 같다.

```text
tests/test_beamact2.py::test_close_never_executes_before_both_READY_GO_ACK_and_delay
git show 26f84d0f0ada1c33473c83cca2d3415ce51bd247:harness/grasp_act_start_sync.py
fatal: path 'harness/grasp_act_start_sync.py' does not exist in '26f84d0f0ada1c33473c83cca2d3415ce51bd247'
```

main 이력만 받은 상태에서는 위의 과거 경로를 읽지 못했다. 다음으로 일반 clone과 같은 범위의 브랜치 ref를 받았고, 이후 동일 검사가 통과했다.

```bash
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
git cat-file -t 26f84d0f0ada1c33473c83cca2d3415ce51bd247
.venv-dev/bin/python -m pytest -q -x \
  tests/test_beamact2.py::test_close_never_executes_before_both_READY_GO_ACK_and_delay
```

그 후 object type은 `commit`, 같은 검사는 **1 passed in 0.18s**였다. 최초 clone을 줄인 감사 환경 때문에 생긴 실패이므로 결함 이슈에서 제외했다. 문서 PR의 일반 `git clone`은 이력·브랜치를 축소하지 않는다. 전체 693개 모듈을 끝까지 다시 실행하지 않았으므로 전체 suite 통과라고 보고하지 않는다.

## README 밖에서 필요했던 수동 작업과 의존성

| 항목 | 수행·확인한 내용 | 분류 |
|---|---|---|
| OS 차이 기록 | 제공된 Debian 호스트를 사용하고 Ubuntu 24.04 검사와 구분 | 감사 환경의 제한 |
| 공개 clone | gh 로그인 대신 현재 정규 URL로 익명 HTTPS clone | 가능한 절차 단순화. 기존 URL redirect는 정상 |
| Git 이력 복원 | 얕은 clone을 해제한 뒤 모든 브랜치 ref를 fetch | 감사자가 처음 clone을 축소해서 필요해진 작업. 일부 테스트의 과거 Git 객체 의존성 확인 |
| 렌더러 선택 | OSMesa 부재 확인 후 EGL과 software flag 사용; GL 문자열로 llvmpipe 확인 | 이 머신에서만 검증한 대안. 공식 Ubuntu 경로는 OSMesa 유지 |
| GPU·패키지 분리 | GPU 장치 없음 확인, `CUDA_VISIBLE_DEVICES=`, `PYTHONNOUSERSITE=1`, system-site 패키지 비공유 | 검사 조건 |
| headless 명령 | 첫 GUI 명령의 `--paused`를 제거하고 `--headless --capture` 사용 | 문서에 별도 복사 가능한 명령 추가 |
| 출력 폴더 | 실패 결과를 보존하고 `quickstart-egl-01`, `cpu-repro-drive-01` 등 새 이름 사용 | 기존 문서에도 안내된 조건 |
| 세션 OS 의존성 | `/bin/ps`와 저장소 FS 여유 10 GiB 필요. 이 호스트는 해당 조건 충족 | 코드로 확인한 미기재 선행 조건. 누락으로 실제 실패했다는 주장은 아님 |
| 영상 도구 | 무료 GIF는 ffmpeg 불필요. 실제 모델 영상은 ffmpeg/libx264 필요 | 기존 문서의 조건. 이번 모델 영상 생성은 미수행 |
| 모델 artifact | Solo Release의 코드·모델·체크섬 직접 다운로드 및 검사 | 다운로드는 성공. 추론 로딩과 평가 재현은 미완료 |
| Solo 보조 코드 | `solo_appearance_v1.py` 누락. 일부 import는 별도 루트 모듈에도 의존 | 실제 최초 실행 차단 및 정적 의존성 |
| Solo 입력 | 대표 결과의 plan/protocol/고정 장면 소스/옵션 연결 필요 | 문서·코드로 확인한 미완료 조건. 임의 생성하지 않음 |
| Solo 호스트 검사 | `require_gcp(training=False)`가 개발 프로젝트·인스턴스·머신을 요구 | 정적으로 확인. 검사 우회·호스트 이전·새 VM 생성 안 함 |
| 추론 패키지 | Solo는 PyTorch·LeRobot 0.6.2를 별도로 요구; 기본 sim/test 설치와 다름 | 이번 새 venv에는 추론 패키지를 추가하지 않음. 모델 loading 성공 주장 없음 |
| Gemini 서비스 | 본인 프록시·계정·지원 모델이 필요; 안내 파일은 누락 | 선택 실험을 실행하지 못한 준비 조건 |
| 원본 자료 | 과거 raw와 최신 2대 실행 자료는 새 clone에 모두 포함된 것이 아님 | 다른 코호트의 자료나 옛 실행으로 대신하지 않음 |

## 재현 차단 이슈

### #679 — Solo 실행 묶음과 대표 결과 입력

[이슈 #679](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/679): `--help`부터 없는 파일을 import한다. 실제 오류, Release ZIP 목록·해시, 이후 필요한 입력·추론 환경·호스트 조건과 완료 기준을 기록했다. 최신 2대 실행 코드는 README 자체가 배포 전이라고 밝히므로, 기본 데모로 그 성공을 확인했다고 판정하지 않았다.

### #682 — Gemini 준비 문서와 검증 조건

[이슈 #682](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/682): 프록시 설치 안내 파일이 없고, 실행기는 `gemini-3.8-flash-high`/`noslip_iterations=0`, 검증기는 `gemini-3.8-flash`/`3`을 요구한다. seed와 토큰 예산만 바꿔서는 일치하지 않는다. 실제 모델 호출 없이 생성 명령과 검사 계약을 비교했다.

### #685 — 인프라 차단의 CLI 종료 코드

[이슈 #685](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/685): `main()`의 실패 반환값을 진입점이 버린다. `run_cohort`만 합성 차단 상태로 대체하고 외부 subprocess를 막은 진단에서 exit 0을 확인했다. 실제로 모델 서비스가 장애를 냈다는 기록은 아니다.

OSMesa 미설치, 첫 Git HTTP 503, 얕은 clone의 과거 객체 누락은 위 이슈들과 구분하여 기록했으며 프로젝트 성능 결함으로 집계하지 않았다.

## 문서 PR에서 수정한 것

실행 결과의 기준은 위의 `ca954d9fa64f94303a3f645c265aff85e2af2fce`로 유지했다. PR 작성 중 병합된 문서 변경 #706(`835380e961b8e8898d65e9a19e76663728dde850`)을 보존하여 그 위에 수정안을 올렸다. #706은 문서만 바꿨으며 이 보고서의 실행 결과를 새 실행으로 소급하지 않는다.

- 공개 clone과 PR 인증 절차를 분리하고 현재 정규 URL을 사용한다.
- 세션이 필요로 하는 `procps`, 10 GiB 여유 공간, 과거 Git 객체 의존성을 밝힌다.
- GUI와 headless 첫 실행을 분리하고, OSMesa 설정을 지닌 터미널에서 GUI를 실행하는 방법을 적는다.
- 짧은 설치 관련 검사와 전체 회귀 suite를 구분한다.
- 빠진 프록시 문서와 신규 실행에 맞지 않는 verifier를 현재 완료된 절차로 제시하지 않는다.
- README에서 설치 데모, 공개 Solo 묶음, 배포 전 최신 실행의 범위를 구분한다.
- 최신 Solo 가중치의 실제 Release 링크를 연결하고, 다운로드 확인과 모델 로딩·평가 재현을 구분한다.
- 연구 코드·의존성 버전·성공 판정·호스트 제한은 변경하지 않았다.

## 문서 수정 검증

수정 문서와 감사 요약의 Bash/sh 코드 블록 29개를 `bash -n`으로 검사했고 모두 통과했다. 수정한 8개 Markdown 파일의 상대 파일 링크 누락은 0개였으며, `git diff --check`도 통과했다. 원본 명령 transcript는 실행 결과를 보존하는 자료이므로 코드 블록 구문 검사 대상에서 제외했다. 이 검사는 Ubuntu OS 설치·LLM·ACT 평가의 실행 검증을 대신하지 않는다.

## 실제 출력

### 무료 CPU 데모

```json
{
  "ok": true,
  "mode": "offline_deterministic_physics_demo",
  "seed": 41,
  "simulated_time_s": 1.5,
  "robot_id": "r1",
  "initial_xy_m": [
    0.263447,
    1.752991
  ],
  "final_xy_m": [
    0.1969,
    1.63147
  ],
  "robot_displacement_m": 0.138548,
  "frame_count": 12,
  "outputs": {
    "animation": "quickstart.gif",
    "summary": "summary.json"
  },
  "scope": "Physics motion and camera rendering only; no LLM, network, hardware, autonomous transport, or task-success validation."
}
```

GIF의 전체 프레임 수(12개)와 640×268 크기를 읽었고, 첫·중간·마지막 프레임을 직접 확인했다. 장면과 R1 카메라가 표시되고 이동에 따라 시야가 변했다. 이는 고정 바퀴 명령의 설치 점검이다.

### 표준 CLI headless 실행

```json
{
  "source_sha": "ca954d9fa64f94303a3f645c265aff85e2af2fce",
  "source_dirty": false,
  "python": "3.12.14",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "mujoco": "3.12.0",
  "headless": true,
  "capture": true,
  "seed": 41,
  "policy": "raw_commands",
  "scope": "simulation_runtime_check",
  "protocol_complete": true,
  "stop_reason": "sim_limit",
  "runtime_events": [],
  "model_calls": 0,
  "sim_s": 2.999999999999858,
  "commands": 3,
  "wall_s": 4.223423119000017
}
```

`protocol_complete=true`는 이 예제 명령 스케줄 완료를 뜻한다. 자율 운반·LLM 협업·물리 임무 성공을 뜻하지 않는다.

## 원본 파일 식별

아래 raw GIF·시뮬레이터 출력은 실행 호스트에 보존했다. 본 PR에는 명령·출력·환경·해시를 텍스트로 넣었으며 raw 영상·207 MB 가중치를 Git 이력에 중복 추가하지 않았다. 로컬 보관을 원격 백업이라고 표현하지 않는다. 두 ZIP은 기존 공개 Release에서 다시 받을 수 있다.

| 파일 | 바이트 | SHA-256 |
|---|---:|---|
| `<checkout>/outputs/quickstart-egl-01/summary.json` | 500 | `3ca9d548de9dd25cf95869d6f4636a549c6caaaba8f155d56b40d24c4b3c894b` |
| `<checkout>/outputs/quickstart-egl-01/quickstart.gif` | 649,564 | `388cf4968c558e3c1a0a75902d78e90249ac274671612ff98882f9afc63362e1` |
| `<checkout>/outputs/cpu-repro-drive-01/result.json` | 3,275 | `3b6076bb7c21da9c9c7748617bfdff50d3fdb55c7c9fa0abd46eba6f99d17bec` |
| `<audit-dir>/release-solo-v1/solo-pipeline-code.zip` | 69,389 | `79cb2365880cbca73a80c53f39fbcbc9df570c920f2df79695e0cfb1d5406575` |
| `<audit-dir>/release-solo-v1/solo-act-model-gseg-step4000.zip` | 207,382,468 | `74b1213b07fcc3ec5cc286be3c44a310ebe2fea2d80ae2057c0b290977a4fea7` |
| `<audit-dir>/release-solo-v1/SHA256SUMS.txt` | 271 | `960d92fd919932c0a1196881a50f669758db2d2823dda972c0d216ac88824ce7` |

## 방법 참고

- [GitHub 공식 clone 안내](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository): 공개 저장소의 정규 HTTPS URL로 clone한다.
- [Python 3.12 명령행 문서](https://docs.python.org/3.12/using/cmdline.html): 저장소 루트의 `python -m scripts...` 실행 형태를 유지한다.
- 프로젝트의 `scripts/sim_quickstart.py`, `scripts/open_simulation.command`, `scripts/ugrp_session.py`, `scripts/run_ci_tests.py`를 실제 진입점으로 사용했다. 대체 구현이나 임의 성공 판정은 만들지 않았다.
