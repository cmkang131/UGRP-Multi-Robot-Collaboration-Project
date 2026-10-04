# 독립 검토 증거 탐색

현재 [28차](../round28/README.md)는 색/화물 offline writer→score의 분모와 동명 지표 정의를 분리합니다. [독립 QA](../round28/validation.md)는 최종 v2 결과와 source 20개를 대조했습니다. 원래 parser/writer/score body와 저작 world·detector·cv2를 연결한 것이며 실제 렌더나 검출 성능 대조가 아닙니다.

Mac `round28/evidence/`에는 script/source-manifest/source 폴더의 상대 배치, active v2와 historical v1, 독립 check, 원고/QA exact byte를 보존합니다. 새 임시 `--output`을 사용하고 원본 golden은 덮어쓰지 않습니다. Source README/docs의 상대 링크는 전체 원 repository를 가리켜 이 선택 bundle에 대상이 모두 포함되지는 않습니다. 원본 source를 고치지 않고 reproduction-notes에 정확 pin과 해석 범위를 적었습니다. 108회 fake detector 호출은 독립 실험 수가 아니고 managed subprocess/전체 finalizer도 실행하지 않았습니다.

이전: [27차](../round27/README.md) · [26차](../round26/README.md) · [25차](../round25/README.md) · [23차](../round23/README.md) · [22차](../round22/README.md) · [21차](../round21/README.md) · [20차](../round20/README.md) · [19차](../round19/README.md) · [18차](../round18/README.md) · [17차](../round17/README.md) · [16차](../round16/README.md) · [15차](../round15/README.md) · [14차](../round14/README.md) · [13차](../round13/README.md) · [12차](../round12/README.md) · [11차](../round11/README.md) · [10차](../round10/README.md) · [9차](../round9/README.md) · [8차](../round8/README.md) · [원고 13개](../publication/README.md). 역사 본문과 증거를 소급 수정하지 않습니다.
