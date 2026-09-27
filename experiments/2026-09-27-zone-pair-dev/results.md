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
