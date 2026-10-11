# Azure 시뮬레이션 실행 (2026-10-11)

사용자 승인: “다 쓰면 자동으로 끄게 해주면 돼. 이어서 ㄱㄱ”. 실행 호스트는 `ugrp-sim-azure`(Korea Central), 보관은 기존 Oracle ARM이다. Oracle x86은 진행 중 실행과 증거 보존을 확인한 뒤 정지한다. 옛 Azure 상시 서비스의 부활이 아니라 작업 단위 CPU 실행 이관이다.

실행 자원을 만들거나 켜는 구독은 **Azure subscription 1 / 88b7ee7f-f2f3-4a0d-a0ce-cf7306943676**뿐이다. `UGRP GPU PAYG / c02f839a-2a6b-49d8-9c9a-f3d9f09aa5ea`에는 실행 자원을 만들지 않는다. 두 구독은 동일 결제 프로필의 크레딧을 사용하므로 안전 자동화의 비용 조회·VM 할당 해제 권한만 양쪽에 부여한다. 모델 키·Azure access token·Automation webhook URL은 저장소와 실행 증거에 넣지 않는다.

## 비용과 종료

- Microsoft for Startups 잔여 크레딧은 사용자 확인 기준 $166, 만료는 **2026-11-19 00:00 KST = 2026-11-18 15:00 UTC**다. spending limit Off이므로 이 장치가 Azure의 결제 상한을 만드는 것은 아니다.
- `scripts/azure_safety_setup.py`: 구독 88b7ee7f의 Action Group → managed identity Automation runbook. `Stop-UgrpVMs`는 두 구독 VM을 발견하고 ARM **deallocate**를 호출한다. 시스템 종료(poweroff)와 다르다.
- 구독·공유 결제 프로필에 2026-10-01~2027-01-01 분기 예산을 둔다. 월이 바뀌어도 10~11월 누적을 초기화하지 않는다. 결제 통화는 KRW다. 실제 `Cost / CostUSD` 비율 1364.75보다 낮은 **1360 KRW/USD**를 적용해 217,600원 예산, 68,000/136,000/204,000원 이메일을 설정한다($50/$100/$150 근사값). 구독 예산의 $150 및 $160 근사 임계값은 Action Group을 호출한다. 환율이 변하면 원화 알림은 정확한 USD 임계값과 달라질 수 있다.
- 매시간 `CostUSD`를 두 구독 합산한다(2026-10-01부터, 이관 이전 비용도 포함). **$150 조기 정지**로 집계 지연에 대한 여유를 두며, 비용 조회 실패도 두 구독 VM을 할당 해제한다. $160 예산 알림은 추가 백업이다. 비용 데이터는 보통 8~24시간 지연되고 예산은 24시간 간격 평가이므로 $160의 정확한 실시간 강제 상한은 검증·보장하지 않는다.
- 동일 runbook의 `Force` 모드를 만료 순간 OneTime 일정에 연결한다. 매일 00:00 KST VM auto-shutdown도 백업으로 설정한다. 미래 일정의 생성·runbook 연결 확인과 해당 날짜 실제 발동은 별개다.
- VM system identity에는 **자기 VM**의 read/instanceView/deallocate만 부여한다. Automation에는 두 구독의 같은 최소 compute 역할과 Cost Management Reader만 부여한다. VM Contributor보다 좁으며 VM 생성·시작·크기 변경·삭제 권한이 없다.
- 기존 VM의 `ugrp-azure-idle-guard.timer`는 15분·lease 미지원 가드였다. 새 가드 활성화 뒤 이 중복 timer만 비활성화하며 정의·기록은 보존한다. 이관 스모크 중 기존 가드가 보관 대기 VM을 실제로 할당 해제한 반례를 기록했다.
- 기존 `ugrp-sim-worker.service`의 무한 GPU worker 재시작 supervisor도 비활성화한다. 파일·과거 자료는 보존하며 새 CPU 실행은 유한 `sim_cli` 작업으로만 시작한다.
- `scripts/azure_idle_guard.py`는 1분 timer로 시뮬레이션/rsync/아카이브와 실행기 lease를 확인한다. 유휴 20분 또는 부팅 후 8시간이면 IMDS의 메모리 내 identity token으로 CLI `az vm deallocate`와 동일한 ARM 작업을 호출한다. 토큰 파일을 만들지 않는다. 8시간 상한은 실행 중에도 적용한다. 부팅마다 유휴 상태를 새로 초기화한다.
- 할당 해제 후에도 OS 디스크·공용 IP·기타 서비스 비용은 남는다. 이 자동화는 VM compute를 정지하며 결제 프로필 전체 서비스의 사용을 중단하는 장치는 아니다.

```sh
python3 scripts/azctl.py status
python3 scripts/azctl.py start
python3 scripts/azctl.py stop
python3 scripts/azctl.py resize --size Standard_D16as_v5
```

`start`는 만료·예산/일정 활성화·USD 합산 비용을 먼저 검사하며 실패하면 켜지 않는다. `stop`은 다른 미완료 실행과 lease가 있으면 정지를 미룬다. `resize`는 할당 해제 상태에서만 허용한다. 모든 CLI 자원 명령은 구독을 명시한다. `azure_safety_setup.py` 재실행은 webhook을 교체하므로 VM이 모두 할당 해제된 유지보수 시점에만 한다.

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

아카이브는 PR #435의 `scripts/ugrp_auto_archive.sh`를 그대로 설치한다. 완료·평가 출력·20분 실제 정적 상태를 기다리고, >64 KiB JSON/JSONL zstd 압축 후 해제 SHA-256, ARM 25 GiB 여유, rsync checksum 및 전체 파일 SHA-256 일치를 확인한 다음 ARM 경로로 공개한다. Azure의 검증된 원본은 ARM symlink로 바뀐다. 신규 archive SSH identity는 해당 VM에서만 생성하며 ARM `ugrparch`의 SFTP 전용 접근에만 쓴다. 클라우드/API/모델 키와 다르며 개인키는 로그·Git·Mac 회수에 포함하지 않는다. 실패하면 Azure 영속 원본을 보존한다. Mac에는 이미지·대형 배열·영상 없이 가벼운 기록만 회수한다.

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
