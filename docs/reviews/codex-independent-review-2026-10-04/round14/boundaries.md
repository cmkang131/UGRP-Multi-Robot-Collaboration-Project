# 14차 경계 요약 — 서로 다른 검사를 하나로 읽지 않기

이번 세 영역에서 새 구현 결함을 확정하지 않았다. current pair의 원인을 단정하기 전에 어떤 검사가 실제 수행됐는지 좁힌다. 상세 원고·script·golden·독립 QA는 Mac의 `round14/evidence`에 보존했다. 공통 source는 #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`이며 approach 읽기는 코드가 같은6727751 snapshot을 사용했다.

## Checkpoint

**HIGH 중간 정지의8초 재관측은 공통 pose guard의 유예가 아니다.** endpoint는 controller보다 먼저 `before_control`을 실행하고 `wait_carry`는 reobserving 예외 목록에 없다. fresh/initialized/finite pose, gate history와 loaded70mm/3° HIGH 조건에서 먼저 `POSE_UNCERTAIN`이 될 수 있다. 그 단계를 통과해도 checkpoint의 post-stop fix·50mm·최소1.2초 조건은 별도다.

14개 endpoint 경우와4개 controller-only 대조를 독립 재실행했다. no/pre/equal-stop fix는 checkpoint timeout, stale/HIGH/uncertain gate는 먼저 pose guard 종료, edge unavailable은 marker 해제 뒤 별도 timeout이었다. 정상 post-stop fix가 다음 carry barrier로 위임되는 것은 새 두 로봇 GO나 임무 성공이 아니다.

fixture는0.1초 polling이며 실제 host는0.05초로 공통 guard를 더 자주 검사한다. 특정 abort 시각을 보편적인 대기시간으로 쓰지 않는다. frame/lease/no-fix report와 **beam_grasp_confirmed=True**는 선언한 collaborator이며 실제 grip receipt/segment 정합성이나 loaded geometry 전체를 실행한 것이 아니다. 공개92.2초 실패가 checkpoint phase였다고 가정하지 않는다.

근거: [checkpoint handler](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/zone_pair_highpose_runtime.py#L254-L313), [endpoint 순서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/zone_pair_executor.py#L342-L399), [공통 guard](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/zone_pair_guards.py#L619-L670). 상세: `high-checkpoint-control-boundary.md`, `checkpoint-guard-repro.py`.

## Vision

**예측 row score·detector evidence·PF update/fix는 다른 단계다.** current OpenCV wrapper는 unique finite bottom 후보를 통과시킨 뒤 같은 후보의 top을 추가하므로 top-only observation을 만들지 않는다. 반면 ranker의 geometry heuristic은 유효 predicted bottom/top을 각각 센다.

현재 camera/static map의 authored3pose×7pan에서 top-only credit5열을 뺀 진단 대조는 top3를 바꾸지 않았다. 실제 NumPy band detector의 authored grayscale4배열에서는 visible/top-clipped bottom은 보존하고 bottom-clipped/flat 후보는0이었다. 이는 전체 OpenCV undistortion/HSV/JPEG pipeline·실제 오탐률·다음 view의 정보량을 검증한 결과가 아니다. beam ROI의 과거 finding과도 다른 detector다.

근거: [관측 wrapper](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/opencv_wall_observation.py#L26-L60), [proposal score](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/vision_pose_source_p03.py#L163-L177). 상세: `opencv-observation-boundary.md`, `opencv-ranker-boundary-repro.py`, `opencv-band-censoring-repro.py`.

## Approach

**pursuit waypoint 생략만으로 현재 wall motion이 무검사라고 할 수 없다.** 실제 pair 접근은 generic goto의 직접 발행과 달리 command buffer를 마지막 `PairCommandGuard.check`에 통과시킨다. arrival도 position/heading 뒤 stop-and-look, gate와 최근 fix, 이후 barrier가 필요하다. owning pose가 처리한 frame을 driver가 다시 measurement update한다는 연결도 찾지 못했다.

planner는 beam·partner keepout을 추가할 수 있지만 최종 geometry guard의 static wall 집합은 동일하지 않다. 따라서 wall veto가 모든 추가 keepout의 연속 pursuit를 입증하지도 않는다. 현재 지원 지도/actual route의 구체 위반 증인이 없으므로 이 부분은 미해결 범위로 남긴다. 기존 source-only 검토이며 trajectory·물리 성공을 실행하지 않았다.

근거: [pair executor/factory](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6727751b49ce11fb62234bb97274137f22850765/harness/zone_pair_executor.py), [approach](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6727751b49ce11fb62234bb97274137f22850765/harness/pair_owncam_approach.py), [final guard](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6727751b49ce11fb62234bb97274137f22850765/harness/zone_pair_guards.py). 상세: `approach-pursuit-source-boundary.md`, `approach-pursuit-source-manifest.json`, 보조 `planner-caller-source-boundary.md`.

[현재 판단 순서](decision.md)와 [독립 검증 범위](validation.md)로 돌아갈 수 있다. 이 부정 결과로 이미 확인한12차 command/worker 결함이 해소됐다고 하지 않는다.
