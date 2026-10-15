# reloc13 관문표와 거부 분포

프레임 누적: 등록 → 유한 실행 자세 전달(명령 전파 포함) → 같은 프레임 지도 삽입 → 주행 사용. 신선한 정적 보정 수용은 별도 열이다. 영상/시간 상관 프레임이며 임무 성공률이 아니다.

|조건|등록 이벤트(오등록)|등록 프레임|자세 전달|신선한 정적 보정|지도 삽입|주행|제어 자세 오류(10cm/5°)|종료|
|---|---:|---:|---:|---:|---:|---:|---:|---|
|reloc12_texture|4(0)|446|446|65|0|0|147/446|{'selfmap4_relocalization_exhausted': 4}|
|R1_texture|2(0)|149|149|0|146|52|149/149|{'supervisor_stop': 2}|
|R1_smooth|0(0)|0|0|0|0|0|0/0|{'supervisor_stop': 1}|
|R2_texture|4(0)|1262|1262|84|1233|360|644/1262|{'cap_end': 3, 'selfmap4_relocalization_exhausted': 1}|
|R3_texture|4(0)|626|626|60|302|36|282/626|{'selfmap4_relocalization_exhausted': 2, 'cap_end': 2}|

|운반 seed|물리 들기|carry_to_zone|zone_place_view|놓기/배송|종료|
|---|---:|---:|---:|---:|---|
|93266|1|0|0|0|cap_end|
|93315|1|1|0|0|carry_recovery_setdown_envelope_blocked|

R3의 주행 감소/삽입 차단은 R7 증거 상실에 대한 정지이며 운용 성공이 아니다. legacy10cm/5°와 감사15cm/5°,30cm/10°는 각 run JSON에 따로 기록했다. R2의 더 긴 주행과 R3의 중단을 reloc12의 짧은 회전 궤적과 합산하지 않는다.

거부 수(누적 관문 첫 실패 및 삽입 이유는 단위별 중복될 수 있다):

reloc12_texture

|사유|수|
|---|---:|
|registered:not_yet_registered|446|
|insertion:pose_uncertain|446|
|map_inserted:pose_uncertain|436|
|map_inserted:camera_unsettled;pose_uncertain|10|
|insertion:camera_unsettled|10|

R1_texture

|사유|수|
|---|---:|
|registered:not_yet_registered|274|
|control_drive_used:stage:active_reloc8|92|
|map_inserted:camera_unsettled|3|
|insertion:camera_unsettled|3|
|control_drive_used:stage:select|2|

R1_smooth

|사유|수|
|---|---:|
|registered:not_yet_registered|133|

R2_texture

|사유|수|
|---|---:|
|control_drive_used:stage:active_reloc8|604|
|registered:not_yet_registered|446|
|control_drive_used:stage:spin|176|
|control_drive_used:stage:pan|76|
|map_inserted:camera_unsettled|29|
|insertion:camera_unsettled|29|
|control_drive_used:stage:select|13|
|control_drive_used:stage:stopped|4|

R3_texture

|사유|수|
|---|---:|
|registered:not_yet_registered|446|
|insertion:registered_r7_unconfirmed|316|
|map_inserted:registered_r7_unconfirmed|308|
|control_drive_used:stage:active_reloc8|208|
|control_drive_used:stage:spin|33|
|control_drive_used:stage:pan|21|
|insertion:camera_unsettled|16|
|map_inserted:camera_unsettled|8|

위치/증거 관문의 물리 틈은 해당 없음(null), 막은 대상은 private map/등록 증거다. 실제 운반 경로 거부는 own_rgb:heavy_crate:4, 최소 틈 −0.07273354264836535m이며 기존 segment_free의 margin-escape 규칙으로 GCP에서 재현했다.

원본 경로·sha256·재현 명령은 [rejection-table.json](rejection-table.json), 기존147오류의 백분위·원인 분류는 [baseline-funnel.json](baseline-funnel.json)과 각 cohort JSON을 참조한다.
