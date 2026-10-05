# 23차 독립 검증

Memory 비교는 source-only이고 final-tick은 선택한 실제 AST와 명시된 대역을 연결한 합성 실행이다. 둘을 전체 실행 검증으로 합치지 않는다.

## Memory caller source

**PASS — 새 결함·실행 결과를 추가하지 않은 source 범위 검증이다.** 원고의 optional M1 비교와 현재 pair/HIGH를 분리하는 범위를 수용한다. main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 source manifest 12개 SHA256을 Git object와 독립 대조했다. Python으로 source 텍스트와 AST를 읽었으며 대상 module import·fixture·pytest·렌더·physics·model·코호트 실행은 하지 않았다. 실제 등록 파일·영상·raw/heldout 결과도 읽지 않았다.

- `configs/simulation_workflows.json:660–670` → `run_m1_owncam_memory_v3.py:82–110,166–205` → `run_m1_owncam.py:78–86,169–172`를 직접 대조했다. 함수 내부 class import이므로 episode의 임시 class 교체가 constructor에 도달한다. `finally` 복원은 source에서 확인했으며 예외 실행·동시 호출 안전성을 시험한 것은 아니다.
- `M1OwnCamDeliveryOffV3`는 `M1OwnCamDeliveryMemV3`를 상속하고 `memory_look_enabled=False`만 자체 설정한다. V3의 부모는 `owncam_memory_delivery`의 provider adapter이며 frozen `m1_owncam_memory` 클래스와 구분했다. 동일 tracking/keepout/목표·조작·공통 safety가 남아 있어 전체 기억 제거 효과로 해석할 수 없다.
- `owncam_drive_mem_v3.py:14–51`의 policy 분기와 `owncam_safety_v3.py:76–172`의 MRO·현재 불확실성·새 fix/arrival·sweep/dispatch 검사 연결을 확인했다. 공통 메서드가 있다는 것은 물리 안전성·보정된 공분산·동일한 실제 입력 궤적의 증거가 아니다.
- 공식 CLI constructor는 `pose_source`/`landmark_provider`를 전달하지 않는다. V3 constructor → `memory_inputs:12–15` → `OwnCamPoseSourceV3`와 `TagLandmarkProvider` 기본값이므로 interim 라벨이 맞는다. 직접 `pose_source` 주입은 별도 API이며 guard wrapper → shared constructor의 own-camera 계약/객체 보유로 이어진다. landmark-only 주입과 혼동하지 않도록 원고가 `pose_source` 인자를 명시한 정정을 확인했다.
- `docs/design/2026-09-27-owncam-memory-v3.md:7–17,66`의 look-policy ablation·과거 reference 제외·interim provider 제한과 일치한다. 공식 #217 본문도 별도로 읽어 marker-free 최종 요구와 현재 caller의 차이를 확인했다. 같은 episode seed 전달은 source 수준이며 실제 paired 완료·통계적 독립성/CRN·시간/오판 효과는 검사하지 않았다.

[대상 원고](memory.md) · `memory-comparison-source-manifest.json` (Mac 전달본 증거)

## 최종 비교 문단 대조

두 matched 조건에 같은 `TIME_CONTRACT`를 선택하는 runner:101과 CLI:187–198의 split/episode/student 전달을 대조했다. 같은 prereg를 두 호출이 실제로 선택했는지 자동 교차 검사했다고 주장하지 않는 정밀화가 맞다. 같은 초기 seed·안전 구현은 이후 exposure/receipt/history/행동의 동일성을 보장하지 않으며, 고정 exposure의 고립된 직접 효과로 부르지 않는 한정도 수용한다. 실제 노출 변화·효과 크기는 미측정이다. 최종 원고 SHA256: `3be1b4dedf5e93c5fbf4c803617978c6173065ac42dc9ee202f8677be6765e37`.


## 마지막 tick의 사건 소비

**PASS — 실제 case/event 소비자의 좁은 음성 대조이며 새 버그 0개다.** `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`의 source 7개 SHA256을 Git object와 대조하고, 별도 임시 출력으로 fixture를 재실행했다. 8개 결과가 보존 JSON과 바이트 동일했다(SHA256 `16c26cb5c89d4524dff637d549f292e19f2048055d967fdc23fe9d5265dbdd25`). 구현·원본 golden은 수정하지 않았다.

- 실제 `pair_llm_case.py:224–260`은 final tick에도 frame 수집·link 갱신 뒤 outbox drain → `on_executor_event` → `step_to`를 수행하고, 그 뒤 break하므로 추가 runtime/arm control tick은 없다. fixture의 `.15` 발생 → `.2` 전달/step → finish 순서가 이 caller를 직접 지난다.
- 실제 executor `_emit`/`drain_events`, `PairLink`, 두 event consumer를 사용한다. 정상 done은 matching command history를 `queue_empty`, timeout은 `local_timeout`으로 바꾼다. 발생 시각을 reset origin으로 변환한 `_last_end=.15`와 전달 시각 `.2`는 origin 0 및 1.3 두 대조에서 구별된다.
- `no_event`는 history 유지·last_end 없음이다. `unrelated_job`은 해당 `_jobs` entry가 없어 history를 바꾸지 않는 대조다. **이벤트 전체를 거부하는 검사는 아니다:** 실제 PairTrial의 latest end 및 scheduler trigger/available은 이 경우에도 갱신한다. 알려지지 않은 job의 물리적 생성 가능성이나 장애를 입증한 것은 아니다.
- Backend·runtime job 생성/종료·clock·scheduler·trial finalizer는 명시적 collaborators다. 실제 scheduler event ordering, horizon 신규 HTTP 억제, pending work 전체 계산이나 물리 job 종료를 재현했다고 볼 수 없다. 특히 pending_work_count는 fixture 자체 계산이다.
- 실제 metric writer는 이 fixture에 trajectory가 없을 때 `NO_TRAJECTORY`, `success=false`, `COLLECTED_UNQUALIFIED`를 보존한다. 절차 수집 완료를 물리 성공·등록된 실험의 적격 결과로 승격하지 않는다. Frame bytes도 authored placeholder이며 이미지 추론은 없다.

표준 Python과 read-only Git source retrieval만 사용했다. 모델/physics/render/실험 데이터·heldout outcome·실제 네트워크 호출은 없었다. 이 검토는 이전 scheduler horizon 감사의 재실행이나 새 성능 증거로 세지 않는다.

`final-tick-repro.py` (Mac 전달본 증거) · `final-tick-result.json` (Mac 전달본 증거) · `final-tick-independent-result.json` (Mac 전달본 증거)

## 최종 원고·집계표 확인

최종 fixture는 unrelated job ID를 emitter 호출 **이전** authored job에 설정한다. 최초 QA 뒤 이 한 줄을 정밀화한 script SHA256 `e54fa24aec7c03b1b0c0f4911a929a4ce63b5af1a70af4756bf607a0a1a05ae6`를 별도 임시 출력으로 다시 실행했고 기존 golden과 byte 동일함을 확인했다. 추가 시나리오나 scheduler 검증은 없다.

현재 원고의 늦은 메시지 표는 source-only로 별도 확인했다. Pair relay가 기록한 accepted receipt/언어 행, Transport.sent_count, OfflineTrial의 scheduler delivery 수집, 최종 trial_metrics의 식을 대조했다. 최종 `messages.sent`는 접수 수+rejection 수이고 `messages.accepted`는 delivery edges를 **message_id로 묶은 메시지 행 수**라 edge 개수와도 다르다. 언어 분모는 relay-accepted 행이며 gate=false다. 접수·전달·상대 모델 입력에 포함됨을 같은 사건으로 보지 않는 해석이 맞다. 이 표는 실제 late-message 재현이나 수치효과 측정이 아니다. 추가 protocol/offline source를 포함한 최종 manifest 9개 hash도 Git object와 일치했다.

[최종 원고](case.md) · `final-boundary-source-manifest.json` (Mac 전달본 증거)


