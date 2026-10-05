# 추가 8차 — HIGH beam edge의 가림 경계와 선 추정

검토 소스는 PR #363 **`0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`**이다. 이 메모는 구현 변경 없이 코드와 작은 합성 RGB 반례만 검토한다. 물리 실행·렌더·하드웨어·유료 모델·raw/heldout/blind 결과를 읽거나 실행하지 않았다. `geometry-repro.py`가 직접 만든 RGB와 원본 `own_beam_edge.py`만 재현에 사용했다. 이전 라운드의 preclose 0-point 설명을 최신 실패 원인으로 승계하지 않는다.

## 결과

**신규 조건부 P2: ROI 아래로 이어지는 색띠가 실제 빔 하단 경계로 수락된다.** `edge_line`은 40–299행만 잘라 `_first_run_end`에 주는데, 이 함수는 마지막 픽셀 뒤에서 색띠가 끝났는지 확인하지 않고 잘린 배열 끝을 run의 끝으로 돌려준다. 실제 경계가 ROI 밖에 있어도 모든 열에서 가짜 수평선 y=299를 얻는다. 원본 tracker는 이를 정상 reference로 만들고 `available=True`를 보고한다.

현재 공개된 HIGH timeout은 이 반례의 실제 발생 사례가 아니다. 저자는 공개 댓글에서 대부분의 경계가 169–171행이고 일부 오른쪽 열이 79–80행이라 OLS seed가 흔들렸다고 설명했다. 이번 crop 반례는 **그 문제를 robust fitting으로 고칠 때도 따로 유지해야 할 음성 대조 조건**이다. 실제 HIGH 영상에서 crop 오인이 발생했는지, 얼마나 자주 발생하는지는 확인하지 않았다.

| 구분 | 이번 확인 | 의미 |
|---|---|---|
| ROI 경계 오인 | 원본 detector/tracker에 합성 RGB를 직접 입력하여 재현 | 현재 사용하는 공유 모듈의 조건부 정확성 문제; #363이 새로 도입한 코드라는 뜻은 아님 |
| 소수 열이 OLS seed를 왜곡 | 84/90열의 정확한 수평선에 오른쪽 6열만 80 px 이동하면 `None` | 저자의 공개 진단과 같은 메커니즘을 독립 합성으로 확인; 신규 발견으로 세지 않음 |
| ray/plane/footprint | 관련 최신 caller와 필터 순서를 읽음 | 새 축 전치·단위 오류를 발견하지 못함; 전체 OpenCV/보정값/실물 검증은 아님 |
| 기존 floor preclose | 새 `blind_final_approach`가 별도 증거 경로를 추가함 | 이전 0-point 거부를 현재 최신 blocker라고 반복하지 않음; 새 blind 경계는 frontier 검토 담당 |

## 1. 왜 crop 끝이 유효한 edge가 아닌가

원본 모듈의 [설명 1–18행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L1-L18)은 **carried beam의 lower edge slope**로 robot-minus-beam 상대 yaw 변화를 관찰한다고 정한다. [함수 계약 62–66행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L62-L66)도 lower edge를 반환한다고 한다. 코드에는 ROI 경계를 물리 경계의 대리값으로 쓰겠다는 예외가 없다.

[45–55행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L45-L55)의 loop는 `j + 1 < n` 때문에 배열 끝에서 멈춘 뒤 run 길이가 40 이상이면 `j`를 반환한다. [73–77행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L73-L77)의 입력은 `mask[40:300, c]`이므로, 원래 영상의 300행 이후에 색띠가 계속 있어도 반환값은 항상 299행이다. 이는 관측된 하단 경계와 관측 구간에서 잘린 run을 구분하지 못한다.

합성 이미지의 바탕 RGB는 `(40,40,40)`, 색띠는 기존 테스트와 같은 `(150,200,30)`이다. 실제 색띠 하단은 `round(340 + slope*(x-320))`, 두께 120 px이며 480×640 전체 이미지 안에 존재한다. `slope=+.04`와 `-.04` 모두 90개 검사 열에서 실제 하단이 300행보다 아래다. 두 이미지에 모두:

- 후보 열 90개, crop 끝을 반환한 열 90개, **300행에도 foreground인 열 90개**;
- `edge_line ≈ (0.0, 299.0, 90)`;
- 원본 `BeamEdgeTracker(1.)`의 기본 `settle_s=3`, `ref_n=2`, `min_dt_s=.5`로 입력하면 reference가 생기고 `available=True`;
- +.04 영상 10개 후 -.04 영상 10개로 바꿔도 `available=True`, `total_rad=0`이다.

마지막 결과의 **0.08 px/px 차이를 0.08 rad라고 해석하지 않는다.** 실제 HIGH slope-to-yaw gain을 측정한 실험이 아니고, tracker에는 명시적으로 ratio 1을 사용했다. 핵심은 어떤 양의 ratio를 선택해도 crop 때문에 두 서로 다른 물리 영상 경계 기울기가 같은 관측 0으로 붕괴한다는 것이다.

음성·양성 대조:

| 합성 입력 | 원본 결과 | 대조의 역할 |
|---|---|---|
| 깨끗한 실제 경계, centre=200, slope=.03 | slope `.0298411`, 90열 | 정상 구간에서 원본의 선 추정이 작동함 |
| 색띠 없는 영상 | `None`, tracker unavailable | 검출 실패 경로가 존재함 |
| 실제 경계가 정확히 299행에서 끝남 | y299 수락, 300행 foreground 0열 | y299를 무조건 지우는 수정은 정상 관측도 지움 |
| 실제 경계가 300행에서 끝남 | 잘린 y299 수락, 300행 foreground 90열 | 단 1행 바깥에서도 관측된 끝과 잘린 끝의 구분이 필요함 |
| 실제 경계 centre340, slope±.04 | 두 경우 모두 잘린 y299 수락 | 관측 대상 기울기와 무관한 완벽한 합의가 만들어짐 |

따라서 요지는 threshold 확대나 특정 y값 일괄 제거가 아니다. run이 crop 끝에 닿으면 바로 다음 영상 픽셀에서도 foreground가 계속되는지와 같은 **관측된 끝인지 잘린 run인지**의 구분이 필요하다. 이것은 구현 패치를 제시하거나 자동 채택한 것이 아니라 검출기의 계약을 정하는 검토 조건이다.

## 2. 최신 HIGH caller에서의 의미

다음 연결은 최신 소스에서 직접 확인했다.

1. [HighPoseSource 90–102행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/vision_pose_source_highpose.py#L90-L102)은 loaded·settled·issued HIGH 조건에서 `beam_edge.observe(now, rgb, servo, enabled)`를 호출한다. 반환된 0이 아닌 yaw increment는 PF에 전달하고, 매 프레임 `update_availability`를 호출한다.
2. [BeamEdgeTracker 140–170행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L140-L170)은 `edge_line`이 `None`이 아니면 reference/최근성 정보를 갱신한다. crop 수평선은 step=0이므로 step-limit 거절도 일어나지 않는다. `applied` 통계가 증가해도 반환 increment는 `None`일 수 있는데, 이는 코드의 0-step 처리이며 이번 보고에서 실제 yaw 교정이 있었다고 세지 않았다.
3. [HIGH wait_carry 277–285행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_runtime.py#L277-L285)은 `beam_edge.available(now)`가 거짓일 때 edge reference pending/timeout을 적용한다. 참이면 부모의 carry barrier 검사로 넘어간다. **이 하나가 참이라고 운반 명령이나 성공이 자동 허가되는 것은 아니다.**
4. [update_availability 258–278행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/owncam_carry_v6e.py#L258-L278)은 같은 availability로 상대 yaw estimator 사용 가능 여부를 분류하여 fallback 추가 yaw uncertainty를 선택한다. 가짜 edge의 영향은 단지 로그 문자열에 한정되지 않는다. 실제 수치 영향은 보정값·다른 상태에 의존하며 이 메모는 실험으로 측정하지 않았다.

이 경로는 **상대 yaw/항법 관측의 유효성**이다. `grip_monitor`가 기록 전용이라는 사용자 결정을 바꾸거나 grip-loss detector를 readiness 필수조건으로 복원하자는 주장이 아니다. 센서·FOV·GT 입력 추가도 제안하지 않는다.

재현은 detector/tracker에 직접 입력한 조건부 테스트다. 전체 provider·프레임 게이트·물리 로봇·carry barrier를 합성 이미지로 끝까지 실행한 것은 아니다. caller 연결은 소스 검토로 확인했다. 현재 HIGH 자세에서 이런 영상이 실제 생긴다는 주장에는 별도의 증거가 필요하다.

## 3. 공개 OLS 실패와 robust fitting 변경에 남는 질문

[작성자의 2026-10-04 04:34:44Z 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5976609395)은 각 로봇 HIGH 302프레임에서 검출이 `None`, 다수 열의 실제 띠 경계는 169–171행, 오른쪽 5/10열만 79–80행이라 설명한다. 이 수치는 작성자의 공개 재생 결과로 인용하며 raw를 새로 열거나 독립 물리 결과로 합산하지 않는다.

원본 detector는 90개 열 중 후보가 90개이면 trim 후 54열 이상이 필요하다. 정확히는 `max(20, .6×90×.5, .6×candidate_count)`를 만족해야 하므로 후보 수가 작을 때도 최소 27열이 필요하다. "항상 54열" 또는 "20열이면 충분"이라고 일반화하면 부정확하다.

독립 합성에서는 수평 경계 180행의 90열 중 **오른쪽 6열만 260행**으로 옮겼다. 나머지 84열은 정확히 같은 선 위에 있지만 전체 OLS seed는 slope `.0829732`를 만들고 4 px trim 후 24열만 남아 `None`이 된다. 해당 6열 이동을 없애면 90열을 정상 수락한다. 이는 다수의 선 후보가 있어도 초기 OLS에 높은 영향력을 가진 끝부분의 소수 열이 검출을 탈락시킬 수 있음을 보여 준다. 공개 사례의 부호·위치·숫자를 그대로 재생한 것은 아니다.

RANSAC/robust estimator를 검토할 때 다음 문제는 서로 다르다.

- 소수 열의 잘못된 run 선택: 지배적인 같은 물리 경계의 consensus를 찾는 문제다.
- ROI에서 잘린 run: **90/90열의 완벽한 가짜 합의**이므로 RANSAC으로는 구분되지 않는다.
- 서로 다른 실제 경계 둘, 혹은 넓은 색 표면: 선을 잘 맞췄다는 사실만으로 beam identity가 증명되지 않는다.
- 선 slope와 상대 yaw의 연결: HIGH 자세·선 후보 선택·사용 열 범위가 달라지면 선 검출 통과와 기존 gain의 유효성은 별도 검증 항목이다. 현재 gain이 반드시 틀렸다는 결론은 내리지 않는다.

따라서 현재 blocker의 진단은 "빔 없음"으로 축약하기보다 `run 없음 → crop으로 잘림 → 관측된 후보 경계들 → consensus/coverage → line residual → reference 생성/최근성`으로 나누는 것이 유용하다. 추가 물리 실행 없이도 합성 대조에 이 경계를 유지할 수 있다. 알고리즘 수정 자체와 새 실제 실행은 이번 작업에서 하지 않았다.

## 4. ray/plane·partial support 검토 범위

다음은 신규 오류가 확인되지 않은 소스 경계다. 이전 보정 기하 라운드와 같은 검사를 새 발견처럼 계수하지 않는다.

| 읽은 최신 소스 | 확인한 계약과 제한 |
|---|---|
| `zone_final_pair_vision.py:62–68` | fisheye의 정규화 optical `(x,y,1)`를 per-pose measured rotation으로 base 방향으로 돌린 뒤 unit ray로 정규화한다. 행벡터 표현의 `optical @ rotation.T` 자체를 전치 오류라고 볼 근거는 없다. `camera_record`는 unloaded floor-supported beam view용이며 loaded edge detector는 이 평면 투영을 쓰지 않는다. |
| `zone_final_pair_contract.py:79–93` | finite shape, orthonormal rotation, det≈+1과 pose key를 검사하고 floor frame 변환을 적용한다. nominal static 값의 내부 일관성과 실제 하중에서의 보정 정확도는 구분된다. |
| `zone_pair_grasp_entry_v6c.py:76–84` | colour+SIM-valid ray+downward 조건 후 beam top `z=.032m`에 교차시킨다. 양의 ray distance와 **base 원점 기준 XY norm<2.5m**를 남긴다. 이 값은 depth-camera 실측값이나 camera-to-point Euclidean range가 아니다. 함수 자체는 plane hypothesis를 사용한다. |
| `zone_pair_beam_track.py:169–193` | segment, anchor age, sigma와 60개 이상의 현재 partial point, 95% footprint 일치가 별도 조건이다. patch는 pose/age/sigma를 갱신하지 않는다. |
| `zone_pair_grasp_entry_v6c.py:87–106,129–139` | tracked grip 앞쪽 in-footprint 점들의 2–98% across-axis span≥28mm와 core max gap≤3mm를 요구한다. 넓은 평면 색표식과 실제 raised beam의 단안 모호성은 원본 docstring에 이미 명시돼 있다. |
| `zone_final_pair_guards.py:126–145` | preclose의 pose/frame/command 조건 뒤 beam estimate가 없으면 `BEAM_UNCERTAIN`; stationary beam/wall clearance는 그 뒤 계산한다. 최신 HIGH는 여기에 새 blind track을 주입하므로 옛 partial-point 필수 경로만으로 최신 close 도달 여부를 설명할 수 없다. |

이 라운드에서 OpenCV 패키지를 새로 설치하거나 전체 기하 테스트 suite를 실행하지 않았다. numpy/Pillow로 가능한 실제 edge 모듈의 조건부 반례에 검증을 집중했다. `_pixel_rays`, camera calibration의 모든 수치, 실제 pose의 visibility, full provider loop를 재검증한 보고가 아니다.

## 재현 자료

- `geometry-repro.py`: 실행 가능한 합성 RGB witness와 assert; 구현 파일을 수정하지 않는다.
- `geometry-repro.json`: 입력 구성별 detector 결과, run/trim/crop 수, tracker 결과.
- `geometry-source/own_beam_edge.py`: 해당 SHA의 원본. SHA-256 `f72118c5c1faeb91094347469dd15fa6059dd99bd6acede4760eec96411f3e8d`; 최신 PR363 snapshot 및 로컬 기준 main의 같은 파일과 바이트 동일함을 확인했다.
- 환경: Python의 설치된 NumPy `2.3.5`, Pillow `12.3.0`; 새 의존성 설치 없음.
- 재현 명령: `python review-notes/round8/geometry-repro.py`.

전체 repository의 코드·설정·등록문서·실험 결과를 수정하지 않았다. 이 메모의 새 finding은 conditional detector correctness 한 건이며, 공개 OLS 진단과 과거 preclose/보정 한계를 추가 결함으로 중복 계수하지 않는다.
