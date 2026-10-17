# mapbuild11 재현·원본

원본 호스트는 gcp5(ugrp-sim-e-1016, changmin5781@gmail.com), source는 cfdcd88450b8bef8730dfdec1fa8e3baa67ede7f다. 새 물리1라운드/최대2녹화를 모두 사용했고 다음 큐는 submit=false다. 아래는 실행·분석 이력의 재현 명령이며 이번 작업에서 추가 실행을 예약하지 않았다.

## 원본과 요약

- 녹화1: `/home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded`, HOST_ERROR/저장0프레임.
- 녹화2: `/home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded-v2`, 2026프레임/202.5 SIM초, 원래 JSON9개는 SHA 검증한 .zst로 보존. `own-rgb` r1/r2 4052파일과 eval-state.npz 유지.
- 실행 로그·명령·큐·preflight: `/home/ugrp/ugrp-sim/ops-reviews/mapbuild11/long-recording2/`.
- 봉인 예측·수치·모델별 funnel: 위 `score/`. 예측파일 SHA `5af88a5b8339878299697578893dc4ec123298059f3353316789eb8d87c20ad0`, 오차파일 SHA `a7b0728ed6a575f5a946cd5a7bca6b6b77f58c9825f124dd300e00977898039a`.
- R3 MC20: `/home/ugrp/ugrp-sim/ops-reviews/mapbuild11/paired-r3-v2/`; 원본 자체는 `runs/mapbuild10-mc20/{own-streams.json.zst,priors.json}` 및 두 과거 predictions 폴더. 코드의 첫 v3 경로 오류는 v2로 고쳤고 실패 종료 영수증도 보존했다.
- CPU 후처리 source22293978afb486e7d188d4d2d0f57e6eec17625a: `/home/ugrp/ugrp-sim/src/mapbuild11-analysis-22293978a`; 도구는 `mapbuild11_plots.py`, `mapbuild11_playback.py`. 기존 source snapshot은 모두 git-shared.git을 직접 참조한 clone이며 gc/prune하지 않았다.

## 실제 녹화 명령

실행기의 실제 queue는 `operations/final-gcp5/queue-physical.json`이다. source pin/SOURCE_FILES, 입력 해시·이전 funnel·공개 상자·정적 지도·teacher class를 확인한 뒤 preflight와 실제 실행을 분리했다. 실제 인자는 [recorded-command.json](recorded-command.json)에 적었다. 첫 시도 의존 파일 누락은 전체 tracked source를 복원하고 camera modules()를 실제로 불러 확인한 뒤 교체했다. 소스·필터·설정은 recording2 동안 고정했다. 예산/유휴 장치를 변경하지 않았고 모든 gcloud에 대상 account/project를 명시했다.

## 원본 VM CPU에서 오프라인 재생

기존 물리 환경의 NumPy2.5.2/SciPy1.17.1로 predict를 수행했다. 별도 그림은 기존 분석 환경의 NumPy2.2.6/SciPy1.18.1/Matplotlib3.11.2에서, 봉인된 수치를 바꾸지 않고 작성했다. 재계산 오차는0이고 원래 온라인 default 제안 재생도2026프레임 최대 차0이었다. [환경 기록](operations/final-gcp5/environment.json)은 열거한 패키지의 버전이며 전체 dependency lock은 아니다.

큰 JSON은 재생에 앞서 **원래 VM에서만** 대응 `.json.zst`를 `zstd -d --keep <파일>`로 원래 바이트에 복원하고 COMPRESSED.jsonl의 원본 SHA와 비교한다. 압축 원본을 덮어쓰지 않는다. 아래 OUTPUT은 매번 새 폴더다. 물리·렌더는 실행하지 않는다.

```sh
cd /home/ugrp/ugrp-sim/src/mapbuild11-cfdcd8845
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python scripts/mapbuild11_long.py \
  --stage predict \
  --input /home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded-v2 \
  --output OUTPUT \
  --calibration /home/ugrp/ugrp-sim/ops-reviews/mapbuild9/own-noise-command-r1-r2.json \
  --requirements experiments/2026-10-17-mapbuild8/requirements.json
```

이 predict 과정은 평가파일을 열지 않는다. prediction-seal을 확인한 뒤 같은 명령에서 `--stage score`로 평가한다(그림을 함께 만들려면 matplotlib이 설치된 기존 analysis Python 사용). 물리 환경에는 matplotlib이 없어서 최초 score는 수치 JSON을 저장한 뒤 그림 import에서 실패했다. 기록된 수치의 봉인은 그 뒤에도 그대로다. 이후 아래 helper가 실제로 그림2개·모델 funnel을 완성했다.

```sh
/home/ugrp/ugrp-rl1b-act-env/bin/python \
  /home/ugrp/ugrp-sim/src/mapbuild11-analysis-22293978a/scripts/mapbuild11_plots.py \
  --input /home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded-v2 \
  --score /home/ugrp/ugrp-sim/ops-reviews/mapbuild11/long-recording2/score
/home/ugrp/ugrp-rl1b-act-env/bin/python \
  /home/ugrp/ugrp-sim/src/mapbuild11-analysis-22293978a/scripts/mapbuild11_playback.py \
  --input /home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded-v2 \
  --output NEW_PLAYBACK_FOLDER
```

기존 분석 환경의 처음 matplotlib 누락도 보존했다. 물리 종료 뒤 그 환경에 `python -m pip install matplotlib`로3.11.2와 의존성5개를 추가했고, 물리 환경에는 설치·업데이트하지 않았다. 설치 로그를 보존했다. [공식 설치/비대화형 backend](https://matplotlib.org/stable/install/index.html).

R3 계측은 같은 cfd 소스에서 다음을 실행했다. raw 파서가 .zst를 지원한다. 선행 queue의 replay 검사와 전후 과거 예측의 frame-by-frame 동일성을 함께 확인했다.

```sh
PYTHONPATH=. /home/ugrp/ugrp-rl1b-act-env/bin/python scripts/mapbuild11_compare.py \
  --output NEW_PAIRED_R3_FOLDER
```

초기 default와 field의 같은168개 수렴 소실 갱신은 paired-frames의 `(trial,frame_id)`로 join하고, old.converged=true/new.converged=false로 골랐다. 그 후 `xy_pass`, `coupled_pass`, `ess_pass`를 직접 센다. yaw 증분 진단은 `wrap(motion_delta.yaw - between(평가 직전 자세, 평가 현재 자세).yaw)`를 phase/fusion별 합산한 것이다. GT로 필터·noise·명령 모델을 맞추는 코드가 아니다.

## 스택·원본·회수 확인

기존 checker와 고정 XML을 그대로 쓰고, 규칙 파일만 commit8a6a4917f의 heading enum alias를 포함한 것으로 재검사했다. `on`과 source DEFAULT `path_tangent_v1`만 같은 값이고 `off`/crab/unknown은 계속 deviation이다. [차단 전후 두 결과](operations/final-gcp5/runtime-stack-heading-alias.json). 새로운 사용자 결정이나 제어 변경이 아니다.

기록 원본4078파일/RGB4052 및 source16772파일·예측 입력11파일 검증은 representative grade 선택 전에 수행했다. RUN_META만 dev→milestone(대표 실패 진단 증거)으로 올리며 원래 bytes를 RUN_META.initial.json에 보존했다. 초기 전체 manifest는 압축 상태로, 이후 전체 inventory는 TSV로 따로 보존했다. [이력](operations/final-gcp5/metadata-evolution.json). 원본 payload/봉인 예측/오차/요약은 바뀌지 않았다.

표준 `scripts/compress_json_traces.py <raw1> <raw2> <ops> --execute`로 EXIT-complete 자료만 압축했다. 15파일의 압축·해제 SHA를 재검사했고 총153879106bytes를 절약했다. [압축 이력](operations/final-gcp5/compression-log.json), [회수48파일 검증](operations/retrieval-verification.json). 전체 raw를 Mac으로 가져오지 않았다.

## 영상·라이선스

자기 r1/r2 원본 JPEG를 ffmpeg hstack/scale/drawtext/tile로 묶었다. TOP/overview 입력은 없다. 전체2Hz406쌍, 종료192.5–202.5초10Hz101쌍, 회전112.8–123.7초10Hz110쌍을 직접 봤다. 마지막 회전 띠는 tile110칸을 채운 실제 범위를 표기했다. 영상 확인은 ffprobe만 사용했고 화면 앱을 열지 않았다. 4배속 대표 파일736907bytes/50.9초, 원래 검토본2297874bytes. 인코딩 명령/해시는 [추가 media 기록](operations/final-gcp5/additional-media.json), 전체는 [playback manifest](operations/final-gcp5/playback-manifest.json)에 있다.

기존 Nav2 코드/포트의 [LGPL-2.1-or-later 고지](../../harness/mapbuild_amcl_vendor/NOTICE.md)와 upstream/COPYING은 유지했다. 이번에는 필터·정합기·vendor 알고리즘을 새로 만들거나 바꾸지 않았다.
