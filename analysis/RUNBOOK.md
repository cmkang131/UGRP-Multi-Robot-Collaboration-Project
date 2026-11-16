# 본 실험 분석 RUNBOOK (collect → analyze → figures)
저장소 루트에서 시작한다. 변수 `DIR`/`DIRB` = 본 묶음/기준선 묶음 디스패처 작업 폴더(`state.json` 이 있는 곳, 동결 때 확정), `NAME` = 출력 이름, `RES`/`RESB` = collect 가 결과를 모으는 폴더, `M` = 매니페스트 폴더. 아래 `collect` 단계는 작업 VM 에 접속하므로 `batch/README.md` 의 환경 변수(`SSH_KEY`, `VM_USER`, `VM1_IP_FILE`, `VM2_IP_FILE`)가 필요하다.
```
R=$(pwd); S=$R/scenes; N=main-$(date +%m%d)
SC="--scenes $S/scenes_designed_v2.json --scenes $S/scenes_coop.json"; DIR=<본 디스패치 폴더>; DIRB=<기준선 디스패치 폴더>; RES=<본 결과 폴더>; RESB=<기준선 결과 폴더>; M=<매니페스트 폴더>
python3 -B batch/collect.py --dir $DIRB --results $RESB && python3 -B batch/collect.py --dir $DIR --results $RES && cd analysis && python3 -B analyze_main.py --runs $RESB --runs $RES $SC --manifest $M/baseline40.csv --manifest $M/core-main308.csv --name $N && python3 -B make_figures.py --name $N
```
- 일부만 끝난 중간 점검이면 `analyze_main.py` 에 `--interim`(안 끝난 칸을 뺌), 그림에는 `--note "중간 점검, 결과 아님"`. 빼면 안 끝난 칸은 실패(0)로 센다.
- 기준선은 `baseline40.csv`(BASE2-*). `core.csv` 의 BASE-* 줄은 실제로 안 돌렸으면 같이 넣으면 안 끝난 기준선 40칸이 더해진다(`core-main308.csv` 는 그것을 뺀 308줄). `batch/make_manifest.py --preset all --baseline-first` 는 `confirm2.csv`·`core.csv`·`optional.csv` 를 만든다. `baseline40.csv` 와 `core-main308.csv` 는 `core.csv` 의 앞 baseline 40줄과 나머지 308줄을 나누고 동결 값(sha, VM 스크립트, 기준선 이름 `BASE2-*`)으로 고쳐 만든 것이며 이 저장소에는 없다.
- 선택 묶음(무작위 등)을 돌렸으면 `--manifest $M/optional.csv`, `--scenes $S/scenes_random_v2.json`, `--oracle-group random_baseline` 을 analyze 줄에 더한다. 두 번째 모델·3대·팀장 교대 팔은 mainA 와 합쳐 검정하지 않는다(팔마다 따로 나온다).
- 출력: `out/$N/{summary.md,cells.csv,tests.json}` 와 `out/$N/figures/fig_a..e_*.svg` + `figures.json`(그린 숫자). matplotlib 이 있으면 .pdf, 없으면 .svg(`--backend svg` 로 강제).
- 점검: `cd analysis && python3 -B -m unittest test_analyze_main test_compare test_make_figures`(85개), summary.md 맨 아래 `경고`·`장면을 못 읽은 칸` 표가 비어 있는지, 1절 칸 현황의 진행·미시작이 0 인지 본다.
- 기록: collect 는 재시도한 run 의 마지막 시도만 가져오므로 첫 시도 기록은 results 에 없다(VM 에 남아 있는지는 확인 안 됨; PREREG 7절 "둘 다 남긴다"와 다름).

## 계획기 정지 칸 다시 돌리기
묶음이 끝나면 `python3 batch/rerun_halted.py --manifest <매니페스트> --evidence <EVIDENCE_DIR> --out <rerun.csv>` 로 `halted` 가 남은 칸(종료 코드 0 이라 디스패처가 안 다시 돌림)을 `<id>-rr1` 로 뽑아 dispatch 로 1회 돌린다. analyze_main 은 첫 시도가 고장(failed·running)이면 rr1 을 쓴다(PREREG 7).
