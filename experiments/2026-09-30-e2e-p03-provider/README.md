# P03 — 무표식 provider와 재측위 상태 보존 계약

**독립 리뷰 후 수정:** 현재 구현과 재검증은 [REVIEW_FIXES.md](REVIEW_FIXES.md)를 따른다.
아래는 최초 구현·검증 당시의 기록이다. v6e에 고정된 공용 소스 변경은 철회하고
P03 전용 후보 파일과 별도 provider ID로 옮겼다. 기존 등록·봉인 bytes는 유지한다.
로컬 물리·렌더·추론은 실행하지 않으며, 정상 GitHub CI는 실행하고 확인한다.

상태: **DRAFT, 오프라인 계약 검사, 병합·봉인·실행 승인 없음.** Refs #216, #219, #223.
감사 기준은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`의 READINESS S02/S03(PR #298)이다.
작업 시작 HEAD와 fetch 당시 origin/main은 `d17ca4345affef8cf027e121cf1f3197b36c23e0`이었다.
배정 worktree `/Users/changmin/projects/ugrp-wt/e2e-p03-provider`, 브랜치 `codex/tagfree-provider-lifecycle`만 수정했다.
검증 소스 SHA·전체 파일 해시·JUnit 결과는 `verification.json`에 기록한다.

## 확인한 문제와 변경

변경 전 가짜 worker 반례 4개가 모두 실패했다.

| 반례 | 변경 전 | 변경 후 계약 |
|---|---|---|
| PF를 2초까지 예측한 뒤 0.8초 프레임 전달 | 현재 posterior의 가중치를 바꾸고 과거 fix로 표시 | PF clock 이전·중복 프레임은 worker 호출 없이 거절 |
| 1초 arm/profile이 대기 중인 1.05초 재측위 | 대기 명령까지 삭제 | scan 이전 프레임만 삭제, 자기 명령·profile은 순서대로 보존 |
| 프레임 전이라도 runtime 시작 후 prior 주입 | dock/GT 평균을 다시 주입할 수 있음 | 최초 prior 단회, command/profile/scan/clock 시작 뒤 거절 |
| DelayedPoseSource를 다시 감쌈 | 0.16초가 두 번 적용될 수 있음 | wrapper 중첩과 worker의 추가 SIM 부과 거절 |

`VisionPoseSource.begin_relocalization()`은 PF 객체·입자·가중치·scale·RNG·명령 clock·서보 이력을 보존한다.
이전 fix receipt와 `last_obs`만 무효화한다. 재측위 요청을 가상의 새 servo 명령으로 넣지 않는다.
실제 자기 명령은 기존 입력 경로로 계속 들어온다. legacy `loc.command`도 같은 provider 기록 경로를 쓴다.
prior에는 mean/std/source, 적용 SIM 시각과 setup-only 여부가 남는다.

fake worker에는 자기 BGR만 주며 관측은 고정된 protocol JSON이다. 신규 수명주기 검사는 peer frame/GT/world를
읽으면 실패하는 own-only 객체를 사용한다. 접근→정렬→grasp/lift→carry→lower/open의 **발행 명령**,
실제 `ProviderM2DoorStudent._queue_grasp()`의 p20 시작, pan 8장, regrasp 발행 명령을 같은 PF로 연결한다.
PF·분산의 초기화가 없고 command/servo clock이 이어지는지를 검사하며, 실제 로봇이 움직이거나 잡았다는 의미는 아니다.
stale/future/duplicate/누락 프레임·거절/실패 응답과 잘못된 worker seq/필수 키/GT 추가 키는 새 fix가 아니다.
worker 실패는 끝까지 fail-closed이며 close 뒤 새 입력·estimate 재사용을 차단한다.
StudyTeamHost 정상 종료·prior 누락·post-setup 실패에서 자신이 만든 모든 provider/worker를 닫는다.
확대 검사에서 prior 누락 시 미등록 worker의 close 누락을 확인했다. 기존 하단 close 정의가 새 정의를 덮은 것을
수정해 종료 메서드를 하나로 합쳤으며, executor 슬롯 대신 생성 직후 기록한 소유 목록으로 정리한다.

## 지연과 조합 pin

`configs/vision_loc_provider_p03.json`은 P03 전용 **미봉인 명세**다. 공용 `pose_providers.json`,
`model_artifacts.json`, 실행 bundle registry와 P01 장면/지도 파일은 편집하지 않았다.

- 기존 활성 모델: seg-v2 `348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9`, 13,071,401 B.
- 허용 조합: 기존 `vision_zero_tag_v1/v2`, v2 로봇, 문 1개 geometry_v2/동일 기하 VIS3 지도,
  기본 authored 렌더(별도 XML 변환 없음), walls_v3(0.40 m), 자기 RGB 640×480, 분할 480×360,
  VIS3 train sag/pan 및 M1 motion 보정. 카메라 mount는 여전히 provisional/unvalidated다.
- worker의 `sim_time_charge.charged=false`는 **추론 wall 시간 비례 비용 0**이다.
  wrapper가 camera-to-estimate 고정 0.16 SIM초를 정확히 한 번 적용한다. **실효값은 0.16 SIM초**다.
  capture/release/consumed 시각은 `pose_timing.jsonl`, prior/worker/lifecycle/지연은 새 `pose_provider.json`에 남긴다.
  raw provider 적용 지연 0과 외부 wrapper 적용 지연 0.16도 각각 명시한다.
- 지연 운송에서 별도 capture 시각을 받으면 receipt 시각으로 바꾸지 않는다. PF가 이미 지난 capture는 거절한다.
  예측만으로 last_fix_t를 갱신하지 않는다. bundle은 조합 파일·worker 설정·Release 명세와 보정 해시를 함께 기록한다.
- 로봇·렌더·카메라 pin 파일 bytes, 등록 보정 또는 model 해시가 다르면 실행 전에 거절한다.
  이 pin은 v3 또는 새 렌더의 정확도를 승인하지 않는다. 코디네이터가 새 조합과 번들을 별도로 등록해야 한다.

`C_mix_rgb`는 별도 **opt-in 준비 항목**이다. `runtime_selectable=false`,
`unavailable_pending_upload`, Release URL 없음, final calibration 미검증을 유지한다.
로컬 bytes `0e7a696e7100cc19d84149251456afedc1318ff4f7901b06bd9396590c651c9d`(13,071,657 B)를 확인했으나
모델을 로딩/실행하지 않았고 Release를 올리지 않았다. 기본 모델로 채택하지 않았다.
두 모델의 전체 파일 해시·크기는 `local-model-hashes.json`에 기록한다.

## 검증 범위와 기록

공용 pytest 잠금은 `scripts.run_ci_tests.run_locked()`를 그대로 사용한다. 다른 작업의 살아 있는 잠금은
해제하지 않았으며, 대기 동안 pytest를 생성하지 않았다. 테스트 실행은 별도 guard로 MuJoCo/torch/torchvision
import, network connect, real worker 생성과 schematic render를 금지했다.
`test_zone_pair_tag_boundary_matrix.py`의 schematic 생성 검사 4개는 렌더 금지 범위에 따라 제외한다.
읽어 본 기존 `test_zone_study_pair_delay.py`의 5개 검사와 기존 host-worker-crash 검사 1개는
저장 RGB의 실제 태그 검출을 수행하므로 제외했다. 태그 검출도 guard로 차단한다.
fake worker subprocess의 pipe/timeout/EOF/close 검사는 허용 범위이며 실제 추론이 아니다.

같은 안전 경계로 재현하는 명령(잠금 점유 시 pytest 없이 종료 코드 3):

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p03-provider/offline_checks.py --junitxml=<새 로컬 출력 경로>
```

최종 결과: **277 passed, 10 deselected, 85.59초**. 수정 후 실패 0개다.
검증 코드 SHA `9cf4322d09eed11e10252601b5c78eabdbb7c727`, 파일 해시와 환경·전체 실패 기록은
`verification.json`을 따른다. 최종 번들 미리보기 해시
`347ad3a65095de31ea27be365649acab905d799025523e5f2cfe124990f3745e`는 미봉인/실행 불가 기록이다.
원본 로컬 경로:
`/Users/changmin/projects/ugrp/outputs/e2e-p03-provider-contract-20260930-194957/`.
새 학습/실험/평가 코호트가 아니므로 TensorBoard 변환·서버·화면은 만들지 않았다.
물리·시뮬레이션·렌더·학습·비전 추론·LLM 호출은 전부 0회다. Drive 작업도 없다.
기존 raw·모델·번들 bytes를 덮거나 삭제하지 않았다. 로컬 기록은 원격 raw 백업을 뜻하지 않는다.

## 코디네이터에게 남기는 검사

1. **실제 이전 leg를 거친 문 앞·문 뒤·목적지 전 3체크포인트 × 최대 120 SIM초**:
   lower→open→p20 8장→새 fix→re-align→grasp→lift까지 같은 provider/PF를 이어 실행한다.
   각 단계 미도달도 분모에 포함한다. scan 전후 last_scan_t·입자 분포/σ·명령/servo 이력·capture/release/consumed 시각,
   eval-only 오차·빔 이동·재파지 결과를 남긴다. GT staging으로 옮긴 시작은 별도 진단으로 센다.
2. 활성 모델과 선택 후보 Release를 버전별로 배포할 담당자가 실제 다운로드→archive 및 전체 파일 SHA-256→
   모델 로딩 검증을 수행한다. P03의 로컬 bytes 해시는 다운로드·로딩 검증을 대신하지 않는다.
   C_mix_rgb의 새 worker/loader/config identity·배포 명세·opt-in 승인은 별도다.
3. P01 최종 로봇/렌더/지도와 카메라 mount·sag/pan·명령 기하·motion 보정을 같은 조합으로 검증한다.
   현재 v2 보정을 v3 또는 밝은 바닥에 자동 승계하지 않는다. 최종 모델 보정과 큰 오차 belief에서의 회복도 남아 있다.

B1(#279)의 p90 3.7 cm는 정지 화면·GT 근처에서 **새 PF**를 시작한 측정이다.
P03의 runtime은 이전 leg의 belief를 유지하며 GT reseed/oracle 분할을 넣지 않는다.
따라서 이번 계약 통과를 실제 재측위 정확도·재파지 성공이나 #216 완료로 해석하지 않는다.

## 참고 자료

- [READINESS S02/S03, PR #298](https://github.com/kcm0127-dotcom/ugrp/pull/298)
- [B1 정지 관측 측정](../2026-09-29-carry-relocalization-b1/README.md), [밝은 바닥 후보 #282](../2026-09-29-seg-lightfloor/README.md)
- [P03 조합 명세](../../configs/vision_loc_provider_p03.json), [기존 모델 배포 지침](../../docs/model_artifacts.md)
- [검증·잠금 지침](../../CONTRIBUTING.md), [실행 버전 관리](../../docs/execution_versioning.md)
