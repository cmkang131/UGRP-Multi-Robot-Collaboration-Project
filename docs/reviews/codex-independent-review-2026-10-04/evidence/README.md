# 독립 검토 증거 탐색

현재 [23차](../round23/README.md)는 [memory caller](../round23/memory.md)와 [case final tick](../round23/case.md)을 구분합니다. [독립 QA](../round23/validation.md)는 전자의 source-only 검사와 후자의 8개 저작 대조·선택 AST 실행을 각각 한정합니다. Full scheduler/finalizer·physics 실행은 아닙니다.

Mac `round23/evidence/`에는 공식 currentness, 두 source manifest, portable final-tick script/golden/독립 결과와 저자 네 원문·QA를 exact byte로 보존합니다. Theory 보충은 요약에 한 단락만 합쳤고 원문은 evidence의 authored 폴더에 남겼습니다. Script는 Git clone의 pinned objects와 표준 Python을 사용하며 새 임시 `--output`을 지정합니다. 원본 golden을 출력 대상으로 쓰지 않습니다. 상대 경로·원고/canonical 대응은 reproduction-notes에 설명합니다.

이전: [22차](../round22/README.md) · [21차](../round21/README.md) · [20차](../round20/README.md) · [19차](../round19/README.md) · [18차](../round18/README.md) · [17차](../round17/README.md) · [16차](../round16/README.md) · [15차](../round15/README.md) · [14차](../round14/README.md) · [13차](../round13/README.md) · [12차](../round12/README.md) · [11차](../round11/README.md) · [10차](../round10/README.md) · [9차](../round9/README.md) · [8차](../round8/README.md) · [원고 13개](../publication/README.md). 역사 본문과 증거를 소급 수정하지 않습니다.
