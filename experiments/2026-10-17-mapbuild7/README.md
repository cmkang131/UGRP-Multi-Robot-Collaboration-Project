# mapbuild7 — 인수·원인 분리·실제 경로 후보 (진행 중 / NOT_READY)

ownership-ack. `mapbuild1` / `codex/mapbuild1` / PR #556, gcp5 단독이다. CPU VM·다른 작업자의 VM·Mac sim/render·GUI·모델 호출은 사용하지 않는다. 요구표는 [mapbuild6 요구표](requirements.json)의 바이트를 유지한다. ACT 학생이나 LLM E2E 성공을 주장하지 않는다.

## 수정 전 R3 원인 분포

원본 `gcp5:/home/ugrp/ugrp-sim/runs/mapbuild6/recording-r3`와 봉인된 `replay-r3`를 gcp5 CPU에서 분석했다. 평가용 `mj_forward`만 사용하며 CPU 적분·제어 전달·상수 fitting은0이다. [원인표](prior-rejection_table.json), [시간별 요약](r3-cause-summary.json). 246개 구간의 XY 증분 잔차 합 순서다. 최종 SE(2) 오차의 가산 기여율이 아니다.

|구간 분류|n|XY 잔차 합 mm|카메라 회전 불일치 P50/P95 °|
|---|---:|---:|---:|
|LK 측정·발행 회전 명령 있음|39|155.433|1.042/1.212|
|rigid consensus 실패→명령 예측|26|76.591|1.022/1.315|
|LK 측정·그 외|36|60.477|.904/1.661|
|서보 명령 변화→명령 예측|51|53.667|2.121/7.609|
|적재/미확인 FK 거부→명령 예측|94|51.115|1.472/1.545|

따라서 빈도만으로 “명령 예측만 문제”나 “특징점 부족”이라고 결론내리지 않는다. 최대 구간7.1초는 참 이동9.153mm를 LK1.366mm로 추정했다. 2.2초는 참4.004mm 전진을10.310mm로 추정했다. 같은 실패 원본의 평가 카메라 차이는 전체 P95 위치16.303mm/회전7.308°다. 실제 카메라 자세는 평가 파일에만 있고 추정 입력으로 넣지 않는다. 실제 경로 확보 뒤 구간별 원인을 다시 분리해야 한다.

R3 자기 카메라 0–9.5/10–19.5/20–24.5초2Hz, 15–20초6시각, 20.6–22.5초10Hz 띠를 직접 확인했다. 물체가11초경 아래로 빠지고12–20초는 바닥/그림자,20.6초 이후 다시 들어온다. 영상만으로 접촉·IK·마찰 원인을 특정하지 않는다. 과거 CPU prefix가 native에서 미상승한 사실은 별도 평가 원장으로 확인된 실패이며 열린 루프 재생을 고치지 않는다.

## 후보와 근거

[API와 입력 계약](API.md). 카메라 치수·축·PWM 변환·보정·FOV는 그대로다. 새 카메라/정합 토글은 기본 off다. 실제 적재 자세 자격과 등록 정확도는 별도 관문이다. 정합의 범위/관측/거부 상수는 기존 `CSMOptions` 그대로이며 GT로 재맞춤하지 않는다.

- 기구 출처: `harness/data/servo_camera_v3_chain.json` SHA `0cced72fd129556cb1e1ecbeef63155129426e669f77b6d5a70244d3d9b269be`, `harness/visual_arm.py`, `sim/masterpi_camera_review_v3.py`.
- [Hiwonder 공식 MasterPi SDK 설명](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/9.ai_vision_project_course.html): 자기 서보 ID/PWM500–2500과 명령 지속시간. 실제 적재 정밀도/하중 처짐 자료로 확대하지 않는다.
- [Olson2009 원문](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf): SE(2) 후보의 상관 탐색과 복수 해 문제. lidar 성능을 색 경계 성능으로 승계하지 않는다.

첫 오프라인 R2/R3 후보는 FK 거부를 해소했지만 정합은 양쪽 `ambiguous_modes`였다. 해당 버전은 이후 센서 분산 누락이 확인돼 점수/후보 위치를 채택 근거에서 제외한다. 미확인 시작 위치를 spawn으로 채우지 않았다.

## 실행 상태

물리 이전 진입점 검사5건은 서로 다른 import/소스 closure 오류로 실패(물리·원본 프레임0), 이후 전체 장면 구성·native noslip0·동결 교사 클래스 SHA 확인을 통과했다. [모든 사전 오류](operations/preflight-rejection_table.json). 이5건의 수정은 합쳐진 사전 분포표 저장보다 먼저여서 “매 수정 전 표 저장”의 엄격한 절차 인수로 주장하지 않는다.

새 물리 R1은5.6SIM초/57프레임의 사전 자기 카메라 sweep 중 코드 검토에서 전역 정합의 거리별 픽셀 분산 누락을 확인해 `SUPERVISOR_STOP`했다. 실제 정합/파지/운반에 도달하기 전이다. [다음 수정 전 표](operations/prior-r2-rejection_table.json), [R1 요약](results/recording-r1-summary.json). 관측 선분별 카메라 원점을 보존하고 원래 CSM 분산 공식을 복원했다. 문턱/척도/정답 fitting은0이다.

R2는 `7a16faf44`에 고정해 실행 중이다. 교사 클래스 `6f057f7e`의 바이트(SHA `6b1cccf16d727449e059acebbba866cc4048f42918d8791ef8b1ba1729bcbdb6`), native NumPy IK와 질감 장면 builder를 재사용한다. 닫힌 루프 교사의 자기 RGB 보유 확인 뒤 지도 주행을 연결하는 새 실행기라 기존40/40을 승계하지 않는다. 근거리 교사는 시연용이며 학습 카메라가 아니다. 원본 전체10Hz 자기 RGB를 기록하는 목적은 위치 추정/실패 검토다. 파지 측정 관문·학습 데이터·학생 성공은 별도다.

부품/시험 통과는 실제 경로 인수가 아니다. 최종 요구 지점·비교·회수·해시·VM 종료·PR 상태는 완료 뒤 이 기록을 갱신한다.
