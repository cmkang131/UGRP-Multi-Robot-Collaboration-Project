# 독립 검토 증거 탐색

현재 [21차](../round21/README.md)는 #220의 기존 평가 gate와 #225 교사 전용 TOP consumer를 분리합니다. [독립 QA](../round21/validation.md)와 [남은 인수 질문](../round21/backlog.md)을 함께 읽습니다. 새 결함이나 실제 시연 성공을 보고하지 않습니다.

Mac `round21/evidence/`에는 공식 텍스트 snapshot, 36개 source object의 hash/AST 결과, 읽기 전용 검사 script와 독립 QA를 보존합니다. 저자 원문 두 개는 `authored/*.md.txt`로 byte를 유지합니다. Script는 Python3/Git 및 세 pin object가 필요하며 `--repo`와 `--output`을 명시합니다. 기존 결과 파일을 덮어쓰지 않습니다. 원래 source workspace 상대 링크와 canonical 이름은 reproduction-notes에 설명합니다.

이전: [20차](../round20/README.md) · [19차](../round19/README.md) · [18차](../round18/README.md) · [17차](../round17/README.md) · [16차](../round16/README.md) · [15차](../round15/README.md) · [14차](../round14/README.md) · [13차](../round13/README.md) · [12차](../round12/README.md) · [11차](../round11/README.md) · [10차](../round10/README.md) · [9차](../round9/README.md) · [8차](../round8/README.md) · [원고 13개](../publication/README.md). 역사 본문과 증거를 소급 수정하지 않습니다.
