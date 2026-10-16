# 20차 독립 검증

## CI source and status

별도 검토자가 네 pin의 workflow·runner·session wrapper·target test 16개 Git source hash와 AST를 대조했다. API reported head와 실제 PR merge checkout을 구분하고 target AST 동일성을 dependency·실행환경 전체 동일성으로 확대하지 않았다.

공식 읽기에서 #6 open, PR5 merged/closed, 과거 같은 reported-head push success, 현재 main b23 run의 33개 job success를 확인했다. 최근 main 8개 목록은 저자의 metadata 범위이며 독립 QA가 전체 목록을 또 조회한 것은 아니다. 과거 해당 assertion과 checkout 세 줄은 제공된 제한 발췌만 읽었다. JUnit·개별 test artifact·연구 outcome·전체 로그를 다시 검증하지 않았다.

현재 선택 경로가 존재하고 최근 main CI가 정상이라는 사실과 원래 실패의 원인·수정 여부를 분리했다. Returncode assertion이 stderr 수집보다 먼저여서 진단 한계가 남는다는 source 해석은 지지되지만 새 cleanup 결함으로 세지 않았다. CI나 process fixture를 새로 실행하지 않았다.

## Randomization

별도 evaluation 검토자가 #213 요구와 #216 최종 OpenCV 선택을 공식 기록에서 확인하고, 26개 snapshot을 exact main/#363/#371 Git object와 대조했다. Script/source를 새 임시 폴더에 복사해 NumPy와 표준 라이브러리만으로 재현했으며 결과 SHA `229196f0258598afd8ce6f3ae091c34dfb7720c150bf7eca483918d654a9b40d`가 원본과 바이트 동일했다.

동일 appearance seed의 결정성, 명시 seed 변경, 코드의 held-out 설계 RGB와 평균색 간격, authored XML에서 light 방향·camera 속성 보존을 확인했다. 이 값은 실제 영상 거리·일반화·성능 효과가 아니다. U/log-U는 거절 전 proposal이며 최종 look은 반올림·거리 거절 뒤 선택한 값으로 정밀화했다.

Appearance seed와 pose seed, replay-floor recolor 확률과 전체 augmentation, validation/BN의 augment=False, HIGH OpenCV와 #371 기본 worker의 분리를 source로 확인했다. 실제 split 독립성·시험 소모 횟수·현재 실험 성능은 감사하지 않았다.

## Delivery

새 버그 집계 0개. 기존 원고 13개와 1–19차 본문을 보존하고, GitHub는 판정 Markdown만 추가한다. Mac은 source/status metadata·한정된 인프라 발췌·작은 재현·golden·선택된 exact source 26개·상세 QA를 보존한다. 실행 snapshot은 전체 repository나 실제 학습 데이터가 아니다. 재현 방법과 저자 source/canonical 파일명의 구분은 evidence의 reproduction-notes를 따른다.
