# HIGH edge 수정의 최소 인수 기준

대상: PR363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`의 `own_beam_edge.py`. 구현하지 않은 **수정안 검토 기준**이다. 기존 `geometry-repro.py`의 합성 oracle를 활용하며 새 물리·raw·모델 실행을 요구하거나 수행한 문서가 아니다. 연구 메모의 진단 가설과 구분해, 무엇이 수정 완료를 입증할지에 집중한다.

## 먼저 보존할 계약

[원본 45–88행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L45-L88)은 첫 40px 이상 연속 색 run의 **관측된 하단**을 후보로 사용한다. crop으로 잘린 run은 그 좌표의 물리 edge 관측이 아니다. 이후 inlier 조건은 `n ≥ max(20, .6×90×.5, .6×candidate_count)`, residual tolerance 4px, refit RMS≤2.5px다. 후보가 90개면 54열, 후보가 적어도 최소 27열이 필요하다. crop 수정의 근거만으로 이 값들을 낮추거나 후보 분모를 조용히 바꾸지 않는다.

설명 가능한 최소 수정 흐름은 **run 추출 → 관측된 끝/잘린 끝 구분 → 같은 물리 경계 후보 → robust fit → 기존 support/residual 조건 → reference와 현재성**이다. 기존 OLS seed만 robust estimator로 교체하면 ROI false edge는 그대로 남는다. 반대로 crop 끝만 거르면 공개된 OLS minority-leverage 문제는 남는다.

## 작은 회귀 판정표

| 합성 oracle | 필요한 판정 | 이 조건이 막는 성급한 수정 |
|---|---|---|
| 정상 band, slope=.03, centre200 | 원본 수준으로 기울기와 높이를 회복 | 모든 경계 후보를 과도하게 제거하여 `None`만 반환하는 수정 |
| 실제 하단 y299, y300 background | **관측된 하단으로 인정 가능** | `end == ROW_HI-1`이면 무조건 버리는 수정 |
| 실제 하단 y300 또는 centre340, y300 foreground | y299를 실제 하단 sample로 계수하지 않음. 고정 ROI 방침이면 missing/censored; 범위를 명시적으로 확장한다면 새 범위에서 실제 transition을 확인 | 배열 끝을 물리 edge로 변환하는 현 오류 |
| centre340에서 slope+.04와−.04 | crop한 y299를 근거로 둘 다 같은 유효 reference라고 승인하지 않음 | 90/90 fake consensus를 좋은 robust fit으로 오인 |
| 84열 실제 수평선 + 끝 6열의 80px 별도 경계 | 지배적인 같은 edge로 취급하기로 정한 후보안이면 기존 54열·4px·2.5px 조건을 유지하면서 회복. 다른 실제 객체/경계와의 identity가 불명확하면 별도 ambiguity 처리 | 성공시키려고 support나 residual 기준을 낮추는 수정 |
| 색띠 없음; 또는 경쟁하는 두 선에 충분한 합의 없음 | 새로운 reference/accepted-frame 시각이 생기지 않음. 기존 reference는 원래 stale 정책대로 만료 | `available` 비율만 높여 검출 품질이 좋아졌다고 보고 |

299/300 판정은 **원래 480행 full image의 다음 픽셀을 이미 가지고 있다**는 점을 쓴다. 이는 카메라 이동/FOV 변경이나 새 센서가 아니다. 실제 이미지 끝까지 이어지는 색 run에는 같은 방법으로 바깥 정보를 만들 수 없다. 색 연결성/최소 run의 정의까지 바꾸는 제안은 별도의 검출 정책 변경으로 명시한다.

부분 열만 잘린 경우에는 `raw supported runs`, `censored runs`, `observed edge candidates`, `inliers`를 구분하여 분모를 읽을 수 있어야 한다. 잘린 열을 제외한 뒤 candidate_count가 줄었다는 이유만으로 이전보다 훨씬 좁은 근거를 묵시적으로 통과시키지 않는다. 필요한 support 정의 변경은 입력 범위·identity·기존 음성 대조까지 포함해 검토한다. 최소 count만 만족하는 열이 한쪽에 몰린 경우의 slope 신뢰도도 count와 다른 문제다.

## ROI·margin 변경의 추가 판정

같은 full RGB에 대해 ROI 하단을 실제 경계보다 **위 / 정확히 경계 다음 행 / 아래**로 옮겨 보았을 때, 관측된 하단이 포함된 구간에서는 같은 물리 edge를 추정해야 한다. 실제 edge가 제외되는 구간에서는 결측이 늘 수 있지만, ROI 하단을 따라 움직이는 가짜 수평선이 새 측정으로 생기면 안 된다. `ROW_HI`가 exclusive이므로 y299 하단의 다음 background 픽셀은 y300이며, 이 인덱스 차이를 구분한다. ROI 좌표로 fit한 경우 반환 image 좌표의 offset도 일관돼야 한다.

이 조건은 동적 ROI나 margin 확대를 권고한 것이 아니다. 후보안이 ROI·sampling columns·선 선택·fit 가중치를 바꾼다면 측정 연산자가 달라진 것이므로, **새 선 검출의 타당성과 HIGH slope→relative-yaw gain의 타당성**을 따로 적는다. 기존 gain이 반드시 틀렸다는 결론이나 자동 재사용 허가는 이 합성 suite에서 나오지 않는다.

마지막으로 원본 `BeamEdgeTracker`의 settling, ref_n, min_dt, servo/unload reset, step limit, stale 조건을 보존한 채 end-to-end 단위 입력을 확인한다. crop이 거부된 프레임이 reference/last_ok_t를 채우면 안 된다. 이때 `available=False`가 곧 grip 실패라는 뜻은 아니며, grip monitor의 기록 전용 정책을 수정할 이유도 없다. 실제 HIGH 사례의 발생률·통과·배송 성공 검증은 이 인수 기준과 별개다.
