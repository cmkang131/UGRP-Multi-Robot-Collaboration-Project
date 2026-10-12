# s4live11 DEV — 감독 확인 후 HOST_ERROR 분리
- 재판정: B 착지0/4·8구간 완주3/4, HOST_ERROR4/8(seed602 SSH 터널 단절); 연구 실패에 합산하지 않음.
- 원래0/8 집계는 summary-before-host-reclassification.json에 byte 그대로 보존; 원본·개별 물리 판정 불변.
- 유효 seed601의 B 오차0.446–0.526m, 나머지1건은 재파지 BAND_CLIPPED 시간초과.
- seed602는0.154–0.155m 뒤 같은 SSH 장애→요청 시간초과→lease 정지; 별도 HOST_ERROR.
- 재부팅 중단4시도도 원본·별도 비용 유지; 통신 장애4건과 동일 사건으로 합치지 않음.
- 원본은 x86 평가 후 ARM 전체 해시 확인; Mac에는 fetch-lite만.
- 실제429는0회, 재시도 물리 보류는 오프라인 시험만 검증.
- [summary.json](summary.json)에 원본 위치·sha256·모델 계수·분모·분류 이력·남은 원인.
