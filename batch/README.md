# 묶음 실행기 (작업 VM 여러 대)

표준 라이브러리만 쓴다. 실제 ssh·VM·LLM 호출은 `--go` 와 채워진 매니페스트가 있어야만 일어난다. 시험(`test_batch.py`)은 전부 가짜 실행기(`fake_launch.py`)로 돈다.

## 파일
- `launch_team_run_v3.sh`: run 하나를 띄운다. 계획기(`team/brain_server.py`)를 이 호스트에서 켜고, 작업 VM 의 실행 스크립트를 ssh 로 시작하고, 포트를 전달(`-R`)한다. 끝나면 종료 코드를 `$EVIDENCE_DIR/<이름>.exit` 에 남긴다. 종료 코드: 99 VM 접속 불가(시작 안 함), 98 이름 중복, 97 계획기 즉시 종료, 96 빈 포트 없음, 143 TERM.
- `dispatch.py`: `run` / `status` / `stop`. 매니페스트를 읽어 VM 별 슬롯 수만큼 동시에 돌리고, 죽었다 다시 `run` 하면 이어서 간다.
- `make_manifest.py`: 매니페스트 생성. `--preset confirm2|core|optional|all`(`--outdir`, `--baseline-first`)은 `confirm2.csv`(18줄), `core.csv`(348줄), `optional.csv`(242줄)를 만든다. 고정값은 **이전 동결의 것**이다: 코드 sha `dbb692c`, VM 스크립트 `run_team_v32.sh`, 시드 90721, `--cap-s 900`(`FROZEN_SHA`, `FROZEN_VMRUN`, `SEED`). 값이 `PLACEHOLDER`·`TODO` 인 칸이 있으면 `--go` 가 거절한다. 최종 동결 매니페스트(코드 6cbd3db, `run_team_v36.sh`, 기준선 이름 `BASE2-*`)는 이 출력에서 sha·스크립트 이름·기준선 이름을 고쳐 만들었고 이 저장소에는 없다. 쓰려면 두 상수를 동결 값으로 맞춘다.
- `check_manifests.py`: 만든 매니페스트를 장면 파일·위 상수와 대조한다(줄 수, 장면 id, 로봇 수, 정답 계획, run_id 중복, sha·스크립트·시드·`--cap-s 900`).
- `collect.py`: 끝난 run 을 VM 에서 rsync 로 모아 `results/` 에 정리한다(분석은 `analysis/`). `rerun_halted.py`: 계획기가 멈춘 칸을 `-rr1` 로 다시 돌릴 매니페스트를 만든다.

## 환경 변수
| 이름 | 뜻 |
|---|---|
| `OUTROOT` (또는 `--outroot`) | 작업 VM 의 결과 폴더(절대 경로). 필수 |
| `VM_WORKDIR` | 작업 VM 에서 실행 스크립트가 있는 폴더. 실제 실행에 필수 |
| `VM1_IP_FILE`, `VM2_IP_FILE` | VM 별 주소가 들어 있는 파일. 매번 다시 읽는다(VM 을 껐다 켜면 주소가 바뀔 수 있다). 없으면 그 VM 은 접속 불가로 센다 |
| `VM_USER`, `SSH_KEY` | 로그인 이름, 키 파일. 없으면 ssh 기본값 |
| `VM_SCENE_DIR` | 작업 VM 에서 장면 파일(`scenes/` 와 같은 것)이 있는 폴더. `make_manifest.py` 가 읽는다 |
| `BRAIN_DIR` | `brain_server.py` 가 있는 폴더. 기본 `team/` |
| `EVIDENCE_DIR`, `ALERTS_LOG` | 계획기 기록 폴더(기본 `batch/evidence/physical`), 경보 로그(기본 `outputs/batch-alerts.log`) |
| `OPENROUTER_API_KEY_FILE`, `UGRP_SPEND_GUARD_FILE` | 계획기가 쓴다. [팀 실행](../team/README.md) 참고 |

작업 VM 쪽 실행 스크립트(`VMRUN`, 매니페스트의 `vmrun` 열)는 이 저장소에 없다. 인자 형식은 `./<VMRUN> <sha> <seed> <OUTROOT> <이름> [--brain-url <주소>] <vm_args>` 이고, `<OUTROOT>/<이름>/team.json`, `out-<로봇>/summary.json`, `<OUTROOT>/exit-<이름>.json`(`"exit_code"`)을 남겨야 스케줄러가 끝난 run 으로 센다.

## 사용
```
python3 -B batch/make_manifest.py --out manifest.csv --shuffle-seed <시드>          # 예시. 동결 때 내용을 채운다
python3 -B batch/dispatch.py run --manifest manifest.csv --outroot <VM 결과 폴더>     # --go 없으면 계획만 출력
nohup python3 -B batch/dispatch.py run --manifest manifest.csv --outroot <VM 결과 폴더> --slots 1=5,2=2 --go > dispatch.log 2>&1 &
python3 -B batch/dispatch.py status        # 대기/실행/검증대기/완료/실패, 그룹별, VM별, 실패 이유
python3 -B batch/dispatch.py stop [--runs] # 디스패처만(실행 중 run 은 계속, 다음에 이어받음) / --runs 면 실행 중 run 도 TERM
python3 -B batch/collect.py --dir <디스패치 폴더> --results <결과 폴더> [--groups mainA] [--full]
cd batch && python3 -B -m unittest -v     # 시험 20개
```

## 동작 규칙과 위험
- 재시도 1회(`--max-retries`): 종료 코드≠0(`stop --runs` 의 143 포함), 결과 불완전은 `-retry1` 로 한 번 더, 그래도 실패면 기록만. 시작도 못 한 것(코드 99)은 재시도를 쓰지 않는다.
- 다시 실행할 때 `--outroot`·`EVIDENCE_DIR` 이 `state.json` 과 다르면 거부(코드 2; 아니면 끝난 일을 다시 돌림). 새 묶음은 새 `--dir` 로.
- VM 을 못 읽으면 끝난 run 을 다시 돌리지 않는다("검증대기"). 연속 8번 실패하면 새 실행을 멈춘다(코드 4, `--abort-after`). 코드 0 전부 완료, 1 실패 있음, 2 이미 실행 중, 3 모든 VM 막힘, 130 중지.
- 포트: run 마다 10칸 블록(`--port-base`~`--port-max`), 런처는 블록 안에서만 올려 다른 run 을 밟지 않는다. pid 는 `pids/<이름>.pid` 파일로만 관리하고 `/proc/<pid>/cmdline` 로 이름을 확인한 뒤에만 신호를 보낸다.
- `run_team_carry.py` 는 `--brain-url` 이 있으면 `--fixed` 를 읽지 않고 LLM 계획기를 쓴다. 그래서 VM 인자에 `--fixed` 가 있는 기준선 run 은 런처가 계획기를 띄우지 않고 `--brain-url` 도 주지 않는다(`NO_BRAIN=1`).
- 토큰 한도·예산 가드는 `team/brain/llm.py` 가 맡는다. 이 도구는 호출 수를 세지 않는다.
- 확인 안 됨: 실제 ssh/rsync-over-ssh, 실제 `brain_server.py` 와의 연결, VM 쪽 실행 스크립트의 인자·종료 코드 형식(위의 가정), ssh 가 끊기면 VM 쪽 실행도 죽는지(런처는 `.launch-pgid` 로 원격 프로세스 그룹을 종료한다).
