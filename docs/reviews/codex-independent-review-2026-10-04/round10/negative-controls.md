# 좁게 반박한 추가 가설

아래 두 감사는 source와 합성 대조가 반박한 범위다. 새 버그로 세거나 전체 runtime 인증으로 확대하지 않는다.

# R9 후속 — capture timestamp와 relocalization 경계

검토 source: #363 `6727751b49ce11fb62234bb97274137f22850765`. **아래 경계에서 새 결함은 발견하지 않았다.** temporal-weight 설계 caveat와 별개로, P03 adapter의 acquisition clock·reset·close가 현재 source의 계약을 지키는지 좁게 확인했다. 실제 runtime, worker, RGB, 물리 latency를 실행한 검증은 아니다.

`vision-timestamp-repro.py`는 hash가 고정된 원본 `zone_study_pose_delay_p03.py`의 class/function 본문을 그대로 실행한다. underlying provider는 time·last-fix·command event만 기록하는 fake다. legacy tag-provider identity import만 독립 실행을 위한 stub으로 대체하며, current HighPoseSource와 같은 non-legacy 분기로 진입한다.

| 조건 | 합성 결과 | source 경계 |
|---|---|---|
| capture10.00, receipt10.10 | report10.15에는 fix 없음, 10.16에서 `last_fix_t=10.00`; completion/receipt로 timestamp를 새로 만들지 않음 | delay adapter 106–142 |
| duplicate10.00, future11.00, stale9.90 | 셋 모두 rejection, 기존 fix timestamp10.00 유지 | 114–121 |
| 같은 time의 frame 뒤 command | `[frame10, command10, frame10.05, command10.05]` 순서 그대로 release | heap sequence 86–96,131–142 |
| t11 relocalization | provider clock10.84에서 이전 receipt 무효화; queued frame10.9는 제거, queued command10.9는 보존 | 153–171 |
| reset 이후 늦게 도착한 capture10.95 | reset floor11보다 오래되어 거부; capture11은11.16부터 새 fix 가능 | 114,160–166 |
| close | pending 비우고 underlying close; frame/command/report 입력 거부, 중복 close는 안전 | 180–187 |
| 모든 시간에 +100초 | release와 age 관계 동일 | fake clock translation control |

provider report는 release cutoff로 예측할 수 있지만 `last_fix_t`는 capture 시각이다. “estimate time과 last fix time이 항상 동일해야 한다”는 잘못된 기준으로 버그를 추가하지 않았다. 한 frame이 오래된 것과 오래된 fix를 가지고 현재 cutoff까지 예측한 belief는 서로 다른 상태다.

## 실제 caller와 API 범위를 구분한 부분

현재 `scripts/run_pair_highpose.py:228–242`는 동기 capture 후 같은 `backend.now`로 `runtime.on_frames`를 호출한다. `sim/final_pair_v3.py:161–189`의 capture는 동기 port capture/파일 기록이며 SIM advance는 runner의 다음 단계다. `CameraRobotPort.capture`(`sim/camera_robot_port.py:100–118`)와 backend `now`(`sim/final_environment_checks.py:42–44`)는 같은 world time을 사용한다. 따라서 현재 정상 caller에서는 acquisition과 호출 time이 동일하다.

`ZoneOwnExecutor.on_frame`(`harness/zone_own_executor.py:217–230`)는 관측의 own robot/camera/frame/age/hash를 검사하지만 pose provider에는 `now`를 전달한다. delay adapter의 optional `captured_sim_s`를 쓰지 않는다는 사실만으로 **현재 동기 runner가 오래된 영상을 fresh fix로 바꾼다고 주장하지 않는다.** 향후 delayed transport를 연결한다면 실제 acquisition time을 optional 인자로 보존해야 하며, 그 caller는 별도 검토 대상이다. validation의 `max_age_s=.25`가 acquisition timestamp 전달을 대신하는 것은 아니다.

## reference reset의 source상 의미

`VisionPoseSource.begin_relocalization`(`vision_pose_source_p03.py:137–153`)은 현재 PF belief/uncertainty를 보존하고 `last_scan_t`와 `last_obs`를 비운다. 새 dock prior를 넣거나 servo 명령을 새로 만든다는 요청이 아니다. `PairVisionPoseSource.begin_relocalization`(`vision_pose_source_pair_v3.py:130–138`)은 last fix quality도 무효화한다. beam-relative-yaw tracker의 과거 누적량을 여기서 무조건 재설정해야 한다는 주장은 source 계약으로 뒷받침되지 않아 기각했다.

HIGH provider는 frame을 tracker로 보내기 전에 `now >= pf.t`와 `_last_frame_t`의 strictly increasing 조건을 검사한다(`vision_pose_source_highpose.py:94–110`). tracker 단독 API에 과거 시각을 주어 availability의 음수 age를 만드는 것은 현재 caller가 통과시키는 사례로 세지 않았다. calibration/gain/resolution은 provider construction에서 고정되며 정상 실행 중 교체하는 caller도 찾지 못했다. hot-swap을 가정한 epoch 문제를 새 결함으로 추가하지 않는다.

## 실행

원본 결과 JSON을 보존하도록 script와 `vision-source/`를 새 임시 폴더에 복사한 뒤 그곳에서 실행한다.

```sh
python vision-timestamp-repro.py
```

Python 표준 라이브러리만 필요하다. script 옆 `vision-source/manifest.json`과 `zone_study_pose_delay_p03.py`가 필요하고 source SHA256을 검사한다. 결과는 `vision-timestamp-results.json`에 저장한다. 여기서 통과한 fake provider는 실제 PF/영상 파이프라인 전체의 인증이 아니다.

---

# 9차 후속: 응답 정규화·요청 ID·claim admission 음성 대조

소스: PR #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 앞선 `runtime-protocol-audit.md`와 분리한 추가 coverage다. **새 결함으로 올릴 결과는 없다.**

## 실제 응답 경로 9개 대조

`runtime-response-admission-repro.py`는 옆의 `runtime-protocol-repro.py`에 있는 정확한 Git 복원 utility를 재사용한다. 같은 폴더에 두고 다음처럼 실행한다.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 runtime-response-admission-repro.py \
  --repo /path/to/UGRP-Multi-Robot-Collaboration-Project \
  --output runtime-response-admission-repro.json
```

실제 `GeminiProxyCompleter(study_json=True)`/`ModelCallTransport`/`SendLedger`/`EventScheduler`와 PairTrial `finish_call`, pair `validate_reply`의 unmodified AST 몸체를 사용했다. request fixture는 문자열 요청 ID, 이미지 없음, 고정 text bill 100이다. 여기서는 multimodal request builder나 물리 실행을 재검증하지 않는다. action callback은 기록만 한다. 모든 wire는 fake이며 각 case의 POST count는 1, provider usage 150, send violation은 0으로 보존되었다.

| fake 응답 | completion gate | call outcome | action callback |
|---|---|---|---|
| 고유 키, 올바른 ID | 통과 | ok | continue |
| stale request_id | 통과 후 schema 거절 | invalid | 없음 |
| duplicate ID: stale 먼저, correct 마지막 | 통과 | ok | continue |
| duplicate ID: correct 먼저, stale 마지막 | 통과 후 schema 거절 | invalid | 없음 |
| duplicate action: continue 먼저, look_around 마지막 | 통과 | ok | look_around |
| duplicate action: continue 먼저, unknown 마지막 | 통과 후 schema 거절 | invalid | 없음 |
| 정확한 단일 json fence | 통과, fence 제거 기록 | ok | continue |
| JSON 앞에 prose | 거절 | error | 없음 |
| JSON object 2개 연속 | 거절 | error | 없음 |

[parse/unwrap](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/three_robot_plan.py#L55-L70), [completion admission](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/llm_completion.py#L112-L125), [pair look normalization](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L73-L92), [request ID/schema validation](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L711-L768)은 같은 JSON parser 결과를 사용한다. Duplicate key는 모두 Python decoder의 last-wins 결과로 일치한다. 마지막 action이 허용되지 않거나 마지막 ID가 틀리면 실행되지 않았다. 서로 다른 layer가 다른 결정을 채택하는 반례는 없다. 중복 키를 금지하는 추가 정책은 가능하지만 그 자체를 현재 결함으로 세지 않는다.

## 요청 ID 범위와 durable identity

PairTrial의 모델-facing ID는 [prepare 369–375](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L369-L375)의 run-local call serial에서 만든다. 다른 run에서 같은 literal이 다시 생길 수 있다. 그러나 이것만으로 다른 run의 실제 응답을 혼용한다고 할 수 없다. 검사한 transport는 [단일 owner thread와 call별 bound opener](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_transport.py#L90-L148)를 사용하고, request/response raw bytes와 SHA256은 해당 send ledger에 연결된다. MainStudyBudget의 [durable request 205–225](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_main_budget.py#L205-L225)는 UUID key와 run_key를 별도로 저장한다.

검사한 실제 call chain에는 run-local request_id만으로 응답을 돌려주는 공유 cache가 없다. 모델-facing ID를 인증 토큰이나 전역 request identity로 해석하지 않되, 존재하지 않는 cache collision/cross-run replay 버그를 만들지 않는다. 임의로 악성 proxy를 가정한 바꿔치기나 provider 모델 변경 발생도 이번 범위에서 입증하지 않았다.

## 고정 역할 claim 가설 기각

pair schema가 양쪽 role enum을 허용한다는 사실만 보면 r1이 r2 역할을 고를 수 있어 보인다. 하지만 실제 [executor_plan 276–284](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_integration.py#L276-L284)은 pair long_beam order에서 actor별 `r1=end_neg`, `r2=end_pos`를 검사한다. 틀리면 `Plan(None, rejected_reason='UNSUPPORTED_PAIR_ROLE')`다. 실제 [PairTrial release 465–490](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L465-L490)는 api가 없으면 executor를 호출하지 않고 거절 action을 기록한다. frontier 담당도 독립으로 같은 actual caller를 확인했다. 이 항목은 source 확인이며 별도 물리 테스트를 수행한 것이 아니다.

잘못된 destination을 runner가 몰래 고쳐준다는 인접 가설도 [ClaimGate 모듈 계약과 start](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_runtime.py#L1-L121)의 CLAIM 인자 보존 때문에 기각한다. 원래 scripted 인자로 대체하지 않고 허가에 기록된 zone/partner를 원래 Team.start에 그대로 건넨다. 잘못된 모델 행동의 schema 수용, dispatch 거절, physical 실패를 같은 사건으로 합치지 않는다.
