# 12차 — 소유 worker 초기화 실패와 정리 경계

고정 source: PR #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 현재 pair live caller와 기반 v88 provider의 실제 코드 경로를 검토했다. **새 P2 후보는 worker를 생성한 직후의 초기화 오류가 명시적 정리 밖에 있다는 점이다.** 실제 child/프록시/모델/물리 실행, 사용자 프로세스 조회·종료, credential·raw·heldout 열람은 없다. 결과는 fake process와 selector를 사용한 한정 재현이다.

## R12-R1 — Popen 뒤 selector 설정 실패가 worker 정리를 건너뛴다

[`VisionWorkerClient.__init__`52–64](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/vision_loc_client.py#L52-L64)는 child를 만든 다음 `os.set_blocking`, selector 생성, stdout 등록을 실행한다. `_closed` 설정과 `atexit.register(self.close)`도 이 작업 뒤다. cleanup이 있는 `try`는 그 이후 ready 메시지 수신에서 시작한다.

따라서 child 생성은 성공했으나 selector 생성/등록이 `OSError(ENOMEM)`으로 실패하면, constructor는 worker의 `kill`, `wait`, pipe close, selector close를 시도하지 않고 빠져나간다. 완성된 client가 반환되지 않아 상위 provider도 그 소유권을 받지 못한다. 이는 bad-ready/ready-timeout 경로와 다르다. 후자는 이미 try 안에 있어 `_fail`과 `close`를 통과한다.

현재 호출 연결은 다음과 같다.

1. [`run_pair_case`198–208](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L198-L208)가 backend를 만들고, LLM arm이면 GatedRuntime을 만든다.
2. [`GatedRuntime`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_runtime.py)의 기반 [`Runtime`24–41](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_final_pair_runtime.py#L24-L41)는 robot별 provider를 **반환받은 뒤** `self.providers`에 넣는다.
3. [`PairVisionPoseSource`108](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/vision_pose_source_pair_v3.py#L108-L108)가 기본 worker로 `VisionWorkerClient(self.cfg)`를 만든다. [`build_provider`147–154](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/vision_pose_source_pair_v3.py#L147-L154)의 try도 이 provider constructor가 반환된 뒤 시작한다.
4. Runtime는 이미 등록된 r1 provider를 닫는다. 그러나 r2 constructor 안에서 실패한 worker는 등록되지 않았다. case에서도 runtime 대입이 완료되지 않아 runtime는 None이고 backend만 정리된다.
5. ENOMEM은 [`HOST_ERRNOS`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L55-L57)에 포함된다. 첫 모델 요청 전이면 실제 [`run_attempts`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L560-L591)는 한 번 더 시도할 수 있다.

이는 현재 #363 HIGH의 synchronous OpenCV worker를 말하는 것이 아니다. #371이 사용하는 v88 기반 provider의 별도 subprocess 경로다. rule arm의 기반 Runtime도 같은 provider를 사용하지만, 위 재시도 연결은 LLM live runner에 한정한다.

## 합성 재현과 정상 대조

`runtime-worker-startup-repro.py`는 exact Git source에서 constructor, cleanup, Runtime, case, retry, SQLite 정의를 AST로 가져오며 해당 몸체를 수정하지 않는다. Popen·pipe·selector·ready 수신, provider의 calibration holder, backend, evaluator만 대역이다. standalone constructor의 정상 ready 값은 대역이므로 실제 checkpoint/model readiness 검증을 다시 실행한 테스트로 해석하지 않는다.

| 대조 | child 생성 | 종료·회수/정리 | 결과 |
| --- | ---: | --- | --- |
| 정상 constructor 후 close 2회 | 1 | EOF, wait, selector·pipe close; 중복 close 무해 | 정상 |
| Popen 자체 실패 | 0 | 소유 child 없음 | 예외만 반환 |
| ready timeout | 1 | kill, close, pipe·selector 정리 | WorkerFailure |
| selector 생성 ENOMEM | 1 | **kill/wait/pipe close 0, atexit 등록0** | OSError |
| selector register ENOMEM | 1 | **child와 만들어진 selector 모두 정리0** | OSError |

실제 case→Runtime→worker→retry 대조에서는 첫 robot을 정상 생성한 뒤 둘째의 selector 생성만 실패시킨다. 첫 robot과 backend는 정상적으로 닫힌다. 하지만 둘째 worker에는 정리 호출이 없고, 2차 attempt를 시작할 때 fixture의 `prior_alive=[10001]`로 남는다. 2차도 같은 실패를 주입하면 두 attempt 모두 `HOST_ERROR`, `failure_class=infra:HOST_ERROR`, 모델 요청0으로 기록된다. `cleanup_error`는 None이다. cleanup 누락의 대상이 caller에 반환되지 않아 그 정리 경로에 들어가지 않았기 때문이다.

별도 Runtime→retry 대조에서는 2차 attempt를 정상으로 두어, 허용된 재시도가 성공해도 첫 attempt의 미반환 worker에 대한 정리 호출이 새로 생기지 않음을 확인했다. 이는 실패 분류를 숨기거나 paid request를 반복하는 결함이 아니다. 합성 SQLite에서도 모델 요청 수와 charge는0이다.

## GC와 실제 영향의 한계

이 client에는 `__del__`이나 weakref 정리 경로가 없다. 예외 발생 위치는 atexit 등록보다 앞이다. 검토 환경의 CPython 3.12 `subprocess.Popen.__del__`도 아직 실행 중인 child를 종료하지 않고 poll 후 `_active`에 보존한다. 따라서 garbage collection을 다음 attempt 전 명시적 child 회수 보장의 대체물로 삼을 수 없다. 프로젝트가 지원하는 모든 Python/OS 구현을 검증한 것은 아니다.

최종 fixture는 selector의 ENOMEM 자원 실패를 사용한다. 단순한 단일-thread fd 소진만으로 Popen 직후 EMFILE가 반드시 생긴다는 주장은 하지 않는다. Popen은 생성 과정에서 쓰던 임시 fd를 닫으므로, 그 단순 시나리오는 별도 도달성 근거가 필요하다. 실제 OS 자원 고갈을 일으키거나 실제 child를 시작하지 않았고, 실제 GPU/CPU 잔류량·잔류시간·현장 빈도·과거 시행 영향을 측정하지 않았다. 입증한 것은 **이 지원되는 초기화 실패 경계에서 정리 호출이 빠지고, 정상 caller의 재시도가 그 상태를 선행 회수 없이 진행할 수 있다는 코드상 계약**이다.

## 닫는 기준

child가 생성된 순간부터 실패에 대한 소유권과 정리 책임을 갖도록 초기화 구간을 보호한다. 아직 selector나 `_closed`가 없는 부분 초기화 상태도 안전하게 정리하고, child의 유한한 종료/회수 또는 명시적인 정리 실패를 기록한 뒤 caller가 다음 attempt 여부를 결정할 수 있어야 한다. 이미 등록된 다른 robot provider와 backend도 계속 독립적으로 정리해야 한다.

정상 ready, ready 실패, Popen 전 실패, Popen 후 selector 생성/등록 실패, r2 생성 실패 시 r1 정리를 함께 검증한다. 기존의 모델 요청 후 재시도 금지와 비용 보존 규칙을 유지한다. borrowed proxy 프로세스를 대신 종료하거나 원래 저장물을 지우는 수정은 이 기준에 포함하지 않는다. 이번 감사에는 구현 수정이 없다.

## Borrowed proxy에서 새 결함으로 올리지 않은 것

현재 `scripts/run_pair_llm.py`는 이미 실행 중인 proxy PID를 받아 [`live_adapter`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_live.py#L125-L140)에서 read-only preflight를 한다. 이 caller가 proxy를 시작하거나 소유·종료하지 않는 것은 명시된 계약이다.

[`proxy_profile`/`runtime_identity`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_pilot_ledger.py#L22-L56)는 audited source hash, 명령의 source path, source 저장 이후 process 시작 시각, 지정 PID의 명시 loopback listener를 검사한다. [`_preflight_live`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L325-L346)는 POST 전에 source hash와 PID 생존을 다시 확인한다. 실제 CLI는 test-only fake wire 인자를 노출하지 않는다.

이것은 실행 중인 서비스에 대한 snapshot provenance이며, PID 재사용·악성 process 변장·동시 listener 교체까지 인증하는 보안 프로토콜은 아니다. 그러한 사건의 실제 supported launcher 경로를 찾지 못했으므로 이론적 race를 신규 결함으로 올리지 않는다. proxy의 실제 현재 파일, credentials, 프로세스, endpoint를 조회하지 않았다.

## 재실행

```sh
python runtime-worker-startup-repro.py --repo /absolute/path/to/repo --source-ref a009112ff5fb18c6b64f58d8cd6392c58d4c028c --output /tmp/runtime-worker-startup.json
```

표준 Python과 해당 Git object만 필요하다. 외부 checkpoint, 모델 package, 실제 worker/HTTP 프로세스, physics가 필요 없다. source를 읽는 `git show`/`rev-parse`만 subprocess로 호출한다. companion JSON은 실행 SHA와 읽어온 source별 SHA-256을 담는다. fake PID는 fixture 식별자이며 실제 PID가 아니다. 재현의 golden 및 manifest는 동일 디렉터리에 보존한다.
