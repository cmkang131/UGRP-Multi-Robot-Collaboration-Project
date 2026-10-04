# 독립 검토 증거 탐색

현재 [25차](../round25/README.md)는 [REAL trace 시간 경계](../round25/clock.md)의 조건부 summary 선택 누락을 기록합니다. [독립 QA](../round25/validation.md)는 source/document 의미와 원래 writer/분석기 4개 합성 대조를 구분합니다. 원본 archive와 실패 상태는 보존됐고 실제 장비 clock·물리원인·과거 trace를 검사하지 않았습니다. [이슈 인수표](../round25/acceptance.md)는 이전 조회 시점의 작업 선정 기록입니다.

Mac `round25/evidence/`에는 source manifest, Python/Git 재현 script와 결과, 독립 receipt, 저자 세 원문의 exact byte를 보존합니다. 실행한 source는 세 writer/consumer 파일이며16개 source hash 확인을 전체 동작 실행으로 읽지 않습니다. 새 임시 `--output`을 사용하고 원본 golden을 덮어쓰지 않습니다. 원문/canonical 경로와 번호24 통합 이유는 reproduction-notes에 설명합니다.

이전: [23차](../round23/README.md) · [22차](../round22/README.md) · [21차](../round21/README.md) · [20차](../round20/README.md) · [19차](../round19/README.md) · [18차](../round18/README.md) · [17차](../round17/README.md) · [16차](../round16/README.md) · [15차](../round15/README.md) · [14차](../round14/README.md) · [13차](../round13/README.md) · [12차](../round12/README.md) · [11차](../round11/README.md) · [10차](../round10/README.md) · [9차](../round9/README.md) · [8차](../round8/README.md) · [원고 13개](../publication/README.md). 역사 본문과 증거를 소급 수정하지 않습니다.
