# Azure 시뮬레이션 실행 (2026-10-11)

사용자 승인: “다 쓰면 자동으로 끄게 해주면 돼. 이어서 ㄱㄱ”. 실행 호스트는 `ugrp-sim-azure`(Korea Central), 보관은 기존 Oracle ARM이다. Oracle x86은 진행 중 실행과 증거 보존을 확인한 뒤 정지한다. 옛 Azure 상시 서비스의 부활이 아니라 작업 단위 CPU 실행 이관이다.

실행 자원을 만들거나 켜는 구독은 **Azure subscription 1 / 88b7ee7f-f2f3-4a0d-a0ce-cf7306943676**뿐이다. `UGRP GPU PAYG / c02f839a-2a6b-49d8-9c9a-f3d9f09aa5ea`에는 실행 자원을 만들지 않는다. 두 구독은 동일 결제 프로필의 크레딧을 사용하므로 안전 자동화의 비용 조회·VM 할당 해제 권한만 양쪽에 부여한다. 모델 키·Azure access token·Automation webhook URL은 저장소와 실행 증거에 넣지 않는다.

## 비용과 종료

- Microsoft for Startups 잔여 크레딧은 사용자 확인 기준 $166, 만료는 **2026-11-19 00:00 KST = 2026-11-18 15:00 UTC**다. spending limit Off이므로 이 장치가 Azure의 결제 상한을 만드는 것은 아니다.
- `scripts/azure_safety_setup.py`: 구독 88b7ee7f의 Action Group → managed identity Automation runbook. `Stop-UgrpVMs`는 두 구독 VM을 발견하고 비동기 Managed Run Command로 우아한 정지를 먼저 요청한 뒤 ARM **deallocate**를 호출한다. 전체 유예는 최대 10분이며 보관 실패·VM agent/API 오류도 비용 상한의 할당 해제를 취소하지 않는다. 시스템 종료(poweroff)와 다르다.
- 구독·공유 결제 프로필에 2026-10-01~2027-01-01 분기 예산을 둔다. 월이 바뀌어도 10~11월 누적을 초기화하지 않는다. 결제 통화는 KRW다. 실제 `Cost / CostUSD` 비율 1364.75보다 낮은 **1360 KRW/USD**를 적용해 217,600원 예산, 68,000/136,000/204,000원 이메일을 설정한다($50/$100/$150 근사값). 구독 예산의 $150 및 $160 근사 임계값은 Action Group을 호출한다. 환율이 변하면 원화 알림은 정확한 USD 임계값과 달라질 수 있다.
- 매시간 `CostUSD`를 두 구독 합산한다(2026-10-01부터, 이관 이전 비용도 포함). **$150 조기 정지**로 집계 지연에 대한 여유를 두며, 비용 조회 실패도 두 구독 VM을 할당 해제한다. $160 예산 알림은 추가 백업이다. 비용 데이터는 보통 8~24시간 지연되고 예산은 24시간 간격 평가이므로 $160의 정확한 실시간 강제 상한은 검증·보장하지 않는다.
- 동일 runbook의 `Force` 모드를 만료 순간 OneTime 일정에 연결한다. `Daily` 모드의 매일 00:00 KST Automation 일정은 백업이다. 활성 lease·미보관 원본·게스트 확인 실패가 있으면 건너뛰고 기록한다. 기존 무조건 DevTest auto-shutdown은 새 일일 일정 설치 때 비활성화한다. 미래 일정의 생성·runbook 연결 확인과 해당 날짜 실제 발동은 별개다.
- VM system identity에는 **자기 VM**의 read/instanceView/deallocate와 Managed Run Command read/write만 부여한다. Automation의 기존 두 구독 compute 역할·Cost Management Reader는 유지하고, 새 `virtualMachines/runCommands/read`·`write`는 Automation과 VM identity 모두 **구독 88b7ee7f의 자기 VM 범위에만** 할당한다. custom role의 배정 가능 범위는 해당 resource group이며 실제 권한 범위는 VM이다. PAYG에 새 Run Command 권한은 부여하지 않는다. VM Contributor보다 좁으며 VM 생성·시작·크기 변경·삭제 권한이 없다.
- 기존 VM의 `ugrp-azure-idle-guard.timer`는 15분·lease 미지원 가드였다. 새 가드 활성화 뒤 이 중복 timer만 비활성화하며 정의·기록은 보존한다. 이관 스모크 중 기존 가드가 보관 대기 VM을 실제로 할당 해제한 반례를 기록했다.
- 기존 `ugrp-sim-worker.service`의 무한 GPU worker 재시작 supervisor도 비활성화한다. 파일·과거 자료는 보존하며 새 CPU 실행은 유한 `sim_cli` 작업으로만 시작한다.
- `scripts/azure_idle_guard.py`는 1분 timer로 시뮬레이션/rsync/아카이브와 실행기 lease를 확인한다. 유휴 20분은 lease·보관 작업·EXIT만 있는 미보관 원본이 있으면 정지하지 않는다. 부팅 후 8시간 상한은 실행 중에도 적용한다. `azure_shutdown.py`가 해당 실행의 SIGINT → 현재 원본 flush/기록 → 최대 10분 ARM 보관 시도(`rsync -ac`, `rsync -anc`, 전체 SHA-256) → 성공/실패 영속 기록을 수행하고, 그 뒤 IMDS의 메모리 내 identity token으로 ARM 할당 해제를 호출한다. 전체 게스트 절차도 600초 외부 deadline으로 제한하고, 실패 시에도 할당 해제한다. 토큰 파일을 만들지 않는다. 부팅마다 유휴 상태를 새로 초기화한다.
- 할당 해제 후에도 OS 디스크·공용 IP·기타 서비스 비용은 남는다. 이 자동화는 VM compute를 정지하며 결제 프로필 전체 서비스의 사용을 중단하는 장치는 아니다.

```sh
python3 scripts/azctl.py status
python3 scripts/azctl.py start
python3 scripts/azctl.py stop
python3 scripts/azctl.py resize --size Standard_D16as_v5
```

`start`는 만료·예산/일정 활성화·USD 합산 비용을 먼저 검사하며 실패하면 켜지 않는다. `start`는 SSH 준비 뒤 미보관 원본을 자동 재보관하며, boot recovery service도 같은 작업을 수행한다. 보관 실패는 종료 코드74로 반환하므로 새 실행을 허용하지 않는다. `stop`은 미보관 원본(EXIT 유무와 관계없음)·활성 lease가 있으면 정지를 미룬다. `resize`는 할당 해제 상태에서만 허용한다. 모든 CLI 자원 명령은 구독을 명시한다. `azure_safety_setup.py`의 전체 재실행은 webhook을 교체하므로 VM이 모두 할당 해제된 유지보수 시점에만 한다. `--lifecycle-only`는 기존 webhook·예산·비용/만료 일정을 유지하고 자기 VM Run Command 권한·runbook 내용·lease-aware 자정 일정만 갱신하며 VM을 켜거나 끄지 않는다.

## 환경·증거·모델 터널

Ubuntu 24.04 x86_64, Python 3.12, `requirements-sim-server.txt`, OSMesa 소프트웨어 렌더를 사용한다. 서버 requirements는 기본 sim requirements와 S3 제어기 추가 의존성 SciPy 1.17.1(기존 Mac/test pin)을 포함한다. 기본 VM은 **Standard_D16as_v5: 16 vCPU / 64 GiB RAM**, Linux 정가 **$0.848/시간**(2026-10-11 Retail Prices API 조회, 할인·세금·디스크·IP 제외). 기존 64 GiB Standard SSD OS 디스크를 우선 사용하고 배치별 저장 예산을 확인한다. CPU·RAM·디스크 예산이 허용하는 범위에서 동시 실행한다.

`~/ugrp-sim/src/<SHA>`는 커밋 전체 트리의 shallow Git 소스, `~/ugrp-sim/ugrp/.venv-sim`은 공유 환경, `~/ugrp-sim/runs/<이름>`은 영속 OS 디스크 원본이다. tmpfs에 원본을 쓰지 않는다. 파일명은 고유해야 하며 미커밋 소스로 실행하지 않는다. `RUN_META.json`, 소스 SHA·명령·부하·EXIT·SHA256SUMS와 실패를 보존한다.

기존 `ORACLE_HOST` 기본값 `oracle`을 유지한 정식 진입점:

```sh
bash scripts/oracle_run.sh --host azure --per-run-mb 128 --class milestone WORKTREE RUN -- \
  .venv-sim/bin/python -m scripts.sim_cli workflow run azure-s3-environment-smoke -- \
  --expected-source-sha FULL_SHA --output outputs/RUN/smoke
bash scripts/oracle_run.sh --host azure fetch-lite RUN
```

Azure 모드는 시작 → 실행 완료 대기 → fetch-lite → 검증된 ARM 아카이브 → 할당 해제다. `--detach`는 명시적으로 이 대기/회수/종료 래퍼를 끄며, 비용·VM 내부 가드는 유지한다. SSH alias `azure`는 기존 NSG가 허용한 Oracle ARM(`oracle-codex`)을 ProxyJump로 사용한다. Mac 공개키를 VM에 추가하며 기존 authorized_keys는 보존한다.

아카이브는 PR #435의 `scripts/ugrp_auto_archive.sh`를 그대로 설치한다. 완료·평가 출력·20분 실제 정적 상태를 기다리고, >64 KiB JSON/JSONL zstd 압축 후 해제 SHA-256, ARM 25 GiB 여유, rsync checksum 및 전체 파일 SHA-256 일치를 확인한 다음 ARM 경로로 공개한다. Azure의 검증된 원본은 ARM symlink로 바뀐다. 신규 archive SSH identity는 해당 VM에서만 생성하며 ARM `ugrparch`의 SFTP 전용 접근에만 쓴다. 클라우드/API/모델 키와 다르며 개인키는 로그·Git·Mac 회수에 포함하지 않는다. 실패하면 Azure 영속 원본과 lease를 보존하고 재시도한다. 비용 상한/부팅 복구 보관은 20분 정적 상태·평가 출력 조건을 기다리지 않고, 작성 프로세스 종료를 확인한 부분 원본도 HOST_ERROR로 보관한다. 별도 `shutdown-<이름>` 경로를 checksum 검증 뒤 공개하며 Azure 원본은 삭제하지 않는다. 실패한 `.incoming-shutdown-*`도 다음 시도에 재사용한다. Mac에는 이미지·대형 배열·영상 없이 가벼운 기록만 회수한다.

정지·보관 결과는 `~/ugrp-sim/lifecycle/events/`, 파일별 SHA-256·보관 확인은 `lifecycle/archives/`에 기록한다. 실행기와 `azctl`은 가벼운 기록만 Mac 기본 체크아웃 `outputs/azure-lifecycle/`로 checksum 확인 후 회수한다. Mac 연결이 끊기면 pending 기록을 남기고 다음 시작/회수 때 영속 디스크의 결과를 다시 회수한다. 회수되지 않은 기록을 완료로 보고하지 않는다.

### 선택적 ARM 네이티브 전송

`UGRP_ARCHIVE_NATIVE=on_v1`은 `archive-one`과 자동 보관을
`scripts/azure_archive_native.py`의 tar/zstd SSH 스트림으로 전환한다. 기본은
`off`이고 기존 sshfs/rsync 경로를 유지한다. 이 모드는 파일별 SSH 왕복 없이
ARM 로컬 디스크에 추출하고 **전체 파일명·크기·SHA-256**을 비교한다.
부분 복사본은 고유 `.incoming-native-*`에 보존하며, 일치한 디렉터리만
`native-<run>`으로 원자 공개한다. ARM의 25 GiB reserve와 64 MiB 여유를
확인하고 네이티브 수신을 직렬화한다. 링크·특수 파일이 있는 소스는 거부한다.

Azure 원본은 압축·삭제·이동하거나 symlink로 바꾸지 않는다. 기존
`.incoming-*`와 `shutdown-*`도 보존한다. 전송 전후 원본 해시·상태와 writer
부재를 확인한 뒤 기존 `lifecycle/archives/<run>.json`에 `verified`,
`source_state`, 전체 inventory 및 ARM 검증 proof를 기록한다. `recover`가
그 마커를 그대로 검증하며 실패는 기존 종료 코드74로 유지한다. 자동 보관은
이 모드에서 기존 원본을 재압축해 검증 마커를 무효화하지 않는다.

VM의 `/etc/ugrp/archive-native.env`를 자동 보관·guard·boot recovery 서비스가
선택적으로 읽는다. `UGRP_ARCHIVE_NATIVE_HOST=ubuntu@161.33.46.134`,
`UGRP_ARCHIVE_NATIVE_IDENTITY=/home/ugrp/.ssh/id_ed25519_arm_archive`를
명시한다. 수동 `recover`/`archive-one`에도 이 환경을 전달한다. ARM에는
이 Python 모듈만 root 소유 `/usr/local/lib/ugrp-archive-native.py`로 설치한다.
기존 archive 공개키에 대해 Ubuntu의 authorized_keys에 `restrict`,
Azure IP의 `from=`, 고정 `command`를 붙인 **별도 줄**을 추가한다.
고정 명령은 `/usr/bin/python3 /usr/local/lib/ugrp-archive-native.py receive
--archive-root /home/ubuntu/ugrp-archive/runs`이며, 수신기는
`SSH_ORIGINAL_COMMAND=ugrp-archive-native-v1`만 허용한다. 기존 SFTP 전용
사용자·키와 SSH 설정은 변경하지 않는다. 개인키는 VM 밖으로 복사하지 않는다.
stock-bot·crontab·다른 실행 프로세스를 변경하지 않는다.

2026-10-11 이번 VM의 명시적 활성화·전송·admission 검증은
[네이티브 전송 기록](../experiments/2026-10-11-archive-native-transport/summary.json)에 남긴다.
설치 helper 교체 시 rollback 사본을 보존하고, 실행 중인 서비스에는 새 코드를
소급 적용하지 않는다. 새 installer는 이 환경 파일을 만들거나 토글을 켜지 않는다.

방법 근거: [OpenSSH 명령/stdin 전송](https://man.openbsd.org/ssh),
[Zstd CLI stdin/stdout](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md),
[Python tar stream/data extraction filter](https://docs.python.org/3.12/library/tarfile.html#extraction-filters).
기존 egojump 전송의 ARM 네이티브 해시 검증·원본 보존 원칙을 따르되,
이 구현은 로컬 tar 파일과 sshfs blob 복사를 생략한다.

### #438 검토 수정의 적용 범위

2026-10-11 앞선 P1 수정은 **기존 runbook 내용 갱신만** 허용된 범위에서 수행했고, 당시 두 VM은 `deallocated`, RBAC·일정·게스트는 미적용이었다. 이후 사용자가 #438 마무리에서 이 세 항목 배포를 승인했다. 소스 `9589255c`에서 자기 VM만의 Run Command 권한, lease-aware 자정 일정과 기존 DevTest 강제 종료 비활성화, runbook Published/바이트 일치를 재조회했다. VM identity의 실제 무해한 명령도 PUT201·GET200·exit0을 확인했다. 첫 다음 자정은 2026-10-12 00:00 KST다.

게스트 가드 본체·감독 실행기·부팅 복구 서비스는 이미 설치된 새 버전과 일치해 재설치를 건너뛰었다. 반환값이 바뀐 `azure_shutdown.py`만 이전 파일을 보존하고 원자 교체했으며, 서비스 시작/재시작/정지와 복구 실행을 하지 않았다. 교체 전후 활성 lease가 같았다. VM은 다른 작업이 켜 둔 실행 상태를 유지했고 이 배포에서 시작·종료하거나 PAYG 자원을 변경하지 않았다. 실제 비용 상한 종료·ARM 보관·미래 자정 발동은 새 소스에서 실행하지 않았다. [마무리 기록](../experiments/2026-10-11-azure-sim-migration/finalize-438.json).

같은 브랜치의 동시 작업에서 `1bfa2bde`가 추가되어, 반복 start 복구는 PID·부팅·프로세스 시작 시각으로 확인한 실행 중 형제 writer를 보관/신호 없이 보존한다. 완료/중단된 원본의 복구 실패는 계속 코드74로 차단하며 일반 종료·비용 상한의 경계는 유지한다. 이 후보를 관련 시험45개로 다시 확인했고 설치된 helper 해시도 일치했다. 내장 helper가 포함된 runbook도 갱신/재조회했다. publish 뒤 연결 ID가 바뀌므로 일정 목록에서 실제 ID를 찾고 개별 GET으로 Daily·Cost·Force 모드를 확인했다(목록 응답의 parameters는 null).

모델은 Mac relay의 `127.0.0.1:18392`로 연결하는 유한 역방향 SSH `127.0.0.1:18391 → Mac:18392`를 사용한다. S4 브랜치의 `scripts/s4_reverse_tunnel.py`에 `--host azure`를 추가할 수 있는 일반 실행기 `scripts/remote_reverse_tunnel.py`는 기본 재연결 OFF, 명시적 `--reconnect`, 최대 4시간 종료 시각을 유지한다. S4의 request idempotency/재시도 토글은 그 브랜치에서 계속 적용한다. 단순 HTTP 터널 확인은 모델 실제 응답 검증이 아니다.

S3 설치 스모크는 기존 표준 Scene·접촉·카메라·0.5초 물리 진행과 3대 자기 RGB 6장을 확인한다. 제어기·LLM 호출·운반 성공 평가를 포함하지 않는다. 공통 관리 catalog에 `azure-s3-environment-smoke`로 등록하며 과거 성공을 새 호스트에 승계하지 않는다.

## 참고 자료

- [Azure 공식 Budget → Action Group → Automation 패턴](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/cost-management-budget-scenario)
- [예산 평가·집계 지연과 범위](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)
- [Automation managed identity](https://learn.microsoft.com/en-us/azure/automation/learn/powershell-runbook-managed-identity)
- [Action Group runbook receiver API](https://learn.microsoft.com/en-us/rest/api/monitor/action-groups/create-or-update?view=rest-monitor-2021-09-01)
- [Action Group 테스트 API](https://learn.microsoft.com/en-us/rest/api/monitor/action-groups/create-notifications-at-action-group-resource-level?view=rest-monitor-2021-09-01)
- [Automation 일정 API](https://learn.microsoft.com/en-us/rest/api/automation/schedule/create-or-update?view=rest-automation-2024-10-23)
- [Linux VM identity 토큰과 ARM 호출](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/how-to-use-vm-token)
- [Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Linux OS 디스크 확장](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/expand-disks)
- [OpenSSH 역방향 전달](https://man.openbsd.org/ssh)
- [Microsoft 공개 코드의 Cost API 429 처리 규칙](https://github.com/microsoft/azure-skills/blob/main/skills/azure-cost/cost-forecast/guardrails.md): 고정 ClientType을 쓰고 모든 retry-after 헤더 중 최댓값을 기다린다. 재시도 후 실패도 시작을 거부한다.

- [Azure Managed Run Command 비동기 실행·timeout·instanceView](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/run-command-managed)
- [Azure 역할 정의·배정 가능 범위와 실제 리소스 할당 범위](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions#assignablescopes)
- [Python sys.exit의 성공·실패 반환값](https://docs.python.org/3/library/sys.html#sys.exit)
- [Rsync 공식 구현/매뉴얼의 checksum·부분 재전송](https://github.com/RsyncProject/rsync/blob/master/rsync.1.md)
