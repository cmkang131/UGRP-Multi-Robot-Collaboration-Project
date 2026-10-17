# 저장 실패72개: 이탈 전1 SIM초 명령 비교

부호열은 시간순 최대10개 0.1 SIM초 명령이다. 기록 시작 후1초 안에 이탈하면 존재하는 짧은 구간만 표시한다. +/−/0은 고정 issued-command odometry의 yaw 부호이며 ?는 해당 같은 상태의 교사 라벨 미확인이다.
크기는 명령마다 예측한 yaw 절댓값 중앙/p90(deg/0.1 SIM초 명령)이다. 실제 차체 회전·물리 성공·이탈 인과가 아니다.
이탈은 seven-probe 기하 검사이며 픽셀 전체 이탈과 다르다. 원본의 visible-only·잠재 집게 닫기 경계를 유지했다.

|모델·seed|이탈 SIM초|학생 부호열|학생 중앙/p90 deg|교사 부호열|교사 중앙/p90 deg|유효 N|분류|
|---|---:|---|---:|---|---:|---:|---|
|A 87434|9.6|++++++++++|0.0847/0.1422|+++++++++0|1.5149/1.5149|10|unidirectional|
|A 87454|5.1|++++++++++|0.0986/0.2081|+++++++000|0.1552/0.1855|10|unidirectional|
|A 87424|18.1|0000000000|0.0000/0.0000|??????????|NA|0|stopped_rotation|
|A 87444|0.1|0|0.0000/0.0000|0|0.0000/0.0000|1|stopped_rotation|
|A 87449|9.9|++++++++++|0.5618/0.5988|??????????|NA|0|unidirectional_teacher_unavailable|
|A 87439|4.8|----------|0.6577/0.6713|??????????|NA|0|unidirectional_teacher_unavailable|
|A 87459|8.7|---------+|0.1047/0.6536|??????????|NA|0|oscillation|
|A 87429|7.9|++++++++++|0.5359/0.6799|??????????|NA|0|unidirectional_teacher_unavailable|
|B 87434|0.7|0000000|0.0000/0.0000|0??????|0.0000/0.0000|1|stopped_rotation|
|B 87454|8.1|---------0|0.0696/0.0947|??????????|NA|0|unidirectional_teacher_unavailable|
|B 87424|2.5|++++++++++|0.9297/0.9479|++++++++++|1.5149/1.5149|10|unidirectional|
|B 87444|0.9|00000000+|0.0000/0.0497|0????????|0.0000/0.0000|1|unidirectional|
|B 87449|4.3|++++++++++|0.8013/0.8200|??????????|NA|0|unidirectional_teacher_unavailable|
|B 87439|5.9|----------|1.1524/1.1562|??????????|NA|0|unidirectional_teacher_unavailable|
|B 87459|8.0|----------|0.2526/0.6080|??????????|NA|0|unidirectional_teacher_unavailable|
|B 87429|13.3|-----00000|0.0018/0.0257|??????????|NA|0|unidirectional_teacher_unavailable|
|C 87434|13.3|++++++++++|0.3195/0.7883|??????????|NA|0|unidirectional_teacher_unavailable|
|C 87454|8.9|-000000000|0.0000/0.0025|??????????|NA|0|unidirectional_teacher_unavailable|
|C 87424|0.7|0000000|0.0000/0.0000|0000000|0.0000/0.0000|7|stopped_rotation|
|C 87444|6.7|-------+++|0.0834/0.2020|??????????|NA|0|oscillation|
|C 87449|16.0|-+++++++++|0.1560/0.1959|--????????|0.9522/0.9529|2|oscillation|
|C 87439|5.7|----------|0.7509/0.7965|??????????|NA|0|unidirectional_teacher_unavailable|
|C 87459|15.9|--00000000|0.0000/0.0046|??????????|NA|0|unidirectional_teacher_unavailable|
|C 87429|4.9|++++++++++|1.1839/1.1977|??????????|NA|0|unidirectional_teacher_unavailable|
|D1 87434|0.1|0|0.0000/0.0000|0|0.0000/0.0000|1|stopped_rotation|
|D1 87454|7.3|----------|0.2403/0.2933|??????????|NA|0|unidirectional_teacher_unavailable|
|D1 87424|0.6|000000|0.0000/0.0000|000000|0.0000/0.0000|6|stopped_rotation|
|D1 87444|0.1|0|0.0000/0.0000|0|0.0000/0.0000|1|stopped_rotation|
|D1 87449|0.9|00000000+|0.0000/0.1607|0????????|0.0000/0.0000|1|unidirectional|
|D1 87439|5.5|----------|0.5138/1.0245|??????????|NA|0|unidirectional_teacher_unavailable|
|D1 87459|8.0|----------|0.7921/0.8636|??????????|NA|0|unidirectional_teacher_unavailable|
|D1 87429|4.9|++++++++++|0.6264/1.0395|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91620|6.7|++++++++++|0.3042/0.3231|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91621|11.8|----------|0.1330/0.1597|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91630|5.7|----------|1.1831/1.2357|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91637|11.1|++++++++++|0.6940/0.7294|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91638|NA|NA|NA|NA|NA|0|no_geometric_exit|
|FINAL_A 91652|5.0|++++++++++|0.2472/0.2736|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91656|9.8|++++++++++|0.2106/0.2940|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91622|12.9|-++++++000|0.0370/0.1356|??????????|NA|0|oscillation|
|FINAL_A 91624|8.2|----------|0.9997/1.1215|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91626|5.6|----------|0.1663/0.3352|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91632|9.0|++++++++++|0.5034/0.6467|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91634|8.0|----------|0.1688/0.2282|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91642|8.1|+++++++++-|0.0529/0.0930|??????????|NA|0|oscillation|
|FINAL_A 91646|6.0|----------|0.7074/0.7118|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91650|7.9|----------|0.2615/0.2929|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91654|9.6|00-+000000|0.0000/0.0501|??????????|NA|0|oscillation|
|FINAL_A 91658|8.6|----------|0.3399/0.3874|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91623|5.0|-------+--|0.1507/0.2112|??????????|NA|0|oscillation|
|FINAL_A 91627|5.3|----------|0.4377/0.5700|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91631|5.7|----------|0.9800/1.0855|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91635|6.4|++--------|0.2561/0.2915|??????????|NA|0|oscillation|
|FINAL_A 91639|4.7|----------|0.6398/0.7529|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91643|8.1|----------|0.2300/0.3734|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91647|6.1|++++++++++|0.2565/0.2755|+++++++000|1.1503/1.2381|10|unidirectional|
|FINAL_A 91651|6.2|-------+++|0.0299/0.0856|??????????|NA|0|oscillation|
|FINAL_A 91655|4.6|----++++++|0.2919/0.5342|??????????|NA|0|oscillation|
|FINAL_A 91659|17.8|0000000000|0.0000/0.0000|??????????|NA|0|stopped_rotation|
|FINAL_A 91625|8.5|+++++-----|0.0847/0.1350|??????????|NA|0|oscillation|
|FINAL_A 91628|10.7|++++++++++|0.6595/0.7051|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91641|9.5|++++++++++|0.1022/0.1767|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91649|NA|NA|NA|NA|NA|0|no_geometric_exit|
|FINAL_A 91653|8.8|++++++++++|0.3814/0.4017|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91657|8.7|----------|0.1158/0.1647|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91629|4.1|++++++++++|1.0902/1.1274|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91633|10.5|----------|0.0784/0.1111|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91636|4.7|++++++++++|0.6712/0.6849|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91640|5.8|++++++++++|0.2015/0.2493|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91645|1.2|000000000-|0.0000/0.0429|00000-????|0.0000/0.7575|6|unidirectional|
|FINAL_A 91644|5.6|++++++++++|0.6356/0.7575|??????????|NA|0|unidirectional_teacher_unavailable|
|FINAL_A 91648|7.2|--++++++++|0.0888/0.1304|??????????|NA|0|oscillation|

원본: /home/ugrp/ugrp-sim/runs/act17-closed-loop-r1/summary.json, sha256=0a3e27f1ad9eedc22440b5f7f698751d06c628526f06594426b04e1beab94443。

새 물리0·학습0·추론0, 저장된 원장의 파생 표다.
