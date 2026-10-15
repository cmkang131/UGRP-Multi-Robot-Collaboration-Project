# reloc17 원본 프레임 관문 재집계

|실행|프레임→검출→갱신→PF resolved→mode→raw P→대응 NIS→기하축→유일→PF 일치→3뷰→수용|독립 registered|
|---|---|---:|
|reloc16-r1-selfmap-93584-v5-93635d6e-hostretry1|301 → 283 → 134 → 97 → 97 → 97 → 97 → 87 → 2 → 0 → 0 → 0|0|
|reloc16-r1-selfmap-93583-v5-93635d6e-hostretry1|301 → 288 → 142 → 83 → 83 → 83 → 83 → 64 → 1 → 0 → 0 → 0|0|
|reloc16-r1-selfmap-93584-v1-93635d6e-hostretry1|301 → 80 → 43 → 34 → 34 → 34 → 34 → 34 → 29 → 8 → 2 → 2|216|
|reloc16-r1-selfmap-93583-v1-93635d6e-hostretry1|301 → 133 → 72 → 55 → 55 → 55 → 55 → 55 → 30 → 12 → 2 → 2|219|
|reloc16-r2-selfmap-93584-v5-5f8b3eb2|301 → 112 → 52 → 35 → 35 → 35 → 35 → 34 → 26 → 8 → 2 → 2|219|
|reloc16-r2-selfmap-93583-v5-5f8b3eb2|301 → 104 → 50 → 44 → 44 → 44 → 44 → 43 → 30 → 13 → 3 → 3|221|
|reloc16-r3-selfmap-93584-v5-df8115a5|301 → 268 → 124 → 0 → 0 → 0 → 0 → 0 → 0 → 0 → 0 → 0|0|
|reloc16-r3-selfmap-93583-v5-df8115a5|301 → 287 → 108 → 0 → 0 → 0 → 0 → 0 → 0 → 0 → 0 → 0|0|

원본과 해시·사유별 거부·독립 통과 수는 rejection-table.json, 프레임별 값은 funnel-frames.csv.
기하/대응은 PF와 독립 계산되며 위 표는 비교용 순차 투영이다. PF가 막힌 뒤의 독립 통과를 수용으로 세지 않는다.

별도 초기 HOST_ERROR 4회는 RGB0프레임으로 영상 관문 분모에 넣지 않았다. 실행명·원본·사유·result SHA256은 JSON의 zero_frame_host_errors에 보존했다.
