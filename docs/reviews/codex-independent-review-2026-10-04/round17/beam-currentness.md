# R17 · R8 beam ROI 경계의 66ff 적용 범위

**R8의 조건부 beam-edge crop finding은 `66ff0978a817caa949d2d738b51d7ae89dd17e71`에서도 source상 해소되지 않았다.** 이는 기존 finding의 currentness 확인이며 새 결함이나 현재 실행에서의 발생 증거가 아니다. 새 RGB/PF/물리 실행은 하지 않았다.

원본 R8 [기하 검토](../round8/geometry.md)와 재현은 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`의 `own_beam_edge.py`를 사용했다. 그 파일은 최신 66ff까지 **바이트 동일**하다. ROI `[40:300]`으로 잘린 색띠가 row 300 이후에도 계속되지만 마지막 검사행 299를 lower edge로 돌려주는 함수와, 이 선으로 reference/available을 갱신하는 tracker가 그대로 남아 있다. 정상 하단이 정확히 299에서 끝나고 row 300은 background인 대조도 기존 R8 범위에 포함된다.

그 뒤 추가된 `zone_pair_highpose_edge.robust_edge_line`은 **공유 OLS가 수락하면 그 결과를 변경 없이 반환**한다(`shared = be.edge_line(rgb)` 뒤 즉시 `EdgeLine(shared, FIT_SHARED)`). R8 반례는 90/90열이 완벽한 수평선으로 공유 OLS에 수락되므로 consensus fallback에 진입하지 않는다. fallback 역시 같은 ROI와 `_first_run_end`를 사용하지만, 이번 전이 증명에는 그 추가 사실조차 필요하지 않다. robust edge 모듈 및 HIGH provider는 검토한 de03와 66ff 사이에 바이트 변경도 없다.

현재 caller 연결은 다음과 같다.

| 현재 source 경계 | 유지된 의미 |
| --- | --- |
| `vision_pose_source_highpose.py:80,94–107` | 실제 HIGH provider가 `HighBeamEdgeTracker`를 구성한다. failure 없음·non-late/non-duplicate frame 조건 아래, loaded·settled·issued HIGH일 때 tracker를 enable하고 availability를 갱신한다. |
| `zone_pair_highpose_edge.py:114–151` | `BeamEdgeTracker.observe`의 원본 code object에 기록용 edge 함수를 bind한다. 기록 함수는 `robust_edge_line`의 답을 그대로 반환한다. |
| `zone_pair_highpose_runtime.py:257–290` | high_ready 및 해당되는 checkpoint freshness 확인 뒤 edge.available를 검사한다. False일 때 reference pending/timeout, True일 때 부모 carry 검사를 계속한다. available 하나가 전체 motion을 승인하는 것은 아니다. |
| `owncam_carry_v6e.py:258–276` | loaded 상태의 edge.available는 yaw fallback 등급 선택에도 쓰인다. 이 파일도 R8와 66ff가 같다. 실제 uncertainty 변화량은 현재 보정과 다른 상태에 달려 있으며 이번에 측정하지 않았다. |

HIGH의 `grip_monitor`는 계속 기록 전용이다. 위 주장은 grip monitor를 필수 gate로 바꾸자는 요구가 아니라 **상대 yaw용 edge reference의 유효성**에 관한 기존 범위다. R14의 bottom-clipped wall band가 no-candidate였던 결과는 별도 OpenCV wall detector 경로이므로 이 beam-edge finding을 해결하거나 반박하는 결과로 합치지 않는다.

현재 실행의 HIGH 영상에서 ROI crop이 실제 발생하는지, row 299 허위 reference가 실제 carry 실패 또는 성공에 영향을 주었는지는 여전히 미확인이다. 공개 OLS 소수열 outlier 문제와, R10의 inlier span에 따른 angular precision 진단도 이 조건부 crop 문제와 구별한다. 유지할 수용 기준은 관측된 run 종료와 ROI가 잘라낸 run의 구별이며, row 299 자체를 무조건 제거하면 기존 정상 대조를 잃는다.

`beam-roi-currentness-source-manifest.json` (Mac 전달본 증거)는 세 pin·다섯 관련 파일의 SHA-256과 원본에 아직 없던 robust 모듈을 기록한다. 이 currentness 결론은 공유 모듈의 바이트 동일성 + 새 wrapper의 accepted-result 보존 + 현재 source caller를 조합한 증명이며, 전체 provider가 합성 RGB를 끝까지 처리한 신규 통합 재현이라고 표현하지 않는다. R8 산출물은 변경하지 않았다.
