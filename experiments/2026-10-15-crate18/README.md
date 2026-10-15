# crate18 — 최소 유효 펄스 정착, 기본 off

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
효과→폭은 저장 중앙값 구간의 선형 보간/외삽 모형이고 100ms로 제한한다.
정답은 이 오프라인 보정과 평가에서만 사용한다. 실행기는 현재 가시 오차와 고정 모형만 받는다.
운반 중 표본0으로 별도 보정은 `unavailable`; 새 정착기는 파지 전 align/ready에만 적용한다.

허용=max(기존,.6δ)는 전후 .7926mm / 좌우2mm / yaw .0074592rad다.
실제 발행 뒤 연속 반전3회는 공통 모듈 그대로 2δ 안에서만 수용한다.
±2δ×3축27개 모서리를 원래 하강/들기 기하로 검사해27/27 통과했다.
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
