# R25 · REAL trace 분석이 서로 다른 호스트의 wall clock을 비교한다

**조건부 P2 — Pi 시계가 호출 호스트보다 빠르고 그 차이가 종료·회수 여유를 넘으면, 저장된 실패 직전 증거가 분석 요약에서 빠질 수 있다.** main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 원래 recorder·local span writer·분석기를 작성한 가짜 시각과 기록으로 연결해 확인했다. 원본 event는 그대로 남고 실패 상태도 유지되지만, 마지막 관측/명령 선택과 그에 따른 RCA 분류가 달라진다. 실제 장비의 clock offset·빈도·과거 분석 결과는 조사하지 않았다.

이 경로는 #214가 참조하는 REAL 플랫폼 진단 도구이며, 현재 HIGH SIM 제어/평가와 다르다. 하드웨어·카메라·모델·원격 SSH/복사·실제 actuator·기존 trace·이미지 원본은 실행하거나 열지 않았다. R3의 stop/servo settle과 R17 HIGH trace 발견을 다시 세지 않는다.

핵심 source는 [Pi event writer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/red_block/recorder.py#L75-L113), [host 실행·회수·종료 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/red_block/deploy.py#L529-L585), [분석 cutoff](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/trace_analysis.py#L146-L167)다. 16개 파일의 hash와 구간별 읽기/실행 범위는 `real-trace-source-manifest.json` (Mac 전달본 증거)에 남겼다.

## 지원 caller와 clock domain

| 실제 source 경계 | 확인한 동작 |
|---|---|
| `scripts/red_block/task_runner.py:225–243` → `deploy.deploy_and_run` | 비-Pi CLI가 원격 배포 wrapper를 호출한다. 일반 harness action도 `scripts/robot_actions._run_skill_process`에서 해당 skill process를 시작한다. 이 호출 연쇄는 source로만 읽었고 원격 실행하지 않았다. |
| `deploy.py:93–101,501–527` → Pi recorder | active run ID가 없으면 standalone run을 만들며, 원격 명령에 trace run/span/dir와 enable 설정을 전달한다. `UGRP_REAL_TRACE_ALL_FRAMES` 기본 1이다. 따라서 표준 harness CLI가 최상위 `execution_trace.create_run`을 자동 호출하지 않는다고 해서 skill trace 전체가 없다고 판단하면 틀린다. |
| `recorder.event:75–113` | 원격 Pi의 `time.time()`을 `wall_time_s`에 기록하고 같은 프로세스의 `monotonic_s`, `event_seq`도 남긴다. 같은 API 이름은 같은 호스트의 clock이라는 뜻이 아니다. |
| `deploy_and_run:529–548,578–585` → `_write_local_trace_result` | 호출 호스트에서 실행 전/후의 `time.time()`을 취하고 원격 trace를 회수한 **뒤** 또 `time.time()`을 `ended_wall_s`로 저장한다. 이는 Pi 실패 발생 시각이 아니라 실패 span의 host wrapper 종료 시각이다. |
| `scripts/analyze_real_trace.py:28–36` → `analyze_run` | 문서에 남은 수동 CLI가 선택 run을 분석한다. `trace_analysis.py:150,158–167`은 host의 `ended_wall_s`를 cutoff로 삼아 Pi `wall_time_s <= cutoff`인 detection/pose/command/frame만 고른다. 이 선택에서 `monotonic_s`와 `event_seq`는 쓰지 않는다. |

[REAL trace 문서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/real_trace_system.md)는 실패 직전 관측·명령과 visible→lost 전이를 진단 증거로 설명한다. 선정한 recorder/deploy/analysis/execution_trace와 실물 문서·네트워크 런북에서는 host/Pi epoch 동기화, offset 보정 또는 허용 오차를 이 비교의 전제로 검사하는 계약을 찾지 못했다. 저장소 전체나 현장 NTP 설정이 없다는 주장은 아니다.

cutoff는 실패 이후의 사건을 제외하려는 선택으로 읽을 수 있으나, inspected source에 같은 clock domain임을 보장하는 변환은 없다. 특히 이미 회수된 같은 span의 기록도 Pi epoch가 충분히 앞서면 이 조건에서 제외된다. 복사 시간이 충분히 길거나 offset이 작으면 같은 누락이 나타나지 않을 수 있다. 실제로 `+5 s`라는 숫자 자체가 항상 문제라는 뜻은 아니다.

## 작성한 기록을 원래 writer로 저장한 반례

`real-trace-clock-repro.py` (Mac 전달본 증거)는 세 Git blob의 hash를 확인한 뒤 원래 AST 함수 body를 실행한다. `recorder.event`, `record_detection`, `record_pose`, `_write_local_trace_result`와 전체 원래 `analyze_run`을 사용한다. camera frame/servo/stop의 의미 값은 리뷰어가 작성한 metadata다. detector·camera capture·JPEG encoding·actuator 함수·배포 및 복사 함수는 실행하지 않았다. run/span 파일은 새 임시 디렉터리에 작성하고 삭제한다.

논리적 사건은 100.0–102.2초의 frame → visible detection → commanded pose → servo command → frame → lost detection → stop 7개다. host 실행 종료는 103.2초, 복사 여유는 0.2초, host 종료 cutoff는 103.4초다. 이 조건에서 Pi wall time만 바꾸었다. `event_seq`, Pi monotonic 값과 나머지 event 내용의 hash는 네 경우 모두 같다. JPEG 경로는 작성한 문자열일 뿐 실제 이미지 bytes를 만들거나 검증하지 않았다.

| authored clock 조건 | 저장된 event | 마지막 frame / visible→lost | 선택된 RCA | 실행 실패 상태 |
|---|---:|---|---|---|
| host/Pi offset 0 | 7 | 유지 | `TARGET_LOST_AFTER_ARM_POSE_CHANGE` | `FAILED` |
| Pi −5초 | 7 | 유지 | 같은 분류 | `FAILED` |
| Pi +5초, 위 host 종료·회수 여유 초과 | 7 | 누락 | `UNCLASSIFIED_FAILURE` | `FAILED` |
| host/Pi epoch를 함께 +50초 | 7 | 유지 | 같은 분류 | `FAILED` |

원본 JSONL 7개가 지워지거나 archive에서 사라지는 반례가 아니다. 분석기의 `_last`와 detection/frame 목록에서 필터링돼 summary의 마지막 입력·명령·관측 전이가 비는 반례다. 이 authored generic 실패 사유에서는 RCA도 변했지만, 명시적 stderr 코드가 먼저 분류되는 모든 실패가 똑같이 바뀐다고 주장하지 않는다. servo 뒤 영상 변화라는 분류 역시 물리적 가림/하중 원인의 실측을 뜻하지 않는다.

4개 조건 assertion이 통과했고 `real-trace-clock-result.json` (Mac 전달본 증거) SHA256은 `de5a9fa25c63c2cfba29e96f30c2f1f8ecfa74b5b9f44378d591047ee30f68c0`이다. 직접 실행 범위는 위 세 writer/consumer 소스이며 전체 REAL CLI·process·하드웨어 실행을 재현한 것은 아니다.

## 최소 수정 방향과 회귀 조건

현재 source는 변경하지 않았다. 다음 중 하나처럼 **시간 관계의 근거를 보존하는 방향**이 필요하다.

- 같은 원격 process/domain의 종료 marker와 event 순서/monotonic 경계를 이용하거나, host↔Pi clock mapping과 그 오차 범위를 명시한다. 서로 다른 호스트의 monotonic 값을 그대로 비교하는 대체는 정당화되지 않는다.
- mapping이 없으면 이미 저장된 span 증거를 summary에서 조용히 배제하지 말고 시간 관계를 판정할 수 없다고 표시한다. 이는 진단 증거를 보존하자는 뜻이며 제어 guard를 완화하자는 뜻이 아니다.

회귀는 같은 논리적 기록·event sequence에서 host/Pi의 0/±offset 및 공통 epoch 이동을 적용해, 지원한 시간 계약 안에서는 마지막 증거가 같거나 명시적 time-unavailable 상태로 남는지 확인하면 된다. mapping의 불확실성 밖인 경우를 확정된 인과 순서로 표시하지 않아야 한다. 기존 실패 status·원본 기록 보존도 함께 유지해야 한다. 실제 NTP 변경·장비 재실행·전체 과거 분석 재처리는 이 검토에 포함하지 않는다.

## 보존 API와 센서 의미의 범위

`harness.web.py`에는 request 단위 `create_run`/activate/finish 연결이 남아 있지만, 현재 `harness.cli.main`에는 그 자동 lifecycle이 없다. 브라우저 퇴역 문서는 GUI/`--chat`/런처 제거와 내부 HTTP API 보존을 구분한다. 따라서 보존 web API 전체를 무지원이라고 하거나 옛 dashboard 설명을 현재 CLI 기본 기능이라고 읽지 않는다. 이번 결함은 별도 standalone skill trace를 분석하는 CLI에도 적용되는 clock 선택 문제다.

원래 [문서 92–98행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/real_trace_system.md#L92-L98)와 분석기 limitations처럼 commanded PWM은 measured joint feedback이 아니고, chassis command/timing은 실측 이동 거리도 아니다. `robot.py`의 command/stop 기록은 시도 경계이며 `chassis_command_complete`는 소프트웨어 motion 함수 반환 뒤 기록이다. 기록 기반 재구성을 물리 피드백 재생·현실 성공 검증으로 바꾸지 않는다.
