# BoxNet1·BoxNet2 원저작물

Yongchao Chen 외의 ICRA 2024 논문(arXiv 2309.15943)에서 공개한 BoxNet1 환경을 사용했다. 공개 코드 저장소 이름은 `multi-agent-framework`이고, 기준 커밋은 `024221d36d520db67a8ee4e19f755789056255fa`다. [논문](https://arxiv.org/abs/2309.15943)

`env1-box-arrange.py`, `env1_create.py`, `prompt_env1.py`는 원 코드를 이 실험에 맞게 바꾼 파일이다. `fixtures/upstream/`에는 회귀 시험과 BoxNet2 시험이 참조하는 같은 커밋의 원본 다섯 파일이 있다. `env2_create.py`와 `prompt_env2.py`는 BoxNet2 원본이며 같은 커밋의 바이트와 같다. 변경 내역과 원본 SHA-256은 실험 보고서에 있다. [REPORT-CHEN2D.md](REPORT-CHEN2D.md)

Copyright (c) 2024 Yongchao Chen. MIT License. [LICENSE](LICENSE)
