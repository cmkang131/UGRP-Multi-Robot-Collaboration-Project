# 19차 독립 검증의 범위

## Priorities

별도 synthesis 검토자가 최신 17차 전달 navigation과 핵심 8/12/13/15/16/17/18차 원고를 읽고 범위·중복 집계·수정 확인·최소 수용 기준을 재도전했다. R12 lower port와 R16 upper queue를 원본 source로 좁게 대조하고, de03→66ff 관련 9개 파일의 바이트 동일성을 확인했다. 새 전체 host 실행이나 fixture 재실행은 하지 않았다.

통합 검토자가 최종 synthesis와 현재 전달 우선순위의 일치를 확인했다. 전송 전 미요청 0/refund와 전송 뒤 청구를 구분하고, 정확한 dock tuple을 읽어 8단계·7개 고유 pan으로 정밀화했다. Geometry와 evaluation도 한정된 의미를 cross-read했다. 같은 취소 계열이라는 분류는 동일 root cause나 단일 회귀만으로 해결된다는 뜻이 아니다. 새 버그는 0개다.

## Issues

Coverage 검토자는 공식 09:12 UTC 열린 이슈 16개를 첫 snapshot과 비교하고 새 댓글 3개만 읽었다. 모두 open이라는 metadata와 제목·본문 불변, #219/#366 댓글 변경 범위를 기록했다. Synthesis 검토자의 별도 QA는 문서 일관성과 주장 강도에 한정하며 공식 API를 또 조회한 것은 아니다. 연결된 원시 결과·점수·TensorBoard를 새로 검증하지 않았다.

이슈에 관련 근거가 있다는 사실을 해결·인수·진행률로 바꾸지 않는다. #6 CI 실패와 worker cleanup의 caller가 다르고, optional RL/V2/Gemini 및 reference 대조는 현재 HIGH 전체의 인수가 아니라는 경계를 유지했다.

## Research

연구 담당은 CHORUS v1, CommCP v1, Planned synchronization 출판 원문의 선택된 절을 직접 읽고 관측 권한·학습/실행·통신 baseline·성공 기준·전이 범위를 비교했다. 정확한 URL·버전·읽은 절·게재 상태의 확인 수준은 [1차 근거](primary-sources.md)에 보존했다.

### Geometry scope

독립 geometry 검토자는 CHORUS와 synchronization 원문 및 최종 비교·제안의 범위를 읽었다. Partial credit, local observation/shared training, central planning/decentralized execution, 정지·재보정과 관측의 혼합을 구분했다. Masked 동일 행동이 내부 미사용의 증명이 아니고, 제안한 observer 대조는 belief·RNG·receipt·반복 이력을 함께 고정해야 한다는 정밀화를 확인했다.

### Statistical scope

독립 evaluation 검토자는 CommCP의 calibration label·option confidence·membership 사건과 관측수 대조를 원문에서 확인했다. 이를 메시지 사실 정확도·episode 성공·현재 UGRP의 확률 보증으로 확대하지 않는 해석을 수용했다. Frozen request의 메시지 교체는 조건을 만족하는 실제 발행 후보가 있을 때만 구성하는 별도 진단이며 원래 inbox나 폐루프 효과로 승격하지 않는다.

세 probe는 모두 제안만 있고 미실행이다. 새 physics/render/model/학습·raw 분석·코드 변경은 없으며 문헌을 구현 성능 증거로 세지 않는다.

## Provenance

기존 source와 원고 13개·1–18차 본문을 보존했다. GitHub는 canonical Markdown, Mac은 상세 QA·metadata 및 저자 원문 byte를 `.txt`로 추가 보관한다. 이 source 원문의 상대 링크는 원래 review workspace 기준이므로 탐색은 canonical 문서와 reproduction-notes를 사용한다. 기존 Mac에만 있는 최초 원문은 경로를 명시했고, 없는 GitHub 파일로 연결하지 않는다.
