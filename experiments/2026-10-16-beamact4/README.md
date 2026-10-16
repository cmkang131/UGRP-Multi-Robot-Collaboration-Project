# beamact4 — 학습 READY·완료 뒤 복구 후보와 교사 인수 명세

상태: **코드·명세 준비 / 실행 NOT_READY**. `origin/codex/beamact3`의 `14f9c135de2a008ef1224d503c7cdbda6ae98f68`에서 `codex/beamact4`를 만들었다. PR #545 위에 쌓는 draft다. 이번 라운드는 학생 코드와 교사 명세만이며 새 시연 기록·학습·모델 재추론·물리·렌더·GCP·GUI 실행은 모두 0이다. 기존 미추적 C1/beamdiag 자료와 `codex/beamact3c` 커밋은 보존했다.

## 먼저 확인한 거부 분포

수정 전에 조정자 확인 beamdiag의 [원본 거부 표](prior-rejection-table.json)를 복사하고, [입력 출처·해시와 TRAIN 백분위](beamdiag-reference.json)를 기록했다. [거부 분포·누적 퍼널·후속 관문 계획](rejection_table.md)을 이번 계획의 기준으로 쓴다. A/B는 합산하지 않는다.

가장 큰 입구 문제는 A/B 각각 초기 40로봇 중 30개가 배정 끝 0.8m 밖인 반면 TRAIN은 54/60,023행(0.090%), 최대 0.84855m였다는 점이다. 입구와 실제 반대 역할 시연은 교사 소유 작업과 연결돼 이번에는 명세만 작성했다. 학생 쪽에서는 정렬 전 GO 각 20/20, 한쪽 done 고착 A11/20·B9/20에 대응하는 후보를 추가했다. 이 수치는 기존 beamdiag 판정이며 이번 코드의 새 측정 결과가 아니다.

## 변경

|토글|기본|켜면 달라지는 동작|
|---|---|---|
|`beamact4_stage_v1`|off|같은 ACT decoder 특징에서 접근·정렬·READY·실행·복구·완료 6분류를 출력한다. PWM 감소는 READY를 만들지 않는다.|
|`beamact4_done_recovery_v1`|off|done 다음 제어 틱에 이전 청크를 버리고 새로 추론한다. done을 철회할 수 있고 현재 완료 요청이 철회되면 종료 대기 시각도 지운다.|
|`beamact4_handoff_v1`|명세만, 미구현|TRAIN p99와 측정된 상대 위치·각도 추정 오차 예산으로 지도→ACT 입구를 정의한다. [인수 명세](handoff-spec.md).|

학습 READY는 `harness/beamact4_policy.py`의 별도 head와 CE 학습 함수·엄격한 저장/로더 후보다. 14차원 행동/CVAE 표적과 기존 wheel CE·completion BCE는 유지한다. stage 표적은 forward 전에 batch에서 제거한다. 학생 입력은 기존 자기 RGB 이력·자기 발행 명령 이력·고정 작업/배정 끝 번호표뿐이다. pan/팔/PWM 문맥을 보존하며 위치·관절·접촉·평가 결과는 입력하지 않는다. 기존 A/B 체크포인트에는 이 head가 없으므로 READY 토글을 켜서 재사용할 수 없다.

`StudentBarrier`는 학습 `ready` 클래스일 때만 첫 READY를 보낸다. `approach/alignment/recover`는 READY를 철회하고 지역 started를 해제한다. 이 구간에서 닫기 제안이 나오거나 시작 허가 없이 `execute/complete`를 제안하면 기존 WAIT(이전 PWM 유지·휠 정지)만 발행하고 다음 틱에 다시 추론한다. 이는 PWM을 학습 READY의 대용으로 쓰는 경로가 아니라, 기존 GO 전 닫기 금지를 유지하는 형식 거부다. 어떤 정렬·재파지 동작도 코드로 생성하지 않는다.

GO/ACK 형식·시한·시작 지연은 기존 고정 `GraspStartSync`를 그대로 쓴다. READY 철회 때 그 객체를 새로 만들어 이전 START/ACK가 새 파지를 허가하지 않게 한다. 상대에게는 기존 boolean READY만 전달하며 학습 단계·상대 좌표를 보내는 옆길은 없다. 대기/거부 때 미발행 청크는 폐기하고 실제 WAIT가 들어간 자기 명령 이력으로 재추론한다. 후보에서는 두 로봇의 이번 단계 출력을 얻은 뒤 READY 메시지를 처리한다. off에서는 기존 로봇별 촬영→발행 순서와 흡수 동작을 보존했다.

작업 완료 요청과 공동 들기/물리 성공은 계속 분리한다. 기존 3.1 SIM초 완료 안정 대기와 60 SIM초 cap은 바꾸지 않았다. 시간 상한 종료는 기존처럼 `cap_end`다. 기존 실패/감독 중단 직전 10 SIM초 자기 카메라 10Hz 기록 고리 버퍼도 유지한다. 새 탐색/계획 예산이나 wall 시간 기반 판정은 추가하지 않았다.

교사 코드는 warp8 소유 `codex/warp6`이므로 수정하지 않았다. [단계 표적·실제 역할 반대·원거리/복구 시연 명세](teacher-spec.md)는 warp8 관문 종료 뒤 조정자가 배정할 작업이다. 공용 `scripts/warp_act_*.py`, 장면, 입력 계약, 기존 beamact3 학습 어댑터도 변경하지 않았다. 실행 번들/모델 자산은 이번에 만들지 않았다.

## 확인 결과

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_beamact2.py tests/test_beamact4.py tests/test_beamact4_policy.py
```

현재 **15 passed / 1 skipped**. 기존 barrier·원본 명령 재생 9개와 새 후보 시험 6개가 통과했다. 새 시험은 1PWM 감소의 READY 오인 방지, 열린 집게 제안의 학습 READY, 철회 후 새 GO/ACK·시작 지연, done 다음 틱의 새 추론, 모의 70행 명령/프로토콜 재생과 PWM·단계 로그 변조 탐지, 숨은 표적/출력 필드 거부를 확인한다. 선택적인 Linux 합성 head/loss gradient 시험은 Mac에서 건너뛰었다. 실제 체크포인트 저장/재로딩·학습 손실/기울기·자기 RGB 인식 정확도·공급자·물리 성공은 검증하지 않았다.

새 두 시험 파일은 CI 목록 끝에 추가만 했다. [토글 중복 검색](toggle-collision-check.json)은 main/warp-act와 codex/claude 원격 241 refs의 harness/scripts/configs/tests에서 이름 충돌 0을 확인했다. 긴 과거 실험 blob까지 포함한 첫 검색은 일부 SIGTERM으로 미완료였으므로 중복 없음의 범위에 포함하지 않는다. `git diff --check`와 변경 학생 모듈 6개 AST 파싱을 확인했다. [검증 원장](verification.json).

## 남은 관문

새 head의 학습 모델이 없고 자기 위치/대상 상대 오차 예산도 미측정이다. 따라서 현재 학생 입구 적합도·READY 오탐률·복구율·실제 반대 역할 수행·들기 개선을 주장하지 않는다. 후속은 교사 배정 → 같은 호스트/머신의 새 교사 ≥95%, 최소40회 → 승인된 시연 기록/오프라인 head 검증 → 새 입구·모델·소스를 등록한 학생 실행 순서다. 이번 [계획 JSON](plan.json)은 `ready=false`, 실행/학습 권한 없음이며 `rejection_table` 절대경로를 포함한다. 기존 A/B 20은 이미 본 진단 세트로, 새 확증 성공률의 분모로 재사용하지 않는다.

영상 원인은 beamdiag의 기존 40회×6시각×2카메라 검토와 대표 5개 전체 2Hz/마지막10초 10Hz 검토 기록을 인용했다. 이번 라운드에서 새 영상을 재생하거나 새 실패 원인을 판정하지 않았다. 원본/미디어 경로와 SHA는 `beamdiag-reference.json`과 기존 research/beamdiag-evidence/에 연결돼 있다.

## 참고와 확인 범위

- [ACT 원 논문 §IV](https://arxiv.org/html/2304.13705v1): 행동 청크와 시각 폐루프의 근거를 직접 읽었다. 학습 READY head와 이 환경의 성공을 검증한 논문은 아니다.
- [Ross et al., DAgger, 2011](https://proceedings.mlr.press/v15/ross11a.html): 정책이 만드는 관측 분포에서 시연을 추가하는 근거를 직접 읽었다. 본 후보는 이번에 DAgger 반복을 수행하지 않았다.
- 고정 LeRobot SHA `89236ea0f4f81a81ca566081e20dd1ff5f823cbe` 원격 원문은 이번 웹 열람에서 실패했다. 저장소 `harness/beamact3.py`와 `grasp_act_policy.py`의 기존 공유 decoder/one-forward hook을 사용했으며 원격 최신 구현을 새로 확인했다고 주장하지 않는다. unit CE는 beamact3의 표준 valid-horizon 평균을 따른 제안이고 검증/보류 성능으로 가중치나 confidence 상수를 선택하지 않았다.

기록은 로컬 프로젝트와 GitHub에 보존한다. VM 접근·시작·정지·lease 생성, 원본 삭제, 모델 키 전달은 모두 0이다.
