# 미완료 prefix 확인 (교사 관문 결과 아님)

대상: group0/world000, seed8317104. `review-own` 2Hz 전체60프레임, SIM0.0–29.5를3장 띠로 직접 확인했다. 원본은 gcp2 `/home/ugrp/ugrp-sim/runs/warp3/prefix-review-g0w0-0013/`, 회수는 primary `outputs/e2e18-admin/playback/warp3-prefix-g0w0/`이며 전송 SHA 일치를 확인했다.

- SIM0–8.5: 청록 상자가 점점 커지고 화면 아래로 이동한다. 초기에는 다른 로봇과 빨강 상자·벽 경계도 보인다.
- SIM9–11.5: 청록 상자가 화면 하단 가장자리를 드나든다.
- SIM12–29.5: 화면 대부분은 파란 구역이며 대상은 직접 보이지 않는다. 명령 원장은 hover/descent/close/lift/정착/뒤돌아 보기/hold/return/lower 순서다. 화면 밖의 파지를 RGB만으로 단정하지 않는다.

RGB 원장의 SIM24.3 확인은 `pickup_site_proven_empty`, 즉 집던 자리가 비었다는 근거이고 보유 성공 자체의 판정은 아니다. 물리 평가상 stable lift7/7은 별도 미완료 snapshot에만 있다. 내려놓기·최종 완료와 원인 판정은 아직 없다.

이것은 실행 중 prefix의 시각적 관측이다. 개요 합성 영상과 종료10SIM초/10Hz 버퍼는 완료 뒤 확인할 예정이고, 빠른 진동이나 실패 원인을 검토했다고 주장하지 않는다. 기존 warp1 기록의 반투명 구역 렌더 차이를 유지한 상태이며 C 영상 동등성을 새 관문으로 추가하지 않는다.
