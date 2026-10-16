# llmhost — GCP L4 자체 판단 VLM 시험 준비 (2026-10-16)

상태: **GPU 미사용 준비 / 실제 모델 추론 NOT_RUN / 기본 판단 모델 유지**.
사용자 승인 범위는 GPU 없이 준비하고, 조정자 승인 뒤 빈 L4에서 시험하는 것이다.
현재 할당량 1과 warp3·warp4·warp5·beamact3 공유 현황은 사용자 제공 조건이다.
본 작업의 읽기 전용 조회에서 `ugrp-act-l4-gcp2`는 RUNNING,
`g2-standard-8`, L4 1개, 140 GB 디스크, 28,800초 STOP 상한,
서비스 계정 없음이었다. 실행·정지·사양·할당량·예산 장치는 변경하지 않았다.
CPU gcp2의 기존 `reloc21`, `warp4` 임대를 확인했고 정지하지 않는다.

## 후보와 서빙 선택

**vLLM 0.25.1을 첫 시험 엔진으로 준비**한다. 공식 지원표에
`Gemma4ForConditionalGeneration`의 이미지 입력이 있고, 양자화 표에는
Ada(SM89)의 AWQ/GPTQ/Marlin이 있다([지원표](https://docs.vllm.ai/en/v0.25.1/models/supported_models/),
[양자화 하드웨어](https://docs.vllm.ai/en/latest/features/quantization/)).
실제 컨테이너는 Docker Registry에서 조회한 digest로 고정했다:
`vllm/vllm-openai@sha256:e4f88a835143cd22aee2397a26ec6bb80b3a4a6fe0c882bcbc63822904766089`
(`v0.25.1` 태그). 이미지 manifest의 존재를 확인했으며 pull·로딩은 미실행이다.
모델과 모든 파일의 고정 revision·크기·SHA는
[`configs/llmhost.json`](../../configs/llmhost.json)에 있다.

| 시험 후보 | 출처 / 고정 revision | 실제 가중치 크기 | 양자화 / 비전 | L4 판정 |
|---|---|---:|---|---|
| 31b_awq | `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` / `a3b96c7a8d07cc84cae0f0261ac2574310b12d37` | 19,188,422,752 B (17.87 GiB) | AWQ W4A16 비대칭, group128, compressed-tensors, 비전 BF16 | 짧은 문맥 시험 후보; KV·이미지 작업 공간까지 들어가는지는 미검증 |
| 26b_a4b_awq | `axteam/gemma-4-26B-A4B-it-AWQ-4bit` / `c688a48cf07a3c80edb4fec7d4e9fe04f6a8ca40` | 17,567,255,396 B (16.36 GiB) | AWQ W4A16 비대칭, group32, compressed-tensors, 비전·라우터·공유 MLP BF16 | 전체 expert 가중치를 적재해야 함; 4B만 메모리에 올리는 모델이 아님 |

두 후보는 **비공식 PTQ 미러**이며 원본 Google·DeepInfra fp4와 동일 모델 조건으로
합산하지 않는다. 미러 작성자의 비전 보존 설명과 실제 config를 대조했다
([31B 작성자 모델 카드](https://huggingface.co/ebircak/gemma-4-31B-it-4bit-W4A16-AWQ),
[26B 작성자 모델 카드](https://huggingface.co/axteam/gemma-4-26B-A4B-it-AWQ-4bit)).
모델 출력 품질·한국어 판단 정확도·자기 RGB 인식 정확도는 미측정이다.

Google 공식 31B QAT W4A16-CT도 조사했다. Hub 메타데이터의 가중치가
23,265,352,448 B(21.67 GiB)여서 L4의 실제 가용 메모리와 KV·비전 공간을
고려하면 첫 시험에는 여유가 부족하다. 원본 BF16 31B/26B도 단일 L4에 부적합하다.
공식 NVFP4 레시피는 Blackwell을 요구하므로 **그 레시피를 L4에 그대로 쓰지 않는다**.
일부 Marlin FP4 경로의 Ada 지원과 특정 Gemma NVFP4 전체 모델 로딩의 검증은
구분해야 한다([Google QAT](https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct),
[vLLM 31B 레시피](https://recipes.vllm.ai/Google/gemma-4-31B-it)).
GPTQ도 Ada 지원 후보지만 이번에 선택한 두 artifact는 AWQ다.

SGLang은 OpenAI Vision API와 기본 Radix prefix cache를 제공한다.
다만 확인한 공식 multimodal 지원 문서에는 Gemma 3이 있고 Gemma 4의
동일 양자화·L4 조합을 확정할 근거가 부족하여 이번 실행 스크립트는 vLLM만 만든다.
SGLang을 검증됐다고 표시하지 않는다
([multimodal 모델](https://docs.sglang.io/docs/supported-models/multimodal_language_models),
[OpenAI API](https://docs.sglang.io/docs/basic_usage/openai_api),
[Radix 옵션](https://docs.sglang.io/docs/advanced_features/server_arguments)).

서빙은 `127.0.0.1:8000`, OpenAI `/v1/chat/completions`, 이미지 1장 필수,
`--enable-prefix-caching`, thinking off, 기본 영상 processor를 사용한다.
`--quantization compressed-tensors`가 artifact 형식과 맞으며 `awq` schema로
강제로 해석하지 않는다. 8,192 token은 첫 용량 시험 설정으로 원문을 자르는 옵션이
아니다. 40개 전체 입력(이미지 token 포함)+출력 상한이 이 안에 드는지 실행 전에
확인해야 하며 넘으면 거부를 기록한다. OOM을 CPU offload·다른 GPU로 자동 우회하지 않는다.
`--gpu-memory-utilization 0.90`은 공식 레시피 값, eager는 CUDA graph의 추가
메모리를 피하는 첫 기동 선택이다. 이 선택의 속도는 미측정이다.

## 처리량·시간 예상의 근거와 한계

[NVIDIA L4 사양](https://www.nvidia.com/en-gb/data-center/l4/)은 24 GB와 300 GB/s다.
31B dense의 순수 INT4 가중치만 `31e9×0.5/300e9=0.0517 s/token`,
약19.4 token/s가 되는 **단일 스트림 대역폭 계산**을 참고한다. 실제 파일 크기를
모두 한 번 읽는 가정이면 약15.6 token/s다. 이는 측정치·속도 보장·엄밀한 상한이
아니다(비전은 매 decode마다 전부 읽지 않고, 일부 텐서는 BF16이며, kernel·KV·연산 비용과
배치 재사용을 생략했다). 출력 50/100 token이라면 이 단순 계산의 decode만 약2.6–6.4초이고
이미지 prefill·서버 대기·네트워크가 더해진다. 따라서 기존 API 중앙값이나 8초 조건을
통과한다고 미리 주장할 수 없다. prefix cache는 공통 입력 prefill만 줄이고 decode를
줄이지 않는다([vLLM APC](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/)).

26B-A4B는 활성 약4B를 모두 INT4로 읽는 단순 가정에 `2 GB/300 GB/s≈6.7 ms`,
약150 token/s지만, 공유층 BF16·expert 분산 접근·라우팅·연산을 생략하므로 이 값을
실제 예상 처리량으로 사용하지 않는다. 공개 공식 자료에서 **이 두 artifact + L4 +
자기 RGB + 해당 길이**의 응답 지연 benchmark는 찾지 못했다.
40회/분, 출력100 token이면 aggregate 66.7 token/s가 필요하므로 실제 배치와 KV 용량을
함께 재야 한다. 26B가 더 빠를 가능성은 가설이며 모델 변경은 사용자 결정이다.

40회 open-loop dispatch는 **58.5초 + 마지막 응답**이다. 각 HTTP transport watchdog은
기존 relay와 같은 180초여서 최장 약4분이다(행동 선택/탐색 시간 상한과 별개).
가중치·컨테이너가 L4에 준비된 뒤 첫 cold load·이미지 초기화에 5–20분을 계획 여유로
두되 아직 실측 근거가 없고, 건강 확인이 20분을 넘으면 중단한다. 두 모델은 순차로 재며
모델별 summary·비용을 분리한다. 최초 가중치/컨테이너 전송은 별도이며 이 예상에 포함하지 않는다.

## 가중치 확보·자격 증명 경계

두 미러의 Hub metadata는 `gated=false`다. 토큰 없이 고정 revision을 사용한다.
Mac 여유 약16 GiB, CPU gcp2 여유 약209 GB를 확인했다. 전체 두 모델 약36.82 GB를
Mac에 임시 저장할 공간이 부족하여 **Mac 수신→8 MiB 조각 SHA→SSH→CPU gcp2**로
순서대로 보낸다. 수신기는 각 조각과 전체 SHA·크기를 확인한 뒤 `.part`를 게시한다.
전체 SHA는 Hub LFS SHA와도 맞아야 한다. 데이터만 VM으로 보내며 HF·모델·Kaggle·
에이전트 자격 증명, Mac의 HF cache 폴더는 보내지 않는다.

```sh
python3 -m scripts.llmhost_weights 31b_awq --stage --output outputs/llmhost/weights-31b
python3 -m scripts.llmhost_weights 26b_a4b_awq --stage --output outputs/llmhost/weights-26b
```

CPU 원본 경로는
`gcp2:/home/ugrp/ugrp-sim/llmhost/models/<candidate>/<revision>/`다.
Mac·receiver 대조 manifest와 조각 해시는 해당 `outputs/llmhost/weights-*/`에 쓴다.
완료 여부는 `manifest.json.completed`로 판정한다. `.part`나 `mac-verified.json`의
부분 결과를 완료로 세지 않는다. 중단 시 완료된 파일은 보존하며 같은 목적지에 덮어쓰지 않는다.
새 기록으로 재개할 때는 원본 전체 해시 검증을 다시 해야 한다.

게이트 모델로 바뀌면 Mac의 기존 HF 로그인을 `--gated`로 읽는 코드 경로를 사용한다.
토큰은 HTTPS 헤더에만 쓰고 argv·기록·VM에 넣지 않는다. 모델 ID/revision/기본 모델 변경은
이 작업이 자동 결정하지 않는다. GCS는 필요하면 Mac에서만 인증하여 **이 프로젝트 소유의
비공개 bucket**으로 업로드하고 재다운로드 SHA를 확인하는 대안이다. 이번 준비는 VM 직접
전송을 선택했으며 bucket 생성·공개 URL·VM 서비스 계정 부착은 하지 않았다
([HF 고정 revision 다운로드](https://huggingface.co/docs/huggingface_hub/guides/download)).

## 기본 off 중계·보호 장치

- [`llmhost_ctl.py`](../../scripts/llmhost_ctl.py): plan/status/start/stop/tunnel.
  모든 gcloud 호출은 `--account changmin5781@gmail.com --project ugrp-sim-b-1014`를 붙인다.
  기존 L4만 쓰며 새 GPU VM 생성·할당량 요청·첫 GCP 프로젝트 접근은 없다.
- start에는 조정자가 발급한 만료 시각·후보·독점 GPU·budget clear를 담은 승인 JSON이 필요하다.
  활성 endpoint 경보·기존 임대·GPU PID·다른 Python/MuJoCo/ffmpeg가 있으면 거부한다.
  8h STOP·서비스 계정 없음·기존 idle timer와 Docker 권한을 검사한다.
  `us-central1/budget-stop` 함수 ACTIVE·`stop_on_budget`·gcp2 topic은 읽기 조회로 확인했다.
  함수·예산·Pub/Sub·기존 유휴 종료 장치는 수정하지 않는다.
- L4가 비고 승인됐을 때만 CPU 가중치를 Mac 경유로 L4에 전달하고 다시 전체 해시를 확인한다.
  50 GiB 저장 예산 여유를 보존한다. 컨테이너·모델 load는 그 뒤다.
- guest worker는 `/home/ugrp/ugrp-sim/leases/llmhost.json`에 작업/PID/시작/예상 종료를 쓴다.
  systemd의 8h RuntimeMaxSec, worker 자체 8h 및 **실제 요청/대기 activity가 없는 20분** 종료를
  둔다. 상주 vLLM process 자체를 활동으로 보지 않는다. 종료 원장은 cap_end/idle/HOST_ERROR를
  구분하며 process group과 자기 이름의 container만 정리한다. stop은 **VM을 정지하지 않는다**.
- [`s4_proxy_relay.py`](../../scripts/s4_proxy_relay.py)의
  `--upstream self_gcp_l4 --self-gcp-candidate 31b_awq --driver-profile study_gemma4_31b_v1`로만
  켠다. 기본 선택·registry·`configs/model_endpoints.json`은 유지한다. 모델·양자화·revision·
  provider·이미지 SHA를 identity/ledger에 남기고 fallback·model key를 사용하지 않는다.
  실제 E2E 연결·이미지 모델 해석은 미검증이며 benchmark는 응답 journal을 거치지 않는다.

**현재 활성 경보:** Mac `outputs/model-endpoint-alerts/last-alerts.json`에 DeepInfra 가격
completion 0.34→0.51, prompt 0.09→0.135, cache read 0.05→0.075 경보가 있었다.
조정자가 원인과 모델 공급 결정을 처리하고 경보가 해소될 때까지 새 LLM batch를 내지 않는다.
이 준비는 경보 파일 삭제·기준 가격 변경·공급자 교체를 하지 않는다.

## llmalt 동일 비교와 승인 후 한 줄

llmalt worktree는 확인 시 깨끗했고, 현재 시험용 40요청 manifest/측정 산출물은 아직
찾지 못했다. 실제 비교는 **동일 40파일·순서·SHA·이미지**, 동일 출력 상한·temperature·
thinking 정책으로 한다. 다른 저장 요청 40개를 대신 골라 동일 비교라고 주장하지 않는다.

```sh
# llmalt가 정한 실제 40개 원본을 같은 순서로 전달한다(이미지 data URI 포함).
python3 -m scripts.llmhost_benchmark prepare --corpus-id llmalt-40 --output outputs/llmhost/corpus.json <40개_요청_JSON_경로>

# 조정자 승인 + 경보 해소 + 빈 L4 + 가중치 준비 뒤 실행할 한 줄(지금 미실행).
python3 -m scripts.llmhost_trial --candidate 31b_awq --corpus outputs/llmhost/corpus.json --coordinator-approval /tmp/llmhost-approval.json --output outputs/llmhost/trial-31b-01 --hourly-usd "$LLMHOST_G2_USD_PER_HOUR" --rate-source "$LLMHOST_RATE_SOURCE"
```

승인 JSON 예시(지금 발급·승인된 파일은 없음):
`{"task":"llmhost","candidate":"31b_awq","approved":true,"gpu_exclusive":true,"budget_stop_clear":true,"expires_unix":<조정자가_정한_시각>}`.
26B는 같은 명령에서 후보와 새 output만 바꾼다. trial은 터널·health·40회·자기 unit 종료까지
묶으며 재시작 루프는 없다. 분리된 운영 명령은
`python3 -m scripts.llmhost_ctl status` / `stop`이다.

비용 입력은 **Seoul STANDARD g2-standard-8 전체 VM의 실제 시간당 USD**와 확인 출처/시각이다.
[공식 accelerator VM 가격표](https://cloud.google.com/products/compute/pricing/accelerator-optimized)를
지역·소비 모드별로 다시 확인하여 채운다. Spot·다른 지역·GPU 단품 가격을 쓰지 않는다.
지역 확정 요율을 아직 확보하지 못해 임의 숫자를 기본값으로 넣지 않았다.
`benchmark_wall_s/3600×hourly_usd`와 첫 준비·전송·기동·종료를 포함한 trial wall 비용을
따로 기록하고 디스크·전송·세금은 별도로 표시한다. 크레딧으로 실제 현금 청구가 0이어도
사용 자원 비용을 0으로 만들지 않는다.

산출물은 성공/40, 모든 요청의 latency·중앙값·8초 초과·429·형식 거부·HOST_ERROR·
이미지 SHA 전달·usage cached/prompt token 비율·server prefix counter 차분과 원본 응답이다.
cache usage 미제공은 `null` 및 coverage로 표시한다. prefix KV cache와 response journal
재생을 분리한다. image 전달은 wire 바이트 검증이며 semantic image use는 별도 관문이다.
`finish_reason=length` 등 정상 stop이 아닌 응답은 비용·기록은 남기되 성공으로 세지 않는다.
funnel은 HTTP→model identity→stop+act JSON 순서 누적 통과/거부와 재현 명령을 남긴다.
LLM act 형식 성공은 로봇 과제 정확도·운반·실물 성공이 아니다.

## 검증·관문 기록

CPU 전용 테스트는 `tests/test_llmhost.py`, 기존 `tests/test_openrouter_upstream.py`다.
프레이밍 실제 subprocess 왕복, 조각 해시 손상 시 원본 게시 금지/임대 정리,
기본 off·GPU 명령·계정/프로젝트·8h·승인 만료·경보 차단·자기 RGB 바이트 보존·
length 거부·캐시 미측정·비용 산식·중계 identity 변경 거부를 검사한다.
최종 24 passed(0.74초). CI shard 목록에도 새 시험 파일이 포함됨을 확인했다.
물리·렌더·GPU·실제 모델 호출은 0이다. GPU runtime/메모리/engine/kernel/idle 정지는
실제로 검증하지 않았으며 mock/CPU 검사로 대체하여 성공을 선언하지 않는다.

[`preparation-funnel.json`](preparation-funnel.json)과 [`queue.json`](queue.json)에
승인 전의 순차 관문·미완료 사유·원본·재현 명령을 기록한다.
대기열의 `rejection_table`은 이 checkout의 파일 절대경로다. 다른 checkout으로 옮기면
그 경로를 다시 생성해야 하며 없는 파일을 승인하지 않는다. 이번 작업은 로봇 제어기나
실행기 관측/행동/영상 기록을 바꾸지 않으므로 SIM 노드 상한과 실패 전10 Hz ring buffer의
제어기 요구를 새로 구현할 범위가 아니다. 서빙/호스트 watchdog은 별개로 8h/20분이다.

## 참고 자료

2026-10-16 웹/Hub/Registry 읽기 조회. 아래는 공식 문서 또는 artifact 작성자 원문이다.

1. [vLLM 0.25.1 지원 모델](https://docs.vllm.ai/en/v0.25.1/models/supported_models/): Gemma4 이미지 입력.
2. [vLLM 31B 레시피](https://recipes.vllm.ai/Google/gemma-4-31B-it), [26B-A4B 레시피](https://recipes.vllm.ai/Google/gemma-4-26B-A4B-it): OpenAI image API·vision·NVFP4 하드웨어·배치 설정. L4 실측으로 전용하지 않음.
3. [vLLM quantization](https://docs.vllm.ai/en/latest/features/quantization/): Ada AWQ/GPTQ/Marlin 표.
4. [vLLM prefix cache](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/): prefill 재사용·decode 한계.
5. [vLLM metrics](https://docs.vllm.ai/en/latest/usage/metrics/): `/metrics`, prefix hit/query counter.
6. [Google Gemma4 모델 카드](https://huggingface.co/google/gemma-4-31B-it), [공식 QAT](https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct): 원본 능력·별도 QAT artifact. 원본 점수를 PTQ 품질로 옮기지 않음.
7. [31B AWQ 작성자](https://huggingface.co/ebircak/gemma-4-31B-it-4bit-W4A16-AWQ), [26B AWQ 작성자](https://huggingface.co/axteam/gemma-4-26B-A4B-it-AWQ-4bit): 비공식 양자화 방법·비전 보존·배포 형식. 작성자 주장과 우리 검증을 구분.
8. [SGLang multimodal](https://docs.sglang.io/docs/supported-models/multimodal_language_models), [server arguments](https://docs.sglang.io/docs/advanced_features/server_arguments): OpenAI vision과 기본 Radix. Gemma4 L4 조합 확인 부족.
9. [NVIDIA L4](https://www.nvidia.com/en-gb/data-center/l4/): 24 GB, 300 GB/s. 속도 수치는 추론 계산으로만 사용.
10. [HF download](https://huggingface.co/docs/huggingface_hub/guides/download): revision 고정·Mac 로그인 경로.
11. [GCP G2 사양](https://docs.cloud.google.com/compute/docs/gpus/), [가격](https://cloud.google.com/products/compute/pricing/accelerator-optimized): 전체 VM 요율을 실제 지역·모드에 맞춰 기록.
