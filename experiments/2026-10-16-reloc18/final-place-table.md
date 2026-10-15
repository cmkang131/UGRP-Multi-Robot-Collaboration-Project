# 최종 place 관문

R3 DEV 예산 observe-only 조건. site는 발행 PWM의 명목 FK로 계산하고 실제 base로 평가 변환했다. 하중 처짐/실기 교정 미확인.

|조건·시드|place RGB|기하 통과|색 통과|처음 xy 오차 m|처음 site 구역 여유 m|종료|
|---|---|---|---|---|---|---|
|candidate 93266|31|31|0|2.3814|-2.0345|destination_floor_not_visible|
|candidate 93315|31|31|0|1.1916|-0.7801|destination_floor_not_visible|
|reloc18-r3-carry-command_only-93266-133c12f4|0|NA|NA|NA|NA|place 미도달|
|command_only 93315|31|31|0|0.7285|-0.6411|destination_floor_not_visible|

도착 추정→place-view는 후보2/2, advance/lower/open/final place는0/2. 검사한93프레임은 전부 색 비율0이며 재구성 불일치0이다.
목적지 바닥이 보이지 않는 것을 실제로 거부했다. 내려놓기 동작·최종 높이·자세 판정까지 가지 않아 그 조건의 결함/성공은 미검증이다.
