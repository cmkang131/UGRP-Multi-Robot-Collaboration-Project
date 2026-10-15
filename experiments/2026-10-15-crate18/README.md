# crate18 — 최소 유효 펄스 정착, 기본 off

**최종 NOT_READY/BLOCKED. 실행 소스9cb9686a: 파지·실제 들기5/6(full2/3, no_clearance3/3),
전체 내려놓기 완료0/6. full79314의 READY 유지 실패가 남아3라운드에서 종료했다.**
입력 감사6/6 inv0/held0/top0, 전체 manifest6·압축복원24·직접 자기 RGB72장을 확인했다.
관문·학습 실행0이며 crate16/17 또는 앞 라운드와 합산하지 않는다. [summary.json](summary.json).

기준 crate17 `4eb7d472`, PR #500. `--crate18 crate18_v1`은 `crate17_v1`(full)과
`crate17_no_clearance_v1`(no_clearance)에만 조합한다. 끄면 crate17 경로다.
교사 정렬만 변경하고 학생·물리·카메라·질량·접촉·배정은 유지한다.

`sim/settle_pulse.py`와 공통 시험은 release20 **097e53da**에서 바이트 그대로 가져왔다.
[upstream.json](upstream.json)에 전체 출처 SHA와 파일 SHA-256을 기록했다.
공통 시험은 이 브랜치에 없는 release 어댑터를 import하므로 원본 시험/fixture를 이 실험의
`release20-tests/`에 보존하고, 정확한 참조 소스 의존성으로 격리 실행한다.
첫 혼합 의존성 실행은 74 PASS/3 FAIL(ReleaseTeacher API 차이); 격리 뒤 27 PASS,
crate 연결 시험 50 PASS다. Mac 물리/렌더 함수는 금지하는 실행기에서만 검증했다.

## 보정과 기하

[calibration.json](calibration.json): GCP n4-highcpu-64의 0.25kg 장면 저장 원장96파일에서
같은 시각 명령→다음0.1초 평가 자세를 맞췄다. 순수 축·동일 폭·±.35만 분리했다.
최소 폭 선택은 표본≥20 및 이동>0.5mm/회전>.005rad 비율≥75%인 최소 관측 폭이다.
정지 마찰 전용 bench 보장이 아니며 잔여 관성/접촉/단계 차이를 포함한다.
무하중 전후25ms/δ1.321mm, 좌우25ms/δ.824mm, 회전18ms/δ.012432rad.
각 최소 폭의 관측 반응 비율은 전후79%, 좌우100%, 회전94%다.
초기1/2라운드의 효과→폭은 중앙값 보간/외삽이었다. 최종3라운드는 아래 p95 모형을 쓴다.
정답은 이 오프라인 보정과 평가에서만 사용한다. 실행기는 현재 가시 오차와 고정 모형만 받는다.
운반 중 표본0으로 별도 보정은 `unavailable`; 새 정착기는 파지 전 align/ready에만 적용한다.

초기1/2라운드 허용=max(기존,.6δ)는 전후 .7926mm / 좌우2mm / yaw .0074592rad였다.
실제 발행 뒤 연속 반전3회는 공통 모듈 그대로 2δ 안에서만 수용한다.
초기 모형은 ±2δ×3축27개 모서리를 원래 하강/들기 기하로 검사해27/27 통과했다.
각 실제 현재 자세도 `grasp_valid`를 통과해야 하며 양자화 수용만으로 READY를 만들지 않는다.
거부·대체된 펄스는 발행 수에 넣지 않고 정지한다. 영상 누락은 latch를 초기화한다.
0.3초 새 관측 안정 확인·입력 감사·weld off·정답 파지 위치 숨김을 유지한다.

## GCP 직접 확인 계획과 기록

push 전 커밋 소스로 알려진77990·79314·79317×2후보, 동시최대6, 최대3라운드.
기존 gcp1/n4-highcpu-64, 프로젝트 `ugrp-act-train-1014`만 사용한다.
단계 상한 grasp60+release27.5+평가2.5=최대90 SIM초. 모형/LLM 호출0.
라운드당 raw예산6×128MiB=768MiB, 최대2304MiB. 원본은 GCP 영속 디스크,
선택 텍스트·검토 프레임·해시는 이 worktree `outputs/crate18/`만 회수한다.
기존 `scripts/remote_run.py --host gcp1 --class dev --pr 500`을 import해 호출하며
PRIMARY만 이 worktree로 지정한다. 공유 admission.lock 아래 실제 worker+예약≤40을 검사한다.
8h STOP·유휴20분·budget-stop은 유지한다. 비용 발동 시 제출하지 않는다.
알려진 제어 결함 확인 시 자기 진행·대기 실행을 정지하고 원인/원본을 기록한다.
같은 결함이3라운드째면 중단한다. 후보·라운드·crate16/17 결과는 합산하지 않는다.

재현:
```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-15-crate18/test.py
python3 experiments/2026-10-15-crate18/dev.py --round 1
```
실행/결과/대기열의 최종 상태는 아래 후속 기록에 명시한다. 현재 관문·학습은 승인하지 않는다.

## 참고 자료

- [release20 원본 소스 097e53da](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/097e53da/sim/settle_pulse.py): 파일과 시험 원문 확인. .6·3회·25%는 이 구현의 공학적 선택이며 안정성 정리가 아니다.
- [release20.md 참고 자료](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/097e53da/experiments/2026-10-14-e2e18-grasp-rootcause/release20.md): 양자화·hysteresis·주기해 출처와 적용 범위를 확인했다.
- [Tao & Kokotović, 1994, IEEE TAC, DOI 10.1109/9.273339](https://doi.org/10.1109/9.273339): 사용자가 지정한 데드존 보상 참고. 이번 접근에서 DOI 원문 접속 실패로 본문 미확인; 적응 제어기의 보장을 구현했다고 주장하지 않는다.

OFF 회귀: crate17 두 후보×알려진3시드의 저장 명령 **4,050/4,050 일치**, 입력 감사0/0.
숫자는 [off-replay.json](off-replay.json); 새 물리 결과와 합산하지 않는다.

제출 사전 점검 a478e933: 기존 frames()의 평가용 top 캡처를 발견해 소스 전송 중 중단.
원격 실행 디렉터리/시뮬레이션0, 예약6개를 해제했다. crate18 on에서 top 캡처를 생략하도록
수정한 후 첫 실제 라운드를 시작한다. OFF의 top 평가 기록 경로는 재생용으로 유지한다.

## 1라운드 e3a61c40 — 원인 확인 뒤 정지

6회 제출: 완료 실패1·감독 중단5, 성공0/6(중단은 실패 완주로 세지 않음).
두 로봇 READY 도달4/6, 집기 허가2/6, 들기 허가1/6. no_clearance77990은
양쪽 명령 완료·실제 hold를 기록했으나 release 완료 전 감독 중단으로 성공 미확정이다.
full77990 r1의 t25.2/31.7에서 기존 alternating_error_sign_4가 새 공통 정착기와
중복 작동했다. 옛 카운터는 다른 축 동작 사이의 선택 부호도 누적하므로 crate18에서
해제하고 실제 발행 뒤 반전만 PulseSettler가 센다. 공통 모듈은 수정하지 않는다.
실패 원인 확인 후 소유 PID5개에 SUPERVISOR_STOP+SIGINT, 모든 원본/압축복원 해시와
실행당6시각×자기 RGB2장(총72장)을 직접 확인했다. 각자 청록/파랑 끝을 유지했다.
자기 프로세스·예약·임대0 확인 후 같은6회를 2라운드로 재검증한다.
[round1.json](round1.json)에 원본/로컬/해시/펄스분포/반전/정렬·파지·들기·감사를 보존한다.

보정 추가 조사: 기존 들기 성공23회에서 GT 물리 hold와 자기 holding_belief가 함께인
전후 이동128표본을 맞췄다([held-calibration.json](held-calibration.json)). 40ms가8건,
중앙10.634mm이지만 이미 움직이는 구간이므로 breakaway 최소를 식별할 수 없다.
운반 중 회전·좌우 표본은0이며 미확인으로 유지한다. 새 정착기의 적용 범위는 계속 무하중 정렬이다.
2라운드 전 관련 시험27+51=78 PASS.

## 2라운드 37835a11 — 파지·실제 들기4/6, 전체 완료0/6

모두 자연 종료했다. 77990/79317의 두 후보는 양쪽 정렬·집기·들기 완료와 GT hold를
확인했고 own RGB 승인 뒤 release에 들어갔으나27.5초 release 상한으로 완료0이다.
79314 두 후보는60초 grasp 상한까지 다축 보정을 반복했다. 4회 반전 옛 가드의
중복 중단은 사라졌으나, 작은 중앙값 quantum의 좁은 latch가 다른 축의 보정으로
풀리면서 .3초 정착이 유지되지 않았다. 예: r2 forward min25ms 반응은 같은 저장군에서
중앙1.321mm, p95 3.071mm다. 전자의 허용.7926mm는 큰 반응의 절반보다 작다.
6원본의 전체 manifest·압축복원·72자기 RGB를 확인했다. 다른 끝 유지, 감사0/0/top0.
[round2.json](round2.json.zst)에 실패·펄스분포·반전·원본/해시·종료를 남겼다.

## 3라운드 최종 모형

최소 폭25/25/18ms를 유지하고, 같은96파일에서 **경험적 p95 반응**을 고정 quantum으로 쓴다.
전후 δ3.071185mm, 좌우1.041256mm, yaw .021610194rad. 허용은 각각
1.842711mm / 2mm / .0129661164rad(약.743도)다. 폭 역모형의 모든 knot도 같은 p95로
바꿔 한 번만 양자화한다. 최소 효과만 넓히고 중앙값 역모형으로 다시 펄스를 키우는
이중 양자화는 하지 않는다. p95는 저장군의 경험적 설계값이며 새 조건95% 보장은 아니다.
공통 모듈·기존 물리·발행 뒤3회 반전·최종 현재 자세의 하강/들기 검사는 유지한다.
새 inner27/27 기하 통과, 반전2δ 범위는9/27만 통과하므로 나머지18/27은
READY/집기 직전의 exact geometry가 거부한다([geometry-p95.json](geometry-p95.json)).
마지막 같은6회 이후 같은 결함이 남으면 추가 실행하지 않는다.

## 최종 3라운드 9cb9686a — 종료·대기열 BLOCKED

6회 모두 자연 종료, 양쪽 READY 기록6/6·파지 허가5/6·들기 허가5/6·평가 hold5/6.
full은2/3, no_clearance는3/3 파지·실제 들기다. 들기5회 모두 자기 RGB 승인 뒤 release에
진입했지만27.5초 release 진단 상한으로 `release_timeout`, 전체 완료0/6이다. 내려놓기 성공으로
해석하지 않는다. first30은 grasp/release 원장 시각과 자기 RGB mtime으로 맞춰6/6 확인,
중앙 **3.526228 wall/SIM**, 초기화 제외·파일 기록 시각/보간 오차를 포함한다. 경고만이며6.0 미만이다.

| 후보·시드 | 정렬 펄스 r1/r2 | 실제 hold | 전체 완료 |
|---|---:|---:|---:|
| full77990 |20/36|예|아니오, release_timeout|
| no_clearance77990 |21/28|예|아니오, release_timeout|
| full79314 |26/91|아니오|아니오, grasp60초 초과|
| no_clearance79314 |22/26|예|아니오, release_timeout|
| full79317 |19/18|예|아니오, release_timeout|
| no_clearance79317 |19/18|예|아니오, release_timeout|

원본 펄스 폭은18–100ms(전후/좌우 최소25ms), 분포·반전·소스/압축/복원 SHA는
[round3.json](round3.json.zst)과 로컬 상세 원장에 있다. 반전 수는 같은 align/ready 구간 안에서만 센다.

남은 반례([remaining-counterexample.json](remaining-counterexample.json)): full79314 r2
world_t56.5–61.5에25ms 전후 펄스12회, 펄스 뒤0.1초 실제 전진 중앙1.627mm이나
5초 순이동은1.640mm이고 자기 가시 x 오차2.364→2.337mm로 거의 유지됐다.
57.4/58.7/59.6/60.1초에 READY 진입, 바로 다음0.1초마다 취소됐다.
실제 단기 이동이 있으므로 이를 단순한 정지 마찰로 확정하지 않는다. 정착 후 유지·GO/ACK
대기 중 재취소의 결함이 남았다는 범위까지만 확인했다. 세 번째에도 남아 더 돌리거나
교사 코드를 추가 수정하지 않았다. 원인 확인 시 같은 소스 진행/대기 실행은 이미0이었다.

18회 원본 전체 manifest, 회수 텍스트·압축복원 해시, 라운드별72장(총216장) 자기 RGB를
직접 확인했다. 모든 검토에서 각자 청록/파랑 손잡이를 유지했다. 자기 임대·예약·시뮬레이션
프로세스0. VM 정상 정지는 타 임대/프로세스 때문에 exit75로 보류됐으며 타 작업은 건드리지 않았다.
8h STOP·유휴20분·budget-stop 유지. 비용 로그 costAmount0은 지연 집계값이며 실제 비용0 보장은 아니다.

대기열은 `outputs/e2e18-admin/vm3-queue/20261015-crate18-diag-<record-sha8>.json`에
후보별 재현5+신규10, 총30행으로 저장한다. 알려진77990·79314·79317을 먼저 배치하고
max_parallel16·전체40·승인/준비/제출/실행 플래그 모두false다. 자체 파지·들기5/6이므로
**BLOCKED**, 관문·학습·후속 물리 실행을 승인하지 않는다. 큐의 기록 SHA와 실제 실행 SHA를
구분하고, runtime 디렉터리/두 계획이9cb9686a와 동일한지 diff로 확인한다.

읽기 전용 결과 재집계(새 물리 실행 없음):
```sh
python3 experiments/2026-10-15-crate18/analyze.py outputs/crate18/round3-9cb9686a
```
발행 직전 controller/runtime 변경은 없고 관련 시험은 **79 PASS**, OFF4,050/4,050이다.
운반 중 회전·좌우 최소 펄스 보정과 전후 breakaway 최소는 여전히 미확인이다.
