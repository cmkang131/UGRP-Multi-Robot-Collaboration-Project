# s3fix11 — Oracle x86 단계 묶음 (2026-10-10)

## 실행 전 등록

사용자 요청으로 새 물리·렌더·저장 제어 재생은 `host=oracle-x86`에서만 실행한다.
AMD EPYC x86_64, 64 logical CPU, 62GiB, Ubuntu24.04, MuJoCo3.12.0/OSMesa.
Mac은 편집·관련 pytest1–3파일·기록 변환만. ARM 신규 실행0, Mac 잠금 대기0.
서버 다른 작업과 합쳐 동시20개 이하, nice0, 각≤60SIM초/dev_light.
동일 비교는 이 호스트 안에서만 하며 ARM/Mac 시간·바이트 동등성을 주장하지 않는다.

새 bundle `zone-s3-x86-stage-probe-v156`, workflow7.49.0. main과 열린10PR 원격의
최대v155/7.48.0 확인 후 예약했다. v155 ARM 실행기·원본은 변경하지 않는다.

우선 기준12개: pair(r1/r2 정렬→hover→하강→닫기)6개 + cyan(r3 정렬→상승→운반)6개.
각 조건 i=0..5는 seed14201+i와 다음 자기 차체 기준 시작 오프셋(dx,dy,yaw)을 고정한다.
`(0,0,0),(.012,0,0),(-.012,0,0),(0,.012,0),(0,-.012,.04),(0,0,-.04)` (m,rad).
pair 두 로봇에 각자의 차체 기준으로, cyan은 r3에만 적용한다. 기존 scene-setup의
eval-only 장면 구성기에만 반영하고 제어기는 매번 새 자기RGB 전역PF로 시작한다.
이것은 저장 장면의 합성 주변 조건이며 정확 체크포인트 재개·독립 확증·E2E가 아니다.
시드를 골라 성공으로 바꾸지 않고 여섯 조건을 전부 보고한다.

v3 마운트는 host 렌더 바인딩, alignment entry는 발행한 inspect 유지 옵션on.
공통 heading 기본on, 집기/놓기/문 최종0.10m 옆걸음 허용, 공동 빔운반 예외 유지.
weld/topRGB/GT제어/시작dock prior 없음. 기존 3mm/0.035rad 판정 문턱은 변경하지 않는다.
PF `sensor_mixture_v1`은 미검증·기본off를 유지하며 입자 수를 늘리지 않는다.

## 판정과 다음 수정의 선택 규칙 (결과 열람 전)

raw 상태/명령/자기RGB/평가 전용 접촉으로 로봇별 hover·하강·닫기·접촉상승·운반,
오차/검출/회전반전, would_stop, 실제정지, wall/SIM을 판정한다. HOST_ERROR/미회수는 별도.
pair baseline의 알려진 회전진동은 시야 검출과 실제 이동을 분리해 확인한다.
후보는 PBVS의 완전 강체변환(집기점 lever arm 포함)과 측정된 합법 단일축 pulse만 사용한다.
새 pulse는 ≥0.10초·실물 최소35출력 계약을 유지하고 물리 보정 결과 없이 이득을 추정하지 않는다.
채택 조건: 동일6조건에서 정렬/닫기 도달 증가, 기존 성공의 실제 물리 실패 증가 없음,
원래 문턱 유지·GT입력0. 후보가 실패하면 같은 원인 반복 대신 기록하고 full smoke는 보류한다.
1시간 진전이 없으면 중단·보고한다. 후속 보정/후보 조건은 실행 전에 이 문서에 추가한다.

## 참고 자료

[Chaumette·Hutchinson 2006, PBVS/interaction matrix](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf):
목표 feature의 변화와 카메라 이동을 전체 좌표변환으로 연결한다. 집기점 오차를 차체 원점의
목표 경로 방향으로 취급하면 회전의 lever arm 항을 잃는다. 우리 단일축/유한 pulse 제약은
이 변환을 각 측정 primitive에 적용하고 자기RGB로 다시 관측하는 방식으로 유지한다.
[MuJoCo rendering](https://mujoco.readthedocs.io/en/stable/python.html#rendering): OSMesa 경로 사용.

## 결과

미실행. 실행 소스를 커밋·push한 뒤 묶음을 보내고 완료/실패 모두 추가한다.

## 보정 묶음 사전 추가 (기준 probe 결과 열람 전)

v157/7.50.0은 학생 없는 고정 명령 보정이다. 기준12개에 이어 같은x86에서6개까지 병렬,
총18개 이하. 각 조건은18SIM초, 두 로봇을 빈 동쪽 방(2.4,-1),(3.4,-1)에 놓고
inspect 자세·무하중에서 forward/left/turn × ±35출력 × .10/.12/.14초를 각2회 측정한다.
자세 yaw는 조건0..5에[-.12,0,.12,-.12,0,.12]rad. 10ms 평가 전용 샘플,
pulse후 .5초까지 완전 응답을 저장한다. 고정 시퀀스는 GT·측정 결과에 반응하지 않는다.
새 포트 옵션 `measured_min100_v1`은 35출력의 합법 .10/.12/.14초 옆걸음만 추가하며
기본off·이전 실행 포트 그대로다. 제어의 마지막10cm 제한·단일축·실물최소출력은 유지한다.

조건0–2를 보정,3–5를 유보로 고정한다. 각 profile 평균 응답과 잔차 분산을 사용하고
원래 모델의 보수적 분산 하한을 낮추지 않는다. 유보 최대 XY오차≤3mm/yaw오차≤.035rad,
실제 이동 방향 일치와 비정상 접촉0을 모두 만족한 profile만 제안기에 허용한다.
통과하면 측정 profile18개를 사용하는 full-pose PBVS finite-action MPC를 pair 후보로 시험한다.
탐색 horizon6/beam128, 기존3mm/.035rad 정규화 잔여오차 최소·동률 짧은 경로 선택을
사전에 고정한다. 첫 pulse 뒤 충분히 정지하고 새 자기RGB로 재계산한다.
조건6개를 모두 같은 초기 장면·seed로 반복하고, r3 기존 제어는 바꾸지 않는다.
이는 고정 보정 데이터의 사용이며 실행 GT 보정이 아니다. 조건별 원본·측정·선택 결과를 남긴다.

## 09:16UTC 사용자 묶음 규칙 적용

이 절이 앞의 동시18/20개 계획보다 우선한다. S3 동시 최대10개. 코드·관련 시험을
먼저 모두 마치고, 묶음 이름·명령·시드를 아래 목록대로 보낸다. 묶음 중 계획 변경 없음.
기존 규칙에서 이미 보낸 기준12개는 동결 소스7a4bda7a를 유지한다. 마지막 cyan c4/c5
자체 프로세스만09:16:43UTC SIGSTOP으로 대기시켰고 종료 슬롯이 생기면 동일 PID를
SIGCONT한다. 원본 파괴/새 seed/새 시도 아님. 두 시행의 wall에는 대기가 포함되어
속도 비교에서 제외하며 scheduling.jsonl에 기록한다. 다른 작업의 프로세스는 건드리지 않는다.

후속 실행 명령은 아래 표의 모듈/조건/이름을 사용한 다음 공통 명령이다. `$SHA`는
묶음 시작 전 커밋·push한 동일 HEAD이며 실행 도중 바뀌면 전송을 거부한다.
`$MODEL`/`$MODEL_SHA`는 전체 보정 묶음 판정이 끝난 뒤 봉인한 단일 모델이다.
필요한 ≤10SIM 경로 스모크는 현재 계획0회(실제 motor port stub 회귀 사용).

```sh
ORACLE_HOST=oracle-x86 "$S/oracle_run.sh" "$WT" "$NAME" -- \
  .venv-sim/bin/python -m "$MODULE" --expected-source-sha "$SHA" \
  --output "outputs/$NAME/raw" --condition "$C" --execute
# 후보는 위 명령에 --model "$MODEL" --model-sha256 "$MODEL_SHA" 추가
```

| 이름 | 모듈 | C | seed |
|---|---|---:|---:|
|s3fix11-measure-c0-r1|scripts.run_s3_x86_pulse_measure|0|14201|
|s3fix11-measure-c1-r1|scripts.run_s3_x86_pulse_measure|1|14202|
|s3fix11-measure-c2-r1|scripts.run_s3_x86_pulse_measure|2|14203|
|s3fix11-measure-c3-r1|scripts.run_s3_x86_pulse_measure|3|14204|
|s3fix11-measure-c4-r1|scripts.run_s3_x86_pulse_measure|4|14205|
|s3fix11-measure-c5-r1|scripts.run_s3_x86_pulse_measure|5|14206|
|s3fix11-candidate-c0-r1|scripts.run_s3_x86_trim_probe|0|14201|
|s3fix11-candidate-c1-r1|scripts.run_s3_x86_trim_probe|1|14202|
|s3fix11-candidate-c2-r1|scripts.run_s3_x86_trim_probe|2|14203|
|s3fix11-candidate-c3-r1|scripts.run_s3_x86_trim_probe|3|14204|
|s3fix11-candidate-c4-r1|scripts.run_s3_x86_trim_probe|4|14205|
|s3fix11-candidate-c5-r1|scripts.run_s3_x86_trim_probe|5|14206|

측정6개는 기준 묶음 전체가 끝나고 동시에 보낸다. 전체6개 raw를 한 번에 fit/holdout
판정하고, qualified일 때에만 후보6개를 동시에 보낸다. 보정 전 후보 실행은 금지한다.
후보/보정 코드 모두 실행 전에 시험하며 결과 뒤 이득/문턱/탐색폭/조건을 바꾸지 않는다.
후보 결과도6개가 모두 끝난 뒤 한꺼번에 raw로 판정한다. 실패면 한 묶음으로 분류한다.

## 기준 실행 전송 기록 (사후 이름 기록)

초기 기준12개는 7a4bda7ac71bc7b59d7d9a9101d9d3c619498df1에서 전송됐다.
이 이름 표는 전송 뒤 기록한 것이며, 새 사용자 규칙 아래 사전 등록으로 소급하지 않는다.
각 명령은 `python -m scripts.run_s3_x86_probe --expected-source-sha 7a4bda7ac71bc7b59d7d9a9101d9d3c619498df1
--output outputs/<이름>/raw --case <case> --condition <C> --execute`이다.

| 이름 | case | C | seed |
|---|---|---:|---:|
|s3fix11-base-pair-c0-7a4bda7a|pair|0|14201|
|s3fix11-base-pair-c1-7a4bda7a|pair|1|14202|
|s3fix11-base-pair-c2-7a4bda7a|pair|2|14203|
|s3fix11-base-pair-c3-7a4bda7a|pair|3|14204|
|s3fix11-base-pair-c4-7a4bda7a|pair|4|14205|
|s3fix11-base-pair-c5-7a4bda7a|pair|5|14206|
|s3fix11-base-cyan-c0-7a4bda7a|cyan|0|14201|
|s3fix11-base-cyan-c1-7a4bda7a|cyan|1|14202|
|s3fix11-base-cyan-c2-7a4bda7a|cyan|2|14203|
|s3fix11-base-cyan-c3-7a4bda7a|cyan|3|14204|
|s3fix11-base-cyan-c4-7a4bda7a|cyan|4|14205|
|s3fix11-base-cyan-c5-7a4bda7a|cyan|5|14206|

09:21:03UTC 완료 슬롯 확인 후 보류2개를 같은PID로 재개했다. 대기260초씩이며
해당 wall은 대기 포함·속도 비교 제외다. 기준 전체 종료 후 post-run 평가를 최대10 worker로
한꺼번에 처리하고, 원본 SHA/프레임별 오차/4배속 영상을 회수한다.
