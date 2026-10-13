# 참고 자료 (2026-10-14 확인)
- Gerkey & Matarić (2004), [MRTA 분류](https://journals.sagepub.com/doi/10.1177/0278364904045564): 독립적인 최단거리 선택과 팀의 충돌 없는 배정은 다른 문제다. 이 작업은 두 끝의 상호 배타 배정이 필요하다.
- Choi/Brunet/How, [MIT CBBA 설명·공개 MATLAB 코드](https://acl.mit.edu/projects/consensus-based-bundle-algorithm): 후보 비용 계산과 통신을 통한 중복 배정 해소를 분리한다. [저자 코드](https://acl.mit.edu/files/CBBA_MATLAB_ACLMIT_July13_2010.zip) 저자 코드 CBBA_BundleAdd.m·CBBA_Communicate.m을 직접 확인: 비용 비교 후 같은 점수는 robot ID로 해결하고 수신 메시지의 최신성을 확인한다. 구조화 경매 메시지를 통신 없음/NL 조건에 추가하지 않는다.
- Groß & Dorigo, [Group transport](https://iridia.ulb.ac.be/supp/IridiaSupp2008-021/index.html): 로컬 관측으로 이동·부착을 정하는 고전 사례. 자기조립 결합 물리는 우리 파지 구현에 이식하지 않는다.
- [Cooperative Object Transportation using Gibbs Random Fields (2021)](https://arxiv.org/abs/2109.13734): 국소 상호작용과 명시적 통신 없는 운반. 우리 두 집게 역할 분리가 검증됐다는 근거는 아니다.
- [ConPoSe (2025)](https://arxiv.org/html/2510.08705v1): 기하 후보 생성, LLM과 국소 탐색의 접촉점 선택, 재선택을 분리한다. 물체·로봇 상태가 제공되는 pushing 설정이므로 우리 자기 RGB 제약에 그대로 성능을 승계할 수 없다. 논문은 코드 공개 예정이라고 명시하며 실제 공개 저장소는 미확인.

적용: 코드는 자기 관측의 끝 후보·비용·점유 근거만 만들고, 판단과 메시지는 같은 LLM 호출에서 나온다. 무통신/모델 실패는 고정 규칙과 자기 RGB 점유 검사로 처리하고 결과를 LLM 결과와 분리한다. 한 번 선택한 물리 끝은 후속 B 방향 변화만으로 뒤집지 않으며, 점유 때문에 바꿀 때도 새 자기 관측과 선택 기록을 남긴다.
