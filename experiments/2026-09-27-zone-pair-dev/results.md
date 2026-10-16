# Pair executor dev PHYSICAL 실행 결과 — 2026-09-27

**tags_temporary, dev, 연구 결과 아님.** 실행: Claude(코디네이터 위임), branch `codex/zone-pair-executor`,
PR #235. 소스 `521e5567e4a1d1b0614b86b8bf355e994edca890`(clean, origin과 동일, 추가 커밋 없이 고정).
사전 기록은 README대로 `prereg_DRAFT.json`을 그대로 사용했다(드라이버가 `status: DRAFT`를 요구하고
실행 SHA는 `--expected-source-sha`로 고정). prereg SHA256 `85334a68…a0fe0f3`, 기준 변경 없음.

## 요약

| 실행 | seed | 결과 | SIM s | wall s | 명령 | API/모델 호출 | 판정 |
|---|---:|---|---:|---:|---:|---:|---|
| dev01 | 901 | **HOST_ERROR** (적용값 검증 거부, 물리 시작 전) | 1.30 | 1.41 | 6 (host 초기 servo·hold만) | 0 / 0 | EVIDENCE_INCOMPLETE, 성공 아님 |
| dev02 | 902 | **실행 안 함** (README 절차: host 오류 시 shell 중단) | — | — | — | — | abort 진단 미수행 (`not_exercised`) |

단계별: 접근·공동 파지·들기·문 통과·B 배치/방출·낙하/접촉·GO/abort 감사 **모두 미시도**.
actor `look_around`/`pair_carry` 제출 0건, r1/r2 동작 명령 0건, STATUS·GO 0건.

## dev01 실패 원인 (정확한 단계)

`DevHost.__init__` 직후 `applied_settings(host)`가 모델의 실제 적용값을 사전 기록과 대조하다 거부했다
(`manifest.simulator_start_s = null`, 즉 평가 관측 시작 전).

```
ValueError: actual model settings differ: {... 'weld': False, 'contact_profile': 'cargo_noslip_v1',
 'noslip_iterations': 10, 'timestep_s': 0.00025}
```

- 사전 기록·드라이버 `EXPECTED`: `timestep_s = 0.002`.
- 실제: `cargo_noslip_v1`의 base인 `local_contact_fine`이 `sim/dispatch_contact_profile.py:24`에서
  timestep을 **0.00025 s**로 설정한다(`sim/zone_cargo_contact.py`: base `local_contact_fine` + noslip 10).
- 나머지 적용값(지도, r1/r2/r3, long_beam 1개, 활성 상자 0, weld OFF, noslip 10)은 일치했다.
- 즉 사전 기록/설계 게이트 3의 "timestep 2 ms" 전제가 표준 접촉 프로필과 맞지 않는다. 가드는 설계대로
  fail-closed로 동작했다. 기준이나 코드를 바꾸지 않았고 재시도하지 않았다.
- 해결에는 사전 기록 기준(timestep, `max_sample_gap_s`, 접촉 스텝 수 계산 등)과 드라이버 `EXPECTED`의
  수정 및 새 코호트가 필요하다. 사용자/구현자 결정 사항이다.

부수 관찰: 평가기(`evaluate_zone_pair_dev.py`)는 이 host 오류 실행에 대해 verdict를 `HOST_ERROR`가 아니라
`EVIDENCE_INCOMPLETE`(error: "planned route does not match preregistered set-down targets")로 낸다.
pair 기록이 비어 있어 경로 대조에서 먼저 예외가 난 것이다. 성공 아님은 동일하나 원인 표시는 manifest를 봐야 한다.

## 운영 기록

- 잠금: `agent_lock acquire --owner claude --branch codex/zone-pair-executor --purpose "pair dev physical dev01/dev02 521e5567…; no model calls" --pid 81629 --expected-minutes 245`
  (04:56:15Z 획득, 04:56:18Z trap으로 반환; 이후 `status` = null). 획득 시 다른 잠금 없음.
- 부하 평균(시작=종료): 20.23 / 12.55 / 11.21 (8 코어; 다른 MuJoCo/시뮬레이션 프로세스 없음, 주 부하는 fileproviderd·TensorBoard·UI).
- 세션: `ugrp_session.py run pair-dev01-521e5567` (pgid 81639, child 81646) → 종료 확인. driver 81629 포함 잔여 프로세스 없음.
- 디스크 여유 106 GiB. 관리 workflow `zone-pair-dev` 0.1.0, 기록 `status: process_failed`, exit 2, runtime 2.62 s.
- 영상 검토: overview.mp4·trace.jsonl이 생성되지 않아(관측 시작 전 거부) 검토 기록을 작성할 대상이 없다. `video_review` 미수행.

## 원본 (로컬 전용, 원격 백업 아님)

루트 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-521e5567e4a1d1b0614b86b8bf355e994edca890/`

| 파일 | SHA256 |
|---|---|
| dev01/manifest.json | `7481c9041f1d0101a7642eab97cd73d4f45f9e689e2e1ce86852277bf20bcf17` |
| dev01/prereg.json | `85334a68bae0d35c197c612cd610c84307c0eba268a34247e71f4e233a0fe0f3` |
| dev01/result.json | `cdd61562b48f8f4a0417650118f63d8e1ccd9ce99868ab1bf89780035a8debec` |
| dev01/commands.jsonl | `7f1045bfdb4d2c1b95770bd7534e4ae30de5c8d19efdeed6a12b84f300257867` |
| dev01/eval_only/result.json | `6005baf197bde38a89dbc2d83f8037ae2e973d927a03b10dc316cadc337ac631` |
| dev01/eval_only/review-01/result.json (평가기 재실행) | `d37dd2b724013c50724504dc5420db880d88d965dab49801dea05b8659219ce6` |
| dev01/artifacts.sha256.json (14개 파일, 재계산 불일치 0) | `2552cdb97bb877f8419ed298f419421cabbc2af2ee4543b26ba4de8272c3bddd` |
| dev01-managed/manifest.json | `3d5e31b2a0f7b9f3456cfcdf5b6b5196e72ce0e627d878b1e74dccef99997a09` |
| dev01-managed/console.log (빈 파일) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

`status.jsonl`, `shutdown.jsonl`, `events.jsonl`은 0 byte, `api_calls.json`·`pair_records.json`은 `[]`.
`eval_only/trace.jsonl`, `contacts.json`, `overview.mp4`, `applied_model.xml`은 생성되지 않았다.

## TensorBoard

새 snapshot `/Users/changmin/projects/ugrp/outputs/tensorboard/0927-zone-pair-dev` (run 1개,
원본 해시를 담은 파생 보기 `tb-view/dev01/result.json`에서 변환). 기존 서버(PID 9293, logdir
`outputs/tensorboard`, 다른 작업 소유)를 재시작하지 않고 run 등록과 값(success 0, SIM 1.3, wall 1.41,
commands 6, model_calls 0)을 EventAccumulator·서버 API·브라우저 화면에서 확인했다. 영상 없음.
처음 review-01만 변환한 snapshot은 삭제하지 않고 `<raw>/tensorboard-superseded/`로 옮겼다.
`outputs/tensorboard-view.json`에는 `zone_pair_dev_20260927` 키만 추가했다(기존 키 byte 동일).

## 검증 범위

- 확인: 소스 고정·clean, 잠금 획득/반환, 관리 workflow 기록, 적용값 가드의 fail-closed 동작, 원본 해시.
- 미확인: 모든 물리 단계, GO 동시 소비, abort 경로(dev02), r3 비간섭, 영상 검토, 설계 게이트 3~6.

---

# v2 코호트 dev03/dev04 — 2026-09-27

**tags_temporary, dev, 연구 결과 아님.** 코디네이터 결정(#221): `cargo_noslip_v1`과 0.25 ms timestep 유지, 새 사전 기록.
소스 `9f28cbf030442a701a666899c02ebb4374e3e3e2`(clean, origin 동일), `prereg_v2_DRAFT.json` 그대로 사용
(README대로 별도 승격 없음, SHA256 `896091d17022d569dfb34123587712395bf9870d065ce2b438d38acedee9108b`).
위 v1 dev01 기록은 그대로 보존한다. v1과 v2 결과는 합산하지 않는다.

## 요약

| 실행 | seed | 종료 | SIM s (시작→끝) | wall s | 동작 명령* | API / 모델 | 판정 |
|---|---:|---|---:|---:|---:|---:|---|
| dev03 (정상 시도) | 901 | completed / STUDY_LAYER_DONE | 1.30→67.50 | 170.4 | 22 | 4 / 0 | DEV_NOT_CONFIRMED, 성공 아님 |
| dev04 (abort 진단) | 902 | completed / STUDY_LAYER_DONE, `intervention_not_reached` | 1.30→67.50 | 167.4 | 63 | 4 / 0 | DEV_NOT_CONFIRMED, abort 진단 미통과 |

\* 평가기 기준 drive/mecanum/arm/look 행. 전체 command 행은 dev03 551, dev04 492(대부분 hold).
두 실행 모두 SIM/wall 한도(900 s / 57,600 s)보다 훨씬 일찍 정상 종료했다. 멈춤·수동 중단 없음.

## 단계별 결과와 원인

두 실행 모두 **접근 이전 단계(공동 제출/랑데부)에서 종료**했다. GO 0건, 접근·공동 파지·들기·문·B 배치 모두 미시도.

- dev03: `look_around`가 두 로봇 모두 12.0 s에 `SWEEP_TRANSITION_BLOCKED`(서쪽 벽 여유 guard) 실패.
  60.0 s에 r1 `pair_carry` 거부 **`SELF_UNCERTAIN`**, r2는 수락 후 `start_ready`만 보내다
  65.0 s `PAIR_RENDEZVOUS_TIMEOUT` → STATUS abort. abort 뒤 양쪽 queue 비움·추가 동작 0건·0.5 s 관찰 충족.
  정상 실행에 필요한 GO 33종이 모두 없어 protocol 실패.
- dev04: r2 `look_around` 11.4 s `SWEEP_TRANSITION_BLOCKED`, r1은 11.5 s 완료. 60.0 s에 r2 `pair_carry`
  거부 **`SELF_UNCERTAIN`**, r1 수락 후 65.0 s `PAIR_RENDEZVOUS_TIMEOUT`. r2의 `carry_go_0`에 도달하지 않아
  사전 등록 abort 주입이 실행되지 않았다(`intervention.json` 없음) → `intervention_not_reached`, abort 진단 통과로 세지 않음.
- `SELF_UNCERTAIN`은 `pair_readiness()`의 `uncertain` 분기(gate/보고 신선도/std 유한성/관측 나이/servo 집합)다.
  어느 하위 조건인지는 raw에 기록되지 않아 **원인 하위 조건은 미확인**이다. 60 s 당시 거부 로봇의 자기 추정
  std는 dev03 r1 약 5.0 cm / 0.015 rad였다(수락한 쪽과 비슷함). 평가 GT로 제어를 보정하지 않았다.
- 적용값 일치(timestep 0.00025, noslip 10, weld OFF), trace·접촉 coverage 완전(dev03 접촉 264,801 step 일치),
  금지 접촉 0, r3 검사 통과, source/input 변경 없음.

## 영상 검토

`eval_only/video-review-01.json`(검토자: Claude Opus 5.5, 코디네이터 위임 에이전트, 사람 아님).
332프레임 5 Hz overview에서 SIM 1.3/7.3/11.9/31.3/59.9/61.3/64.9/67.5 s 프레임을 확인했다.
세 로봇이 서쪽 벽 depot 출발 위치에 계속 있고 빔도 초기 위치 그대로다. 모든 단계는 **미도달로 false**,
낙하·충돌은 보이지 않았다. 검토 기록은 trace/영상 SHA와 연결되어 있고 `review-01/result.json`에 반영됐다(verified=false).

## 운영

- 잠금 `claude`, driver PID 1222, 예상 1925분(README 계산식), 05:12:51Z 획득 → 05:18:32Z 반환, 이후 status null.
- 부하 평균: 획득 5.58/8.82/10.95, dev03 끝 9.47/7.78/10.05, dev04 끝 8.47/9.02/10.21 (8코어, 다른 MuJoCo 없음).
- 세션 `pair-dev03-9f28cbf0`(pgid 1235), `pair-dev04-9f28cbf0`(pgid 2953) 종료 확인, 잔여 프로세스 없음.
- 관리 기록 `process_completed`, exit 0 (runtime 171.6 s / 168.5 s). 재시도·추가 실행 없음.

## 원본 (로컬 전용, 원격 백업 아님)

루트 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v2-9f28cbf030442a701a666899c02ebb4374e3e3e2/`
(dev03 26 MB, dev04 25 MB; 각 `artifacts.sha256.json` 2,012개 파일 재계산 불일치 0).

| 파일 | SHA256 |
|---|---|
| dev03/manifest.json | `c82f53ea6ff59e30414bb925414eb89ee6d9fa5ee8e9f07a689ec1fc2f3d8f8e` |
| dev03/artifacts.sha256.json | `876cbc79b0d66fe354f8f83b871a83d92c9827445b82d47e90ec65e7519c2f93` |
| dev03/eval_only/trace.jsonl | `8ce94e3e584c4b6ed207e51b89cf681569080385469da947f627375edb9e927a` |
| dev03/eval_only/overview.mp4 | `b4e0ee85d577c03931630b7b72799583da9a813dd8a58bb3aa5b998a775db74d` |
| dev03/eval_only/video-review-01.json | `cadae6ad76e9e2ea819cf09dba3c2c4e73460c843a54da03cd24935981e3c992` |
| dev03/eval_only/review-01/result.json | `398f26bfc4c4b6b6259d1ef00448e2a4c9c2fa185bcbeefcec3a9e8a073ade2b` |
| dev03-managed/manifest.json | `85e03078219e3843762259366a37e33b21c506716618f1e200942bcbff3a7a76` |
| dev04/manifest.json | `01685d3ff59fb09c23cf1e0c3df225373f876a8dd77a07205ed8e32074ca518e` |
| dev04/artifacts.sha256.json | `b891b3f09080f2e0974195b03035fa0584b21d81831f4f3273dfb0e069dd6bf3` |
| dev04/eval_only/trace.jsonl | `9bd15ccb90e1746ceace4aafa36b44bf18caa88f5177425c056f1192c1efd11a` |
| dev04/eval_only/overview.mp4 | `61dacc54ec2315eb4cd916a0aeef398fb371487e21edaf87260d6af3a30df1f4` |
| dev04/eval_only/video-review-01.json | `24c2fde8c70f2992f6e0ed03d87e682e28af04712190ae2697f241de371c1f42` |
| dev04/eval_only/review-01/result.json | `96c66809ec0e68e2acfbd6c518d64db5d672ecfcd28efcc314bafcd4c98bfadb` |
| dev04-managed/manifest.json | `fa1114173334b971edec8cc6384082e527eac5654b6f8b407a282b19fe51f06b` |

## TensorBoard

기존 snapshot을 덮어쓰지 않고 새 collection `0927-zone-pair-dev/v2`에 run 2개
(`v2/eval_only__review-01__5416d0a5`=dev03, `v2/eval_only__review-01__56a9288b`=dev04)를 추가했다.
view 키 `zone_pair_dev_v2_20260927`만 추가(기존 키 byte 동일). 기존 서버(PID 9293)를 재시작하지 않고
서버 API·브라우저 pinned 카드에서 success 0, SIM 67.5, wall 170.4/167.4, 명령 22/63, 모델 0을 확인했다.
**영상은 TensorBoard media로 등록되지 않았다**: 변환기는 `motion.mp4`/`execution.mp4`만 링크하며 README의
`overview.mp4` symlink를 인식하지 않는다(코드 미변경, 후속 과제).

## 검증 범위 (v2)

- 확인: 적용값·coverage·금지 접촉·r3·abort 뒤 queue 정리(dev03, 랑데부 실패 abort 경로), 영상과 기록 일치.
- 미확인: 접근·공동 파지·들기·문 통과·B 배치, GO 동시 소비, 사전 등록 carry-GO abort(dev04 미도달),
  `SELF_UNCERTAIN` 하위 원인, look_around sweep guard 실패의 정당성. 추가 실행은 새 사전 기록이 필요하다.
