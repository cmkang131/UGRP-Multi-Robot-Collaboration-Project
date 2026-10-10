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

## 현재 결과

기준12개 완료·회수. 아래 최종 판정 표가 현재 상태이며 앞부분의 실행 전 문구는 당시 사전 등록이다.
보정/후보는 아래 동결 계획을 따르고, 실행/회수/판정을 각각 구분한다.

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

## 기준 전체 raw 판정과 후속 최종 동결 (보정0회 시점)

기준12개 전체 평가 완료: pair는 r1/r2 모두6조건 hover0. 각144/144회 검출했고
회전 반전117–141회였다. cyan c0/c1/c2는 양손가락 접촉 상승1,061/1,051/1,051표본,
운반 변위0.5866/0.5825/0.5930m, c3/c5는1,190/1,190검출에도 반전145/146회·hover0.
c4는 제가 한도 조정을 위해 일시 정지한 동안 기존 render Future.result(timeout=30s)의
wall기한을 넘긴 HOST_ERROR다. 정책 실패로 합치지 않으며 스케줄링 유발 실패로 기록한다.
이제 용량 초과는 프로세스 일시 정지가 아니라 시작 전 유한 큐로 처리한다.

**아직 보정/후보 물리 실행0회**인 이 시점에 다음 라운드를 한 묶음으로 확정한다.
세 로봇의 같은 회전진동을 함께 다룬다. 앞의 'r1/r2만 보정, r3 unchanged, 후보6개'
계획을 이 절로 교체한다(실행 중 조건 변경 아님). 보정 명령/길이/6seed/분할/합격문턱은
그대로이며 r3도 동일 고정 시퀀스를 측정한다. 세 초기 위치는 정적 벽 여유를 확보한
(2.8,-1),(3.7,-1),(4.6,-1), yaw조건은 그대로. train/holdout 각18표본/profile.
GT는 고정 응답 측정에만 쓰고 학생의 행동에는 전달하지 않는다.

후보는 pair6개와 cyan6개, 총12조건을 **한 번에 큐에 제출, 최대10개 동시** 실행한다.
남은2개는 빈 슬롯에서 자동 시작하며 실행 중 사람/에이전트의 결과 판정이나 수정은 없다.
최종10cm 안에서만 측정 pulse/full-pose PBVS를 쓰고, cyan에는 기존처럼 yaw성공 조건을
추가하지 않는다. pair의 원래 yaw조건과 모든 위치/접촉 판정은 유지한다.

고정 목록은 [batch-plan.json](batch-plan.json)이다. 앞의 후보 이름6개 대신 아래12개를
사용한다. 공통 child명령의 `--case`만 표와 같이 다르고, SOURCE_SHA/모델SHA는 한 묶음에서 같다.

| 이름 | case | C | seed |
|---|---|---:|---:|
|s3fix11-candidate-pair-c0-r1|pair|0|14201|
|s3fix11-candidate-pair-c1-r1|pair|1|14202|
|s3fix11-candidate-pair-c2-r1|pair|2|14203|
|s3fix11-candidate-pair-c3-r1|pair|3|14204|
|s3fix11-candidate-pair-c4-r1|pair|4|14205|
|s3fix11-candidate-pair-c5-r1|pair|5|14206|
|s3fix11-candidate-cyan-c0-r1|cyan|0|14201|
|s3fix11-candidate-cyan-c1-r1|cyan|1|14202|
|s3fix11-candidate-cyan-c2-r1|cyan|2|14203|
|s3fix11-candidate-cyan-c3-r1|cyan|3|14204|
|s3fix11-candidate-cyan-c4-r1|cyan|4|14205|
|s3fix11-candidate-cyan-c5-r1|cyan|5|14206|

전체 제출 명령(보정 후처리와 후보 시작 사이에 자격 판정만 있으며 튜닝 없음):

```sh
# phase=measure, name=s3fix11-measure-batch-r1; 이후 qualified면 candidate로 같은 방식
ORACLE_HOST=oracle-x86 "$S/oracle_run.sh" "$WT" "s3fix11-$PHASE-batch-r1" -- \
  .venv-sim/bin/python -m scripts.run_s3_x86_cohort --expected-source-sha "$SHA" \
  --phase "$PHASE" --output "outputs/s3fix11-$PHASE-batch-r1/cohort" --execute
# candidate에서만 --model "$MODEL" --model-sha256 "$MODEL_SHA" 추가
```

[Python Future/Executor 공식 문서](https://docs.python.org/3/library/concurrent.futures.html):
전체 작업을 bounded executor에 제출하고 완료 결과를 모은다. Future 대기는 wall timeout이므로
실행 중 SIGSTOP은 정상 스케줄링 수단으로 쓰지 않는다. baseline c4 원본은 보존한다.

새 포트의 실제 실행 경로는 묶음 전 딱1회 `s3fix11-pathcheck-r1`, seed14201/C0으로
확인한다. 명령은 위 보정 개별 명령에 `--path-check` 추가. 첫6고정명령만 실행하여
3SIM초(초기화/settle 포함5.35초), 보정 train/holdout에는 넣지 않는다. 소스·시험 완료 후
실행하고 HOST_ERROR면 경로 오류만 한 묶음으로 고친 뒤 ≤10초 확인을 다시1회 한다.
경로 통과 후 조건6개는 동일 코드에서 동시에 시작한다. 모델 선택 규칙은 변경하지 않는다.

## 기준12개 최종 회수·검증

물리 소스 `7a4bda7ac71bc7b59d7d9a9101d9d3c619498df1`, post-run 평가 `1071e697fc00772a8677d1331d4a9e3e68e94f8c`, host=oracle-x86.
전체 raw40,568파일을 기본 체크아웃 `outputs/oracle-runs/<이름>/raw`로 회수하고 해시 일치를 확인했다.
[로봇별 단계·would_stop·종료·원본 해시](completed-baseline.json), [프레임 판정 요약](baseline-summary.json).

|case/C|hover→하강→닫기|r3 접촉 상승·운반(m)|종료|wall/SIM(s)|
|---|---|---:|---|---:|
|cyan/0|2.80→4.10→5.75|0.5866|DEV_STAGE_FINISHED|384.622/60|
|cyan/1|3.20→4.50→6.15|0.5825|DEV_STAGE_FINISHED|382.322/60|
|cyan/2|3.20→4.50→6.15|0.5930|DEV_STAGE_FINISHED|362.139/60|
|cyan/3|—→—→—|0.0000|DEV_STAGE_FINISHED|384.023/60|
|cyan/4|—→—→—|0.0000|HOST_ERROR|334.847/9|
|cyan/5|—→—→—|0.0000|DEV_STAGE_FINISHED|577.414/60|
|pair/0|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|335.773/60|
|pair/1|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|338.745/60|
|pair/2|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|342.526/60|
|pair/3|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|340.140/60|
|pair/4|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|343.691/60|
|pair/5|r1/r2 모두 0/2|—|DEV_STAGE_FINISHED|339.264/60|

단계 시각은 probe 시작 후 SIM초. cyan c4/c5의 wall은 자체 한도 조정 대기260초를 포함하여 속도 비교에서 제외한다.
pair는 각로봇0/6. r3 접촉 상승·운반3/6시도(완료 정책 시행3/5, 스케줄링 HOST_ERROR1).
11개는60SIM초까지, c4는9SIM초에 render wall timeout으로 종료. 실제 낙하/집게이탈 정지는0.
cyan B도착0/6이며 놓기/귀환 미도달; pair는 집기 전이므로 임무 성공이 아니다.
입력계약·혼합축/짧은 명령0, frame/command 자세 불일치0. 기본 off 본체/카탈로그는 유지한다.
would_stop 원문과 로봇별 계수는 위 JSON에 보존했다: pair admission/POSE_UNCERTAIN,
cyan REAL_PREGRASP_UNCONFIRMED·ARM_COLLISION_GUARD·GRASP_INHAND_UNCONFIRMED·POSE_UNCERTAIN·PATH_COLLISION_GUARD·POSE_CLUSTER_UNCERTAIN.

TensorBoard 새 snapshot `1010-s3fix11-x86-baseline-v2`:12실행270scalar를 이벤트와 실제 서버에서 원본 수치와 대조했다.
영상12개 Range206, Chrome 강에서 핀8개·선택12개·HParams4열과 대표4배속15초 영상 재생 확인.
[검증 JSON](tensorboard-verification.json), [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1010-s3fix11-x86-baseline-v2%2F#timeseries),
[대표 r3 영상](http://127.0.0.1:6007/video/42f1eee45cd08828283e).
첫 offline-only 변환은 schema 미지원으로12개 모두 실패해 별도 빈 snapshot에 보존하고, 표준 result 변환기로 새 v2를 만들었다.
이는 실험 실패/재실행이 아니다. 원본과 기존 snapshots는 수정하지 않았다.

## 후속 묶음 실행 기록

코드/회귀 완료 소스 `259f17e1e442c9bf6519954bde11b42244493885`: 바뀐3파일의 선별9개 회귀와 추가 setup1개, 최종 sequence/setup/cohort3개 재확인 초록 후 push.
최종 고유 검증10개 범위는 trim8개 + 실제 probe loop + workflow catalog이며, 같은 검사의 반복 통과를 추가 표본으로 세지 않는다.
기존 카탈로그 SHA256 `fc5bdf913a9f672bb3adb9597e1925b88a163a7ce1a1b30fb4fed9cf7ad0c813`, main과 바이트 동일.

09:34UTC 전송 전 SSH 실패 후09:40UTC 복구, uptime으로 재부팅 확인. 이때 실행은0이며 원본 손실 없음.
`s3fix11-pathcheck-r1`은 동일 소스로 EXIT0/HOST_ERROR0,6고정 명령×3로봇18응답,
3.00SIM초(초기화 포함5.35), 실행 wall7.765초/전체 process wall30.65초. train/holdout에서 제외.
경로 통과 후 `s3fix11-measure-batch-r1`의 고정6개를 모두 동시 제출했다. 실행 중 조건/코드 변경 없음.

## 보정6개 일괄 판정 — 기각, 후보 실행0

전체6개 EXIT0/HOST_ERROR0, 각18SIM초108응답(총648), 비정상 접촉0.
경로 확인 포함7개 raw189파일 해시 일치. [실행/회수](measurements.json),
[기각 모델과18개 유보 점수](trim-model.json), [기각 표본 진단](rejected-profile-diagnostic.json).

|C/seed|wall(s)|SIM(s)|응답|
|---|---:|---:|---:|
|0/14201|28.347|18|108|
|1/14202|27.760|18|108|
|2/14203|28.198|18|108|
|3/14204|28.499|18|108|
|4/14205|27.710|18|108|
|5/14206|27.863|18|108|

18개 중17개는 방향/유보 XY3mm/yaw.035rad 기준을 통과했다.
**forward +35/.10초만 최대 XY3.08199556mm로 기각**(C4/seed14205/r3/두 번째 반복 index18).
실제 응답 `(13.9511,3.1327)mm`, 예측 `(15.2632,.3439)mm`, yaw잔차.00318450rad.
문턱 초과는.081996mm이지만 사전 기준을 완화하거나 이 명령만 사후 제거하지 않는다.
고정한 all18 profile 자격 조건에 따라 전체 모델qualified=false, 후보12개와 full smoke는0회다.

원인 분리: 같은 +35/.10초의 전체 평균 전진은 첫 반복16.6563mm, 두 번째13.7697mm,
횡방향은-.07975→1.09047mm로 달랐다. 단일 평균 모델의 반복/이력 의존 잔차가 관찰되며,
어떤 물리 상태가 원인인지는 아직 분리하지 않았다. 로봇별 모델이면 해결되거나 단순 문턱 문제라고 단정하지 않는다.
다음 물리 제안: **명령 전 정지 시간·직전 명령을 요인으로 고정한 전체 보정 묶음을 사전 등록해 이력 의존성을 먼저 검증**한다.
현재 라운드 중 조건/seed/문턱/모델 선택 규칙은 변경하지 않았다.

준비한 full-pose PBVS와 합법≥.10초 pulse/공유 PF 예측기 연결은 회귀 검증 범위이며,
새 후보의 실제 정렬·집기 성능은 미검증·기본off다. PF plausible-only 100/500/새100 비교도 기존0/12 상태이며 새 성능 주장이 없다.

보정 TensorBoard는 `1010-s3fix11-x86-measure-v2`에 경로 확인1개·보정6개·기각 판정1개,63scalar를 등록하고 이벤트/서버 수치 대조를 완료했다. 첫 변환의 출처 필드 형식 오류8건은 빈 snapshot으로 보존하고 새 v2에서 수정했다(물리 재실행 아님). [보정 검증](tensorboard-measure-verification.json). 기준270개와 합계333scalar, 실행 raw40,757파일을 검증했다.
