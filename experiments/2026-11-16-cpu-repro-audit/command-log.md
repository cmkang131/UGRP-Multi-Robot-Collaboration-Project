# CPU 재현 점검: 명령과 실제 출력

기준 소스: `ca954d9fa64f94303a3f645c265aff85e2af2fce`. 날짜: 2026-11-16 (Asia/Seoul).

재현·진단 명령의 stdout/stderr와 종료 코드를 보존했다. `<checkout>`은 새 체크아웃, `<audit-dir>`은 그 밖의 기록 폴더, `<python-runtime>`은 호스트 Python 설치 위치다. 절대경로를 위 표기로 치환하고 표시용 줄 끝 공백을 정리했으며 오류·수치·종료 상태는 변경하지 않았다. GitHub 조회와 코드 읽기는 실행 성공으로 집계하지 않았다.

외부 기록기는 자식 프로세스의 stdout/stderr를 합쳐 파일로 받았다. 제한에 도달하면 해당 기록기가 시작한 프로세스 그룹만 종료하고 `124`를 기록했다. 이는 실험기의 성공·실패 판정값이 아니다. KST 시작 시각과 wall 시간은 기록용이며 성능 비교가 아니다.

## 최초 접근

현재 저장소의 첫 `git ls-remote ... HEAD refs/heads/main` 시도는 HTTP 503으로 실패했고 같은 주소 재시도는 성공했다. 이 일시적 네트워크 실패를 저장소 결함으로 이슈화하지 않았다.

```json
{
  "timestamp": "2026-11-16T03:18:03.530748+00:00",
  "argv": [
    "gh",
    "repo",
    "clone",
    "kcm0127-dotcom/ugrp"
  ],
  "cwd": "<audit-dir>",
  "returncode": 4,
  "stdout": "",
  "stderr": "To get started with GitHub CLI, please run:  gh auth login\nAlternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.\n"
}
```

```json
{
  "timestamp": "2026-11-16T03:18:03.645109+00:00",
  "argv": [
    "python3.12",
    "--version"
  ],
  "cwd": "<audit-dir>",
  "returncode": 0,
  "stdout": "Python 3.12.14\n",
  "stderr": ""
}
```

## 새 체크아웃

```text
$ git clone --depth 1 --branch main --single-branch https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git ugrp-clean
Cloning into 'ugrp-clean'...
Updating files:  50% (8205/16361)
Updating files:  51% (8345/16361)
Updating files:  52% (8508/16361)
Updating files:  53% (8672/16361)
Updating files:  54% (8835/16361)
Updating files:  55% (8999/16361)
Updating files:  56% (9163/16361)
Updating files:  57% (9326/16361)
Updating files:  58% (9490/16361)
Updating files:  59% (9653/16361)
Updating files:  60% (9817/16361)
Updating files:  61% (9981/16361)
Updating files:  62% (10144/16361)
Updating files:  63% (10308/16361)
Updating files:  64% (10472/16361)
Updating files:  65% (10635/16361)
Updating files:  66% (10799/16361)
Updating files:  67% (10962/16361)
Updating files:  68% (11126/16361)
Updating files:  69% (11290/16361)
Updating files:  70% (11453/16361)
Updating files:  71% (11617/16361)
Updating files:  72% (11780/16361)
Updating files:  73% (11944/16361)
Updating files:  74% (12108/16361)
Updating files:  75% (12271/16361)
Updating files:  76% (12435/16361)
Updating files:  77% (12598/16361)
Updating files:  78% (12762/16361)
Updating files:  79% (12926/16361)
Updating files:  80% (13089/16361)
Updating files:  81% (13253/16361)
Updating files:  82% (13417/16361)
Updating files:  83% (13580/16361)
Updating files:  84% (13744/16361)
Updating files:  85% (13907/16361)
Updating files:  86% (14071/16361)
Updating files:  87% (14235/16361)
Updating files:  88% (14398/16361)
Updating files:  89% (14562/16361)
Updating files:  90% (14725/16361)
Updating files:  91% (14889/16361)
Updating files:  92% (15053/16361)
Updating files:  93% (15216/16361)
Updating files:  94% (15380/16361)
Updating files:  95% (15543/16361)
Updating files:  95% (15681/16361)
Updating files:  96% (15707/16361)
Updating files:  97% (15871/16361)
Updating files:  98% (16034/16361)
Updating files:  99% (16198/16361)
Updating files: 100% (16361/16361)
Updating files: 100% (16361/16361), done.

exit_code=0

```

## 01-venv

- 시작: 2026-11-16T12:19:05.782258+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 1.719 s
- 기록기 상한: 60.0 s; 상한 종료: `false`

```text
$ python3.12 -m venv .venv-dev

exit_code=0

```

## 02-upgrade-pip

- 시작: 2026-11-16T12:19:12.920574+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 18.841 s
- 기록기 상한: 180.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -m pip install --upgrade pip
Requirement already satisfied: pip in ./.venv-dev/lib/python3.12/site-packages (25.0.1)
Collecting pip
  Downloading pip-26.3-py3-none-any.whl.metadata (4.6 kB)
Downloading pip-26.3-py3-none-any.whl (2.0 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.0/2.0 MB 23.5 MB/s eta 0:00:00
Installing collected packages: pip
  Attempting uninstall: pip
    Found existing installation: pip 25.0.1
    Uninstalling pip-25.0.1:
      Successfully uninstalled pip-25.0.1
Successfully installed pip-26.3

exit_code=0

```

## 03-install-readme

- 시작: 2026-11-16T12:19:26.318680+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 33.95 s
- 기록기 상한: 240.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -m pip install -r requirements-sim.txt -r requirements-test.txt
Collecting mujoco==3.12.0 (from -r requirements-sim.txt (line 7))
  Downloading mujoco-3.12.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (232 kB)
Collecting numpy==2.5.2 (from -r requirements-sim.txt (line 8))
  Downloading numpy-2.5.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (6.6 kB)
Collecting opencv-python-headless==5.0.0.93 (from -r requirements-sim.txt (line 9))
  Downloading opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl.metadata (19 kB)
Collecting pillow==12.3.0 (from -r requirements-sim.txt (line 10))
  Downloading pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (9.1 kB)
Collecting websockets==15.0.1 (from -r requirements-sim.txt (line 11))
  Downloading websockets-15.0.1-cp312-cp312-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.8 kB)
Collecting glfw==2.10.2 (from -r requirements-sim.txt (line 12))
  Downloading glfw-2.10.2-py2.py3-none-manylinux_2_28_x86_64.whl.metadata (5.5 kB)
Collecting PyOpenGL==3.1.10 (from -r requirements-sim.txt (line 13))
  Downloading pyopengl-3.1.10-py3-none-any.whl.metadata (3.3 kB)
Collecting scipy==1.17.1 (from -r requirements-test.txt (line 4))
  Downloading scipy-1.17.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (62 kB)
Collecting pytest==9.1.1 (from -r requirements-test.txt (line 6))
  Downloading pytest-9.1.1-py3-none-any.whl.metadata (7.6 kB)
Collecting stonesoup==1.7 (from -r requirements-test.txt (line 9))
  Downloading stonesoup-1.7-py3-none-any.whl.metadata (4.7 kB)
Collecting absl-py (from mujoco==3.12.0->-r requirements-sim.txt (line 7))
  Downloading absl_py-2.5.1-py3-none-any.whl.metadata (3.3 kB)
Collecting etils[epath] (from mujoco==3.12.0->-r requirements-sim.txt (line 7))
  Downloading etils-1.15.0-py3-none-any.whl.metadata (6.5 kB)
Collecting iniconfig>=1.0.1 (from pytest==9.1.1->-r requirements-test.txt (line 6))
  Downloading iniconfig-2.3.1-py3-none-any.whl.metadata (2.8 kB)
Collecting packaging>=22 (from pytest==9.1.1->-r requirements-test.txt (line 6))
  Downloading packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
Collecting pluggy<2,>=1.5 (from pytest==9.1.1->-r requirements-test.txt (line 6))
  Downloading pluggy-1.7.0-py3-none-any.whl.metadata (5.0 kB)
Collecting pygments>=2.7.2 (from pytest==9.1.1->-r requirements-test.txt (line 6))
  Downloading pygments-2.21.0-py3-none-any.whl.metadata (2.5 kB)
Collecting matplotlib (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading matplotlib-3.11.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (80 kB)
Collecting ordered-set (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading ordered_set-4.1.0-py3-none-any.whl.metadata (5.3 kB)
Collecting plotly>=5.0 (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading plotly-7.1.0-py3-none-any.whl.metadata (8.8 kB)
Collecting pymap3d (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading pymap3d-3.2.0-py3-none-any.whl.metadata (8.7 kB)
Collecting rtree (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading rtree-1.4.1-py3-none-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl.metadata (2.1 kB)
Collecting ruamel.yaml>=0.16.5 (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading ruamel_yaml-0.19.1-py3-none-any.whl.metadata (16 kB)
Collecting utm (from stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading utm-0.9.0-py3-none-any.whl.metadata (5.2 kB)
Collecting narwhals>=1.15.1 (from plotly>=5.0->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading narwhals-2.28.0-py3-none-any.whl.metadata (15 kB)
Collecting fsspec (from etils[epath]->mujoco==3.12.0->-r requirements-sim.txt (line 7))
  Downloading fsspec-2026.9.0-py3-none-any.whl.metadata (10 kB)
Collecting typing_extensions (from etils[epath]->mujoco==3.12.0->-r requirements-sim.txt (line 7))
  Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Collecting zipp (from etils[epath]->mujoco==3.12.0->-r requirements-sim.txt (line 7))
  Downloading zipp-4.1.2-py3-none-any.whl.metadata (3.6 kB)
Collecting contourpy>=1.0.1 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading contourpy-1.4.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (3.8 kB)
Collecting cycler>=0.10 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading cycler-0.12.1-py3-none-any.whl.metadata (3.8 kB)
Collecting fonttools>=4.28.2 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading fonttools-4.68.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (139 kB)
Collecting kiwisolver>=1.3.1 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading kiwisolver-1.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (5.2 kB)
Collecting pyparsing>=3 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading pyparsing-3.3.3-py3-none-any.whl.metadata (5.9 kB)
Collecting python-dateutil>=2.7 (from matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading python_dateutil-4.0.0-py3-none-any.whl.metadata (7.3 kB)
Collecting tzdata (from python-dateutil>=2.7->matplotlib->stonesoup==1.7->-r requirements-test.txt (line 9))
  Downloading tzdata-2026.6-py2.py3-none-any.whl.metadata (1.4 kB)
Downloading mujoco-3.12.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (19.8 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 19.8/19.8 MB 30.3 MB/s eta 0:00:00
Downloading numpy-2.5.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (16.7 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 16.7/16.7 MB 33.8 MB/s eta 0:00:00
Downloading opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl (61.2 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 61.2/61.2 MB 50.9 MB/s eta 0:00:00
Downloading pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (6.9 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 6.9/6.9 MB 60.8 MB/s eta 0:00:00
Downloading websockets-15.0.1-cp312-cp312-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl (182 kB)
Downloading glfw-2.10.2-py2.py3-none-manylinux_2_28_x86_64.whl (248 kB)
Downloading pyopengl-3.1.10-py3-none-any.whl (3.2 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.2/3.2 MB 19.8 MB/s eta 0:00:00
Downloading scipy-1.17.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (35.2 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 35.2/35.2 MB 45.5 MB/s eta 0:00:00
Downloading pytest-9.1.1-py3-none-any.whl (386 kB)
Downloading stonesoup-1.7-py3-none-any.whl (458 kB)
Using cached iniconfig-2.3.1-py3-none-any.whl (7.6 kB)
Using cached packaging-26.3-py3-none-any.whl (129 kB)
Downloading plotly-7.1.0-py3-none-any.whl (9.7 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 9.7/9.7 MB 34.8 MB/s eta 0:00:00
Using cached pluggy-1.7.0-py3-none-any.whl (27 kB)
Using cached pygments-2.21.0-py3-none-any.whl (1.3 MB)
Downloading ruamel_yaml-0.19.1-py3-none-any.whl (118 kB)
Downloading absl_py-2.5.1-py3-none-any.whl (137 kB)
Downloading matplotlib-3.11.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (9.9 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 9.9/9.9 MB 25.3 MB/s eta 0:00:00
Downloading ordered_set-4.1.0-py3-none-any.whl (7.6 kB)
Downloading pymap3d-3.2.0-py3-none-any.whl (64 kB)
Downloading rtree-1.4.1-py3-none-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (507 kB)
Downloading utm-0.9.0-py3-none-any.whl (8.6 kB)
Downloading contourpy-1.4.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (383 kB)
Downloading cycler-0.12.1-py3-none-any.whl (8.3 kB)
Downloading fonttools-4.68.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (5.4 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5.4/5.4 MB 34.3 MB/s eta 0:00:00
Downloading kiwisolver-1.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (1.5 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.5/1.5 MB 18.7 MB/s eta 0:00:00
Downloading narwhals-2.28.0-py3-none-any.whl (490 kB)
Downloading pyparsing-3.3.3-py3-none-any.whl (126 kB)
Downloading python_dateutil-4.0.0-py3-none-any.whl (92 kB)
Downloading etils-1.15.0-py3-none-any.whl (177 kB)
Downloading fsspec-2026.9.0-py3-none-any.whl (221 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Downloading zipp-4.1.2-py3-none-any.whl (10 kB)
Downloading tzdata-2026.6-py2.py3-none-any.whl (348 kB)
Installing collected packages: PyOpenGL, glfw, zipp, websockets, utm, tzdata, typing_extensions, ruamel.yaml, rtree, pyparsing, pymap3d, pygments, pluggy, pillow, packaging, ordered-set, numpy, narwhals, kiwisolver, iniconfig, fsspec, fonttools, etils, cycler, absl-py, scipy, python-dateutil, pytest, plotly, opencv-python-headless, contourpy, matplotlib, stonesoup, mujoco
Successfully installed PyOpenGL-3.1.10 absl-py-2.5.1 contourpy-1.4.0 cycler-0.12.1 etils-1.15.0 fonttools-4.68.0 fsspec-2026.9.0 glfw-2.10.2 iniconfig-2.3.1 kiwisolver-1.5.1 matplotlib-3.11.2 mujoco-3.12.0 narwhals-2.28.0 numpy-2.5.2 opencv-python-headless-5.0.0.93 ordered-set-4.1.0 packaging-26.3 pillow-12.3.0 plotly-7.1.0 pluggy-1.7.0 pygments-2.21.0 pymap3d-3.2.0 pyparsing-3.3.3 pytest-9.1.1 python-dateutil-4.0.0 rtree-1.4.1 ruamel.yaml-0.19.1 scipy-1.17.1 stonesoup-1.7 typing_extensions-4.16.0 tzdata-2026.6 utm-0.9.0 websockets-15.0.1 zipp-4.1.2

exit_code=0

```

## 04-solo-help

- 시작: 2026-11-16T12:19:51.719675+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `1`
- 실제 경과: 0.064 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python solo_pipeline/scripts/run_grasp_act_student.py --help
Traceback (most recent call last):
  File "<checkout>/solo_pipeline/scripts/run_grasp_act_student.py", line 26, in <module>
    _SOLO_APPEARANCE_SPEC.loader.exec_module(solo_appearance_v1)
  File "<frozen importlib._bootstrap_external>", line 995, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1132, in get_code
  File "<frozen importlib._bootstrap_external>", line 1190, in get_data
FileNotFoundError: [Errno 2] No such file or directory: '<checkout>/solo_pipeline/scripts/solo_appearance_v1.py'

exit_code=1

```

## 05-package-check

- 시작: 2026-11-16T12:20:24.633756+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.266 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -m pip check
No broken requirements found.

exit_code=0

```

## 06-quickstart-readme

- 시작: 2026-11-16T12:20:33.013622+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `1`
- 실제 경과: 0.265 s
- 기록기 상한: 120.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=osmesa CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 .venv-dev/bin/python scripts/ugrp_session.py run quickstart -- .venv-dev/bin/python -m scripts.sim_quickstart --output outputs/quickstart-01
UGRP session 'quickstart' started (pgid 6)
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "<checkout>/scripts/sim_quickstart.py", line 151, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "<checkout>/scripts/sim_quickstart.py", line 143, in main
    summary = run(args.output, seed=args.seed, seconds=args.seconds, frame_count=args.frames)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<checkout>/scripts/sim_quickstart.py", line 64, in run
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
  File "<checkout>/sim/multi_masterpi_production.py", line 25, in <module>
    import mujoco
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/mujoco/__init__.py", line 71, in <module>
    from mujoco.rendering.classic.renderer import Renderer  # pytype: disable=import-error
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/mujoco/rendering/classic/renderer.py", line 20, in <module>
    from mujoco.rendering.classic import gl_context
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/mujoco/rendering/classic/gl_context.py", line 38, in <module>
    from mujoco.osmesa import GLContext as _GLContext
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/mujoco/osmesa/__init__.py", line 31, in <module>
    from OpenGL import GL
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/OpenGL/GL/__init__.py", line 4, in <module>
    from OpenGL.GL.VERSION.GL_1_1 import *
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/OpenGL/GL/VERSION/GL_1_1.py", line 14, in <module>
    from OpenGL.raw.GL.VERSION.GL_1_1 import *
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/OpenGL/raw/GL/VERSION/GL_1_1.py", line 7, in <module>
    from OpenGL.raw.GL import _errors
  File "<checkout>/.venv-dev/lib/python3.12/site-packages/OpenGL/raw/GL/_errors.py", line 4, in <module>
    _error_checker = _ErrorChecker( _p, _p.GL.glGetError )
                                        ^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'glGetError'
UGRP session 'quickstart' stopped

exit_code=1

```

## 07-readme-regressions

- 시작: 2026-11-16T12:20:39.577793+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `124`
- 실제 경과: 240.002 s
- 기록기 상한: 240.0 s; 상한 종료: `true`

```text
$ env CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv-dev/bin/python scripts/run_ci_tests.py
Running 693 offline test modules (shard 0/1)
........................................................................ [  0%]
........................................................................ [  0%]
........................ssssssssssss...............................F.... [  1%]
........................................................................ [  1%]
............sFF......F..s.F.F..s.F...................................... [  2%]
................................................................... [  2%]
........................................................................ [  3%]
............................................................................................................................. [  4%]
............................................. [  4%]
........................................................................ [  5%]
........................................................................ [  5%]
........ [  5%]
........................................................................ [  6%]
........................................................................ [  6%]
........................................................................ [  7%]
..............EEEEEEEEEEEEEEEEEEEE...................................... [  7%]
.................................F.......................FF............. [  8%]
......................................................................F. [  8%]
..................F...........EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE [  9%]
EEEEEEEEE........EEEEE..E............................................... [  9%]
.EEEE.....EEEEEEEE...E..............E.................F.F............... [ 10%]
........................................................................ [ 10%]
..........................................
exit_code=124

```

## 08-quickstart-egl

- 시작: 2026-11-16T12:20:56.026243+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 12.354 s
- 기록기 상한: 120.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 .venv-dev/bin/python scripts/ugrp_session.py run quickstart-egl -- .venv-dev/bin/python -m scripts.sim_quickstart --output outputs/quickstart-egl-01
UGRP session 'quickstart-egl' started (pgid 6)
{"final_xy_m": [0.1969, 1.63147], "frame_count": 12, "initial_xy_m": [0.263447, 1.752991], "mode": "offline_deterministic_physics_demo", "ok": true, "outputs": {"animation": "quickstart.gif", "summary": "summary.json"}, "robot_displacement_m": 0.138548, "robot_id": "r1", "scope": "Physics motion and camera rendering only; no LLM, network, hardware, autonomous transport, or task-success validation.", "seed": 41, "simulated_time_s": 1.5}
UGRP session 'quickstart-egl' stopped

exit_code=0

```

## 09-renderer-info

- 시작: 2026-11-16T12:21:40.843651+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.368 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 .venv-dev/bin/python -c 'import json,mujoco; from OpenGL import GL; context=mujoco.GLContext(32,32); context.make_current(); print(json.dumps({"vendor":GL.glGetString(GL.GL_VENDOR).decode(),"renderer":GL.glGetString(GL.GL_RENDERER).decode(),"version":GL.glGetString(GL.GL_VERSION).decode()})); context.free()'
{"vendor": "Mesa", "renderer": "llvmpipe (LLVM 19.1.7, 256 bits)", "version": "4.5 (Compatibility Profile) Mesa 25.0.7-2+deb13u1"}

exit_code=0

```

## 10-cli-headless

- 시작: 2026-11-16T12:22:46.827995+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 5.266 s
- 기록기 상한: 120.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 bash scripts/open_simulation.command run configs/simulation/drive.json --headless --capture --output outputs/cpu-repro-drive-01
UGRP session 'simulation-native-5' started (pgid 12)
Output: <checkout>/outputs/cpu-repro-drive-01
Stopped: sim_limit | <checkout>/outputs/cpu-repro-drive-01/result.json
Simulation record: <checkout>/outputs/simulation-runs/20261116-122246-local-806e1a29/manifest.json
UGRP session 'simulation-native-5' stopped

exit_code=0

```

## 11-solo-release-download

- 시작: 2026-11-16T12:23:03.063743+09:00
- 작업 폴더: `<audit-dir>/release-solo-v1`
- 종료 코드: `0`
- 실제 경과: 16.018 s
- 기록기 상한: 180.0 s; 상한 종료: `false`

```text
$ curl --fail --location --silent --show-error --max-time 150 --remote-name https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/solo-v1-20261114/SHA256SUMS.txt --remote-name https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/solo-v1-20261114/solo-pipeline-code.zip --remote-name https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/solo-v1-20261114/solo-act-model-gseg-step4000.zip --write-out '%{filename_effective} %{http_code} %{size_download}\n'
SHA256SUMS.txt 200 271
solo-pipeline-code.zip 200 69389
solo-act-model-gseg-step4000.zip 200 207382468

exit_code=0

```

## 12-verifier-contract

- 시작: 2026-11-16T12:23:04.538407+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.064 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -c 'import json; from pathlib import Path; from scripts.run_gemini_seed_validation import command; from scripts.verify_gemini_budget_run import EXPECTED; argv=command(Path("outputs/not-executed"),45,"medium",60,"gemini-3.8-flash-high"); generated={"model":argv[argv.index("--model")+1],"noslip_iterations":int(argv[argv.index("--noslip-iterations")+1])}; print(json.dumps({"scope":"offline command generation only; no model call or simulated trial","generated_argv":argv,"mismatches":{k:{"generated":v,"verifier_expected":EXPECTED[k]} for k,v in generated.items() if v!=EXPECTED[k]}},indent=2))'
{
  "scope": "offline command generation only; no model call or simulated trial",
  "generated_argv": [
    "<checkout>/.venv-dev/bin/python",
    "-m",
    "scripts.evaluate_gemini_team",
    "--output",
    "outputs/not-executed",
    "--seed",
    "45",
    "--robots",
    "1",
    "--seconds",
    "300",
    "--model",
    "gemini-3.8-flash-high",
    "--max-calls",
    "30",
    "--max-input-tokens",
    "120000",
    "--input-request-estimate",
    "6000",
    "--impratio",
    "10",
    "--noslip-iterations",
    "0",
    "--communication",
    "none",
    "--request-timeout",
    "60",
    "--max-transient-failures",
    "2",
    "--reasoning-effort",
    "medium",
    "--record"
  ],
  "mismatches": {
    "model": {
      "generated": "gemini-3.8-flash-high",
      "verifier_expected": "gemini-3.8-flash"
    },
    "noslip_iterations": {
      "generated": 0,
      "verifier_expected": 3
    }
  }
}

exit_code=0

```

## 13-old-repo-remote

- 시작: 2026-11-16T12:23:19.423842+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 6.556 s
- 기록기 상한: 45.0 s; 상한 종료: `false`

```text
$ env GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/kcm0127-dotcom/ugrp.git HEAD
ca954d9fa64f94303a3f645c265aff85e2af2fce	HEAD

exit_code=0

```

## 14-headless-paused

- 시작: 2026-11-16T12:23:19.372471+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `2`
- 실제 경과: 0.717 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 bash scripts/open_simulation.command run configs/simulation/drive.json --paused --capture --headless --output outputs/cpu-repro-paused-01
UGRP session 'simulation-native-5' started (pgid 12)
Simulation record: <checkout>/outputs/simulation-runs/20261116-122319-local-1ddd37c0/manifest.json
sim: --paused requires the native viewer
UGRP session 'simulation-native-5' stopped

exit_code=2

```

## 15-release-checksums

- 시작: 2026-11-16T12:23:59.458160+09:00
- 작업 폴더: `<audit-dir>/release-solo-v1`
- 종료 코드: `0`
- 실제 경과: 0.666 s
- 기록기 상한: 45.0 s; 상한 종료: `false`

```text
$ python3 -c 'from pathlib import Path; import hashlib,json,zipfile; lines=Path("SHA256SUMS.txt").read_text().splitlines(); out=[]
for line in lines:
 expected,name=line.split(maxsplit=1); name=name.lstrip(" *"); path=Path(name)
 if path.exists():
  actual=hashlib.sha256(path.read_bytes()).hexdigest();out.append({"name":name,"bytes":path.stat().st_size,"expected_sha256":expected,"actual_sha256":actual,"matches":actual==expected})
  assert actual==expected
print(json.dumps(out,indent=2))
for name in ["solo-pipeline-code.zip","solo-act-model-gseg-step4000.zip"]:
 with zipfile.ZipFile(name) as z:
  print(name, "members:",json.dumps(z.namelist(),indent=2)); assert z.testzip() is None
  if name=="solo-pipeline-code.zip": print("contains_solo_appearance_v1:",any(x.endswith("solo_appearance_v1.py") for x in z.namelist()))'
[
  {
    "name": "solo-act-model-gseg-step4000.zip",
    "bytes": 207382468,
    "expected_sha256": "74b1213b07fcc3ec5cc286be3c44a310ebe2fea2d80ae2057c0b290977a4fea7",
    "actual_sha256": "74b1213b07fcc3ec5cc286be3c44a310ebe2fea2d80ae2057c0b290977a4fea7",
    "matches": true
  },
  {
    "name": "solo-pipeline-code.zip",
    "bytes": 69389,
    "expected_sha256": "79cb2365880cbca73a80c53f39fbcbc9df570c920f2df79695e0cfb1d5406575",
    "actual_sha256": "79cb2365880cbca73a80c53f39fbcbc9df570c920f2df79695e0cfb1d5406575",
    "matches": true
  }
]
solo-pipeline-code.zip members: [
  "solo_pipeline/",
  "solo_pipeline/scripts/",
  "solo_pipeline/scripts/run_grasp_act_student.py",
  "solo_pipeline/scripts/grasp_act_student_worker.py",
  "solo_pipeline/README.md",
  "solo_pipeline/harness/",
  "solo_pipeline/harness/grasp_act_inference.py",
  "solo_pipeline/harness/grasp_act_contract.py",
  "solo_pipeline/harness/grasp_act_input.py",
  "solo_pipeline/harness/approach_survey_v1.py",
  "solo_pipeline/harness/grasp_act_rollout.py",
  "solo_pipeline/harness/grasp_act_policy.py",
  "solo_pipeline/harness/seg_frontend_v1.py",
  "solo_pipeline/harness/release_table_v1.json",
  "solo_pipeline/harness/release_code_v1.py",
  "solo_pipeline/harness/approach_survey_v1_parts/",
  "solo_pipeline/harness/approach_survey_v1_parts/approach_core.py",
  "solo_pipeline/harness/approach_survey_v1_parts/ground_projection.py",
  "solo_pipeline/harness/approach_survey_v1_parts/face_align.py",
  "solo_pipeline/harness/approach_survey_v1_parts/survey_observe.py"
]
contains_solo_appearance_v1: False
solo-act-model-gseg-step4000.zip members: [
  "actor/",
  "actor/config.json",
  "actor/adapter.json",
  "actor/SHA256.json",
  "actor/model.safetensors"
]

exit_code=0

```

## 16-cohort-exit-diagnostic

- 시작: 2026-11-16T12:24:25.472355+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.215 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -c 'import runpy,sys,tempfile; from pathlib import Path; from unittest.mock import patch; import scripts.evaluate_gemini_cohort as cohort
with tempfile.TemporaryDirectory(prefix="ugrp-audit-") as tmp:
 sys.argv=["scripts.run_gemini_seed_validation","--execute","--output",str(Path(tmp)/"trial"),"--seeds","45"]
 state={"status":"infrastructure_blocked","blocking_reason":"INFERENCE_UNAVAILABLE","scope":"synthetic offline diagnostic; not a research trial"}
 with patch.object(cohort,"run_cohort",return_value=state),patch("subprocess.run",side_effect=AssertionError("external execution forbidden in this diagnostic")):
  runpy.run_module("scripts.run_gemini_seed_validation",run_name="__main__")'
{"status": "infrastructure_blocked", "blocking_reason": "INFERENCE_UNAVAILABLE", "scope": "synthetic offline diagnostic; not a research trial"}

exit_code=0

```

## 17-complete-history

- 시작: 2026-11-16T12:24:51.864363+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 64.474 s
- 기록기 상한: 180.0 s; 상한 종료: `false`

```text
$ git fetch --unshallow origin main
From https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project
 * branch              main       -> FETCH_HEAD

exit_code=0

```

## 18-regressions-first-failure

- 시작: 2026-11-16T12:26:05.550775+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `1`
- 실제 경과: 111.057 s
- 기록기 상한: 180.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTEST_ADDOPTS=-x .venv-dev/bin/python scripts/run_ci_tests.py
Running 693 offline test modules (shard 0/1)
........................................................................ [  0%]
........................................................................ [  0%]
........................ssssssssssss.................................... [  1%]
........................................................................ [  1%]
............sF
=================================== FAILURES ===================================
_________ test_close_never_executes_before_both_READY_GO_ACK_and_delay _________

    def test_close_never_executes_before_both_READY_GO_ACK_and_delay():
>       barrier=sync();students={r:StudentBarrier() for r in ('r1','r2')}
                ^^^^^^

tests/test_beamact2.py:26:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/test_beamact2.py:20: in sync
    raw=subprocess.check_output(['git','show',DEPENDENCY_SHA+':harness/grasp_act_start_sync.py'],text=True)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<python-runtime>/lib/python3.12/subprocess.py:466: in check_output
    return run(*popenargs, stdout=PIPE, timeout=timeout, check=True,
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

input = None, capture_output = False, timeout = None, check = True
popenargs = (['git', 'show', '26f84d0f0ada1c33473c83cca2d3415ce51bd247:harness/grasp_act_start_sync.py'],)
kwargs = {'stdout': -1, 'text': True}

    def run(*popenargs,
            input=None, capture_output=False, timeout=None, check=False, **kwargs):
        """Run command with arguments and return a CompletedProcess instance.

        The returned instance will have attributes args, returncode, stdout and
        stderr. By default, stdout and stderr are not captured, and those attributes
        will be None. Pass stdout=PIPE and/or stderr=PIPE in order to capture them,
        or pass capture_output=True to capture both.

        If check is True and the exit code was non-zero, it raises a
        CalledProcessError. The CalledProcessError object will have the return code
        in the returncode attribute, and output & stderr attributes if those streams
        were captured.

        If timeout (seconds) is given and the process takes too long,
         a TimeoutExpired exception will be raised.

        There is an optional argument "input", allowing you to
        pass bytes or a string to the subprocess's stdin.  If you use this argument
        you may not also use the Popen constructor's "stdin" argument, as
        it will be used internally.

        By default, all communication is in bytes, and therefore any "input" should
        be bytes, and the stdout and stderr will be bytes. If in text mode, any
        "input" should be a string, and stdout and stderr will be strings decoded
        according to locale encoding, or by "encoding" if set. Text mode is
        triggered by setting any of text, encoding, errors or universal_newlines.

        The other arguments are the same as for the Popen constructor.
        """
        if input is not None:
            if kwargs.get('stdin') is not None:
                raise ValueError('stdin and input arguments may not both be used.')
            kwargs['stdin'] = PIPE

        if capture_output:
            if kwargs.get('stdout') is not None or kwargs.get('stderr') is not None:
                raise ValueError('stdout and stderr arguments may not be used '
                                 'with capture_output.')
            kwargs['stdout'] = PIPE
            kwargs['stderr'] = PIPE

        with Popen(*popenargs, **kwargs) as process:
            try:
                stdout, stderr = process.communicate(input, timeout=timeout)
            except TimeoutExpired as exc:
                process.kill()
                if _mswindows:
                    # Windows accumulates the output in a single blocking
                    # read() call run on child threads, with the timeout
                    # being done in a join() on those threads.  communicate()
                    # _after_ kill() is required to collect that and add it
                    # to the exception.
                    exc.stdout, exc.stderr = process.communicate()
                else:
                    # POSIX _communicate already populated the output so
                    # far into the TimeoutExpired exception.
                    process.wait()
                raise
            except:  # Including KeyboardInterrupt, communicate handled that.
                process.kill()
                # We don't call process.wait() as .__exit__ does that for us.
                raise
            retcode = process.poll()
            if check and retcode:
>               raise CalledProcessError(retcode, process.args,
                                         output=stdout, stderr=stderr)
E               subprocess.CalledProcessError: Command '['git', 'show', '26f84d0f0ada1c33473c83cca2d3415ce51bd247:harness/grasp_act_start_sync.py']' returned non-zero exit status 128.

<python-runtime>/lib/python3.12/subprocess.py:571: CalledProcessError
----------------------------- Captured stderr call -----------------------------
fatal: path 'harness/grasp_act_start_sync.py' does not exist in '26f84d0f0ada1c33473c83cca2d3415ce51bd247'
=========================== short test summary info ============================
FAILED tests/test_beamact2.py::test_close_never_executes_before_both_READY_GO_ACK_and_delay - subprocess.CalledProcessError: Command '['git', 'show', '26f84d0f0ada1c33473c83cca2d3415ce51bd247:harness/grasp_act_start_sync.py']' returned non-zero exit status 128.
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 288 passed, 17 skipped in 108.70s (0:01:48)

exit_code=1

```

## 19-proxy-guide-path

- 시작: 2026-11-16T12:27:20.786172+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.032 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -c 'from pathlib import Path; import subprocess; path="docs/gemini_subscription_proxy.md"; print("path:",path); print("exists:",Path(path).is_file()); print("tracked:",bool(subprocess.check_output(["git","ls-files","--",path],text=True).strip())); print("quickstart_references:",[(i,line.strip()) for i,line in enumerate(Path("docs/ubuntu_quickstart.md").read_text().splitlines(),1) if "gemini_subscription_proxy" in line])'
path: docs/gemini_subscription_proxy.md
exists: False
tracked: False
quickstart_references: [(91, '기본 데모와 테스트가 통과한 뒤 **[각자 PC에서 Gemini 로그인 프록시 설치](gemini_subscription_proxy.md)**를 따른다. 각 팀원이 본인 PC에서 서버를 실행하고 본인 Google 계정으로 로그인한다. 개발자 Mac이나 개발자 계정에 연결할 필요가 없다.')]

exit_code=0

```

## 20-complete-branch-refs

- 시작: 2026-11-16T12:28:52.768233+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 24.314 s
- 기록기 상한: 180.0 s; 상한 종료: `false`

```text
$ git fetch origin '+refs/heads/*:refs/remotes/origin/*'
From https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project
 * [new branch]          amend/gate-transition-measurement-20261025 -> origin/amend/gate-transition-measurement-20261025
 * [new branch]          archive/claude/e2e-bquad-20261014 -> origin/archive/claude/e2e-bquad-20261014
 * [new branch]          archive/claude/e2e-route-20261014 -> origin/archive/claude/e2e-route-20261014
 * [new branch]          archive/claude/e2e18-align-20261014 -> origin/archive/claude/e2e18-align-20261014
 * [new branch]          archive/claude/e2e18-perf-20261014 -> origin/archive/claude/e2e18-perf-20261014
 * [new branch]          archive/claude/e2e18-speedfix-20261014 -> origin/archive/claude/e2e18-speedfix-20261014
 * [new branch]          archive/hygiene-20261011-193431-codex-ci-split -> origin/archive/hygiene-20261011-193431-codex-ci-split
 * [new branch]          archive/hygiene-20261011-193431-loaded-rest-v104 -> origin/archive/hygiene-20261011-193431-loaded-rest-v104
 * [new branch]          archive/hygiene-20261011-193431-mapfree-explore -> origin/archive/hygiene-20261011-193431-mapfree-explore
 * [new branch]          archive/hygiene-20261011-193431-review-363 -> origin/archive/hygiene-20261011-193431-review-363
 * [new branch]          archive/hygiene-20261011-193431-review-371 -> origin/archive/hygiene-20261011-193431-review-371
 * [new branch]          archive/hygiene-20261011-193431-sim-speed -> origin/archive/hygiene-20261011-193431-sim-speed
 * [new branch]          archive/macprune-20261016-carry-ckpt -> origin/archive/macprune-20261016-carry-ckpt
 * [new branch]          archive/macprune-20261016-carry-diag -> origin/archive/macprune-20261016-carry-diag
 * [new branch]          archive/macprune-20261016-ego-wall-map -> origin/archive/macprune-20261016-ego-wall-map
 * [new branch]          archive/macprune-20261016-gcp-sim-host -> origin/archive/macprune-20261016-gcp-sim-host
 * [new branch]          archive/macprune-20261016-grasp-blind -> origin/archive/macprune-20261016-grasp-blind
 * [new branch]          archive/macprune-20261016-light-ext -> origin/archive/macprune-20261016-light-ext
 * [new branch]          archive/macprune-20261016-merge-train -> origin/archive/macprune-20261016-merge-train
 * [new branch]          archive/macprune-20261016-pf-consistency -> origin/archive/macprune-20261016-pf-consistency
 * [new branch]          archive/macprune-20261016-review-abort -> origin/archive/macprune-20261016-review-abort
 * [new branch]          archive/macprune-20261016-review-edge -> origin/archive/macprune-20261016-review-edge
 * [new branch]          archive/macprune-20261016-review-pcg -> origin/archive/macprune-20261016-review-pcg
 * [new branch]          archive/macprune-20261016-review-pcg2 -> origin/archive/macprune-20261016-review-pcg2
 * [new branch]          archive/macprune-20261016-rules-warp-all -> origin/archive/macprune-20261016-rules-warp-all
 * [new branch]          archive/macprune-20261016-simalt-pilot -> origin/archive/macprune-20261016-simalt-pilot
 * [new branch]          archive/macprune-20261016-warp-flows -> origin/archive/macprune-20261016-warp-flows
 * [new branch]          archive/pair-llm-v97-b201f777 -> origin/archive/pair-llm-v97-b201f777
 * [new branch]          archive/pair-llm-v99-ad1dda73 -> origin/archive/pair-llm-v99-ad1dda73
 * [new branch]          archive/wt-beam-bisect      -> origin/archive/wt-beam-bisect
 * [new branch]          archive/wt-beam-pair        -> origin/archive/wt-beam-pair
 * [new branch]          archive/wt-beam-pair-gate-b53183b7 -> origin/archive/wt-beam-pair-gate-b53183b7
 * [new branch]          archive/wt-beam-pair-gate-d79f04a3 -> origin/archive/wt-beam-pair-gate-d79f04a3
 * [new branch]          archive/wt-beam-pair-gate-e645b34b -> origin/archive/wt-beam-pair-gate-e645b34b
 * [new branch]          archive/wt-beam-pair-gate-f84b2c8a -> origin/archive/wt-beam-pair-gate-f84b2c8a
 * [new branch]          archive/wt-beampair-src-d79f04a3 -> origin/archive/wt-beampair-src-d79f04a3
 * [new branch]          archive/wt-beampair7        -> origin/archive/wt-beampair7
 * [new branch]          archive/wt-beampair8        -> origin/archive/wt-beampair8
 * [new branch]          archive/wt-claude-flaky-guard-20261003 -> origin/archive/wt-claude-flaky-guard-20261003
 * [new branch]          archive/wt-claude-v6d-align-20261003 -> origin/archive/wt-claude-v6d-align-20261003
 * [new branch]          archive/wt-claude-v6d-reg-20261003 -> origin/archive/wt-claude-v6d-reg-20261003
 * [new branch]          archive/wt-claude-v6e-carry-20261003 -> origin/archive/wt-claude-v6e-carry-20261003
 * [new branch]          archive/wt-claude-v6e-place-20261003 -> origin/archive/wt-claude-v6e-place-20261003
 * [new branch]          archive/wt-codex-ci-split-20261003 -> origin/archive/wt-codex-ci-split-20261003
 * [new branch]          archive/wt-crate-src-487579ea -> origin/archive/wt-crate-src-487579ea
 * [new branch]          archive/wt-crate-teacher    -> origin/archive/wt-crate-teacher
 * [new branch]          archive/wt-egojump          -> origin/archive/wt-egojump
 * [new branch]          archive/wt-gatesv5-beampair -> origin/archive/wt-gatesv5-beampair
 * [new branch]          archive/wt-gatesv5-release  -> origin/archive/wt-gatesv5-release
 * [new branch]          archive/wt-map-amcl         -> origin/archive/wt-map-amcl
 * [new branch]          archive/wt-map-selfmap      -> origin/archive/wt-map-selfmap
 * [new branch]          archive/wt-mergeprep-pr437  -> origin/archive/wt-mergeprep-pr437
 * [new branch]          archive/wt-mergeprep-pr440  -> origin/archive/wt-mergeprep-pr440
 * [new branch]          archive/wt-mergeprep-pr484  -> origin/archive/wt-mergeprep-pr484
 * [new branch]          archive/wt-mergeprep-pr493  -> origin/archive/wt-mergeprep-pr493
 * [new branch]          archive/wt-mergeprep-pr500  -> origin/archive/wt-mergeprep-pr500
 * [new branch]          archive/wt-mergeprep-pr505  -> origin/archive/wt-mergeprep-pr505
 * [new branch]          archive/wt-mergeprep-pr506  -> origin/archive/wt-mergeprep-pr506
 * [new branch]          archive/wt-mergeprep-pr507  -> origin/archive/wt-mergeprep-pr507
 * [new branch]          archive/wt-mergeprep-pr510  -> origin/archive/wt-mergeprep-pr510
 * [new branch]          archive/wt-mergeprep-pr522  -> origin/archive/wt-mergeprep-pr522
 * [new branch]          archive/wt-mergeprep-pr527  -> origin/archive/wt-mergeprep-pr527
 * [new branch]          archive/wt-mergeprep-pr532  -> origin/archive/wt-mergeprep-pr532
 * [new branch]          archive/wt-mergeprep-pr533  -> origin/archive/wt-mergeprep-pr533
 * [new branch]          archive/wt-mergeprep-pr536  -> origin/archive/wt-mergeprep-pr536
 * [new branch]          archive/wt-mergeprep-pr537  -> origin/archive/wt-mergeprep-pr537
 * [new branch]          archive/wt-mergeprep-pr538  -> origin/archive/wt-mergeprep-pr538
 * [new branch]          archive/wt-ops-release18-a3bbc90e -> origin/archive/wt-ops-release18-a3bbc90e
 * [new branch]          archive/wt-ops-release20-e897b0c2 -> origin/archive/wt-ops-release20-e897b0c2
 * [new branch]          archive/wt-release21-rec    -> origin/archive/wt-release21-rec
 * [new branch]          archive/wt-release21-src-46afd8b0 -> origin/archive/wt-release21-src-46afd8b0
 * [new branch]          archive/wt-release22-src-7fcbe7c9 -> origin/archive/wt-release22-src-7fcbe7c9
 * [new branch]          archive/wt-release22-src-9df35e49 -> origin/archive/wt-release22-src-9df35e49
 * [new branch]          archive/wt-release22-src-f4763385 -> origin/archive/wt-release22-src-f4763385
 * [new branch]          archive/wt-release25-base-check -> origin/archive/wt-release25-base-check
 * [new branch]          archive/wt-reloc16          -> origin/archive/wt-reloc16
 * [new branch]          archive/wt-reloc17          -> origin/archive/wt-reloc17
 * [new branch]          archive/wt-scene-tex2       -> origin/archive/wt-scene-tex2
 * [new branch]          archive/wt-search26-src-f92b07aa -> origin/archive/wt-search26-src-f92b07aa
 * [new branch]          archive/wt-view-egomap70    -> origin/archive/wt-view-egomap70
 * [new branch]          claude/act-crate-teacher    -> origin/claude/act-crate-teacher
 * [new branch]          claude/act-solo-teacher     -> origin/claude/act-solo-teacher
 * [new branch]          claude/act-train            -> origin/claude/act-train
 * [new branch]          claude/act16-analysis       -> origin/claude/act16-analysis
 * [new branch]          claude/act16w               -> origin/claude/act16w
 * [new branch]          claude/arm-disk-cleanup-rules-20261024 -> origin/claude/arm-disk-cleanup-rules-20261024
 * [new branch]          claude/backlog-disposition  -> origin/claude/backlog-disposition
 * [new branch]          claude/beam-pair-teacher    -> origin/claude/beam-pair-teacher
 * [new branch]          claude/beamact3c-evidence   -> origin/claude/beamact3c-evidence
 * [new branch]          claude/beamact5             -> origin/claude/beamact5
 * [new branch]          claude/beamact5-align       -> origin/claude/beamact5-align
 * [new branch]          claude/beamact5-align-a     -> origin/claude/beamact5-align-a
 * [new branch]          claude/beamact5-align-r     -> origin/claude/beamact5-align-r
 * [new branch]          claude/beamact5-e2ewarp-r4  -> origin/claude/beamact5-e2ewarp-r4
 * [new branch]          claude/beamact5-flake       -> origin/claude/beamact5-flake
 * [new branch]          claude/beamact5-flake-a     -> origin/claude/beamact5-flake-a
 * [new branch]          claude/beamact5-flake-r     -> origin/claude/beamact5-flake-r
 * [new branch]          claude/beamact5-flake2      -> origin/claude/beamact5-flake2
 * [new branch]          claude/beamact5-flake2-a    -> origin/claude/beamact5-flake2-a
 * [new branch]          claude/beamact5-flake2-r    -> origin/claude/beamact5-flake2-r
 * [new branch]          claude/beamact5-localdup    -> origin/claude/beamact5-localdup
 * [new branch]          claude/beamact5-r2-a        -> origin/claude/beamact5-r2-a
 * [new branch]          claude/beamact5-r2-r        -> origin/claude/beamact5-r2-r
 * [new branch]          claude/beamact5-r2-t        -> origin/claude/beamact5-r2-t
 * [new branch]          claude/beamact5-r4-a        -> origin/claude/beamact5-r4-a
 * [new branch]          claude/beamact5-r4-r        -> origin/claude/beamact5-r4-r
 * [new branch]          claude/beamact5-r4-t        -> origin/claude/beamact5-r4-t
 * [new branch]          claude/beampair7            -> origin/claude/beampair7
 * [new branch]          claude/beampair8            -> origin/claude/beampair8
 * [new branch]          claude/beampair9            -> origin/claude/beampair9
 * [new branch]          claude/bf16-training-precision -> origin/claude/bf16-training-precision
 * [new branch]          claude/busy-pasteur-lioq74  -> origin/claude/busy-pasteur-lioq74
 * [new branch]          claude/claude-md-reference-first -> origin/claude/claude-md-reference-first
 * [new branch]          claude/crossroom-carry      -> origin/claude/crossroom-carry
 * [new branch]          claude/deepseek-api-harness -> origin/claude/deepseek-api-harness
 * [new branch]          claude/deepseek-main-worker -> origin/claude/deepseek-main-worker
 * [new branch]          claude/drive-model-deadband -> origin/claude/drive-model-deadband
 * [new branch]          claude/drop-triframe        -> origin/claude/drop-triframe
 * [new branch]          claude/dsh-keep-claude-code -> origin/claude/dsh-keep-claude-code
 * [new branch]          claude/e2e-bcones           -> origin/claude/e2e-bcones
 * [new branch]          claude/e2e-bquad            -> origin/claude/e2e-bquad
 * [new branch]          claude/e2e-min-runner       -> origin/claude/e2e-min-runner
 * [new branch]          claude/e2e-route            -> origin/claude/e2e-route
 * [new branch]          claude/e2e18-align          -> origin/claude/e2e18-align
 * [new branch]          claude/e2e18-callrate       -> origin/claude/e2e18-callrate
 * [new branch]          claude/e2e18-gemma-planner  -> origin/claude/e2e18-gemma-planner
 * [new branch]          claude/e2e18-grasp-rootcause -> origin/claude/e2e18-grasp-rootcause
 * [new branch]          claude/e2e18-grasp1         -> origin/claude/e2e18-grasp1
 * [new branch]          claude/e2e18-jevmotion      -> origin/claude/e2e18-jevmotion
 * [new branch]          claude/e2e18-llmmemory      -> origin/claude/e2e18-llmmemory
 * [new branch]          claude/e2e18-perf           -> origin/claude/e2e18-perf
 * [new branch]          claude/e2e18-route1         -> origin/claude/e2e18-route1
 * [new branch]          claude/e2e18-speedfix       -> origin/claude/e2e18-speedfix
 * [new branch]          claude/e2e18-standoff       -> origin/claude/e2e18-standoff
 * [new branch]          claude/e2ewarp-visdet       -> origin/claude/e2ewarp-visdet
 * [new branch]          claude/egocentric-no-static-map -> origin/claude/egocentric-no-static-map
 * [new branch]          claude/egonav               -> origin/claude/egonav
 * [new branch]          claude/egonav-e2ewarp-mapcorr -> origin/claude/egonav-e2ewarp-mapcorr
 * [new branch]          claude/egonav-far           -> origin/claude/egonav-far
 * [new branch]          claude/egonav-mem           -> origin/claude/egonav-mem
 * [new branch]          claude/gcp-sim-host         -> origin/claude/gcp-sim-host
 * [new branch]          claude/gcp2-budget-2000     -> origin/claude/gcp2-budget-2000
 * [new branch]          claude/gcp2-host            -> origin/claude/gcp2-host
 * [new branch]          claude/grasp-act-probes     -> origin/claude/grasp-act-probes
 * [new branch]          claude/grasp-act-release    -> origin/claude/grasp-act-release
 * [new branch]          claude/han-32-instr-fix-20261028 -> origin/claude/han-32-instr-fix-20261028
 * [new branch]          claude/han-32-instr-fix-provenance-20261028 -> origin/claude/han-32-instr-fix-provenance-20261028
 * [new branch]          claude/l1lite-brief-format-20261024 -> origin/claude/l1lite-brief-format-20261024
 * [new branch]          claude/llmalt               -> origin/claude/llmalt
 * [new branch]          claude/llmnomap             -> origin/claude/llmnomap
 * [new branch]          claude/loaded-rest-v104     -> origin/claude/loaded-rest-v104
 * [new branch]          claude/map-amcl             -> origin/claude/map-amcl
 * [new branch]          claude/map-carry-zone       -> origin/claude/map-carry-zone
 * [new branch]          claude/map-selfmap          -> origin/claude/map-selfmap
 * [new branch]          claude/mapfree-explore      -> origin/claude/mapfree-explore
 * [new branch]          claude/mapfree-goal-floor   -> origin/claude/mapfree-goal-floor
 * [new branch]          claude/model-endpoint-watch -> origin/claude/model-endpoint-watch
 * [new branch]          claude/p2-seed-refs-wip     -> origin/claude/p2-seed-refs-wip
 * [new branch]          claude/planner-gemma-deepinfra -> origin/claude/planner-gemma-deepinfra
 * [new branch]          claude/release-record       -> origin/claude/release-record
 * [new branch]          claude/release25            -> origin/claude/release25
 * [new branch]          claude/reloc16              -> origin/claude/reloc16
 * [new branch]          claude/reloc17              -> origin/claude/reloc17
 * [new branch]          claude/reloc18              -> origin/claude/reloc18
 * [new branch]          claude/reloc19              -> origin/claude/reloc19
 * [new branch]          claude/reloc20              -> origin/claude/reloc20
 * [new branch]          claude/reloc21              -> origin/claude/reloc21
 * [new branch]          claude/rl-act               -> origin/claude/rl-act
 * [new branch]          claude/rules-1016           -> origin/claude/rules-1016
 * [new branch]          claude/rules-act-plan       -> origin/claude/rules-act-plan
 * [new branch]          claude/rules-analysis       -> origin/claude/rules-analysis
 * [new branch]          claude/rules-cache          -> origin/claude/rules-cache
 * [new branch]          claude/rules-code-default-1013 -> origin/claude/rules-code-default-1013
 * [new branch]          claude/rules-crate-colors   -> origin/claude/rules-crate-colors
 * [new branch]          claude/rules-decision-model-1013 -> origin/claude/rules-decision-model-1013
 * [new branch]          claude/rules-funnel         -> origin/claude/rules-funnel
 * [new branch]          claude/rules-gcp-main       -> origin/claude/rules-gcp-main
 * [new branch]          claude/rules-gcp2-walltex   -> origin/claude/rules-gcp2-walltex
 * [new branch]          claude/rules-held-hidden    -> origin/claude/rules-held-hidden
 * [new branch]          claude/rules-imitable-teacher -> origin/claude/rules-imitable-teacher
 * [new branch]          claude/rules-lookaround     -> origin/claude/rules-lookaround
 * [new branch]          claude/rules-mjwarp         -> origin/claude/rules-mjwarp
 * [new branch]          claude/rules-nocrate        -> origin/claude/rules-nocrate
 * [new branch]          claude/rules-noslip         -> origin/claude/rules-noslip
 * [new branch]          claude/rules-pairreview     -> origin/claude/rules-pairreview
 * [new branch]          claude/rules-pairreview-light -> origin/claude/rules-pairreview-light
 * [new branch]          claude/rules-planner-ling   -> origin/claude/rules-planner-ling
 * [new branch]          claude/rules-runfirst       -> origin/claude/rules-runfirst
 * [new branch]          claude/rules-speed          -> origin/claude/rules-speed
 * [new branch]          claude/rules-speedgate      -> origin/claude/rules-speedgate
 * [new branch]          claude/rules-stop-known-defect -> origin/claude/rules-stop-known-defect
 * [new branch]          claude/rules-success-first  -> origin/claude/rules-success-first
 * [new branch]          claude/rules-tokenrate      -> origin/claude/rules-tokenrate
 * [new branch]          claude/rules-topcam         -> origin/claude/rules-topcam
 * [new branch]          claude/rules-visible-only-teacher -> origin/claude/rules-visible-only-teacher
 * [new branch]          claude/rules-vm24           -> origin/claude/rules-vm24
 * [new branch]          claude/rules-warp-all       -> origin/claude/rules-warp-all
 * [new branch]          claude/rules-warp-all2      -> origin/claude/rules-warp-all2
 * [new branch]          claude/rules-watch-video    -> origin/claude/rules-watch-video
 * [new branch]          claude/scenario-v6-boxes    -> origin/claude/scenario-v6-boxes
 * [new branch]          claude/scene-floor-texture  -> origin/claude/scene-floor-texture
 * [new branch]          claude/scene-tex2           -> origin/claude/scene-tex2
 * [new branch]          claude/sim-speed            -> origin/claude/sim-speed
 * [new branch]          claude/simalt-pilot         -> origin/claude/simalt-pilot
 * [new branch]          claude/speed-gate-16x-1013  -> origin/claude/speed-gate-16x-1013
 * [new branch]          claude/stackgrep            -> origin/claude/stackgrep
 * [new branch]          claude/start-zone-prior     -> origin/claude/start-zone-prior
 * [new branch]          claude/team-recovery-longer-backoff -> origin/claude/team-recovery-longer-backoff
 * [new branch]          claude/v6h1-acceptance-run  -> origin/claude/v6h1-acceptance-run
 * [new branch]          claude/v6h1-confirm-run     -> origin/claude/v6h1-confirm-run
 * [new branch]          claude/visgoal              -> origin/claude/visgoal
 * [new branch]          claude/warp-act             -> origin/claude/warp-act
 * [new branch]          claude/warp-flows           -> origin/claude/warp-flows
 * [new branch]          claude/warp4                -> origin/claude/warp4
 * [new branch]          claude/warp5                -> origin/claude/warp5
 * [new branch]          claude/zone-dispatch-validation -> origin/claude/zone-dispatch-validation
 * [new branch]          cleanup/step1-personal-infra -> origin/cleanup/step1-personal-infra
 * [new branch]          cleanup/step2-dated-docs    -> origin/cleanup/step2-dated-docs
 * [new branch]          codex/act18                 -> origin/codex/act18
 * [new branch]          codex/act18-bf16-stack      -> origin/codex/act18-bf16-stack
 * [new branch]          codex/actdiag               -> origin/codex/actdiag
 * [new branch]          codex/advanced-rgb-clock-validation -> origin/codex/advanced-rgb-clock-validation
 * [new branch]          codex/advanced-rgb-validation -> origin/codex/advanced-rgb-validation
 * [new branch]          codex/archive-a3-fresh-audit-755dca3-0926 -> origin/codex/archive-a3-fresh-audit-755dca3-0926
 * [new branch]          codex/archive-a3-fresh-audit-de69eb3-0926 -> origin/codex/archive-a3-fresh-audit-de69eb3-0926
 * [new branch]          codex/archive-communication-observer-0926 -> origin/codex/archive-communication-observer-0926
 * [new branch]          codex/archive-dispatch-process-perception-0926 -> origin/codex/archive-dispatch-process-perception-0926
 * [new branch]          codex/archive-dispatch-top-pipeline-0926 -> origin/codex/archive-dispatch-top-pipeline-0926
 * [new branch]          codex/archive-pr137-main-integration-0926 -> origin/codex/archive-pr137-main-integration-0926
 * [new branch]          codex/archive-realtime-owner-commit-0926 -> origin/codex/archive-realtime-owner-commit-0926
 * [new branch]          codex/archive-realtime-stage-continuity-0926 -> origin/codex/archive-realtime-stage-continuity-0926
 * [new branch]          codex/archive-rgb-common-physical-recovery-0926 -> origin/codex/archive-rgb-common-physical-recovery-0926
 * [new branch]          codex/archive-wf-count-fix-20261006 -> origin/codex/archive-wf-count-fix-20261006
 * [new branch]          codex/baseline-resume-20261027 -> origin/codex/baseline-resume-20261027
 * [new branch]          codex/beamact1              -> origin/codex/beamact1
 * [new branch]          codex/beamact3              -> origin/codex/beamact3
 * [new branch]          codex/beamact3c             -> origin/codex/beamact3c
 * [new branch]          codex/beamact4              -> origin/codex/beamact4
 * [new branch]          codex/d0d1d2-diagnostic-20261027 -> origin/codex/d0d1d2-diagnostic-20261027
 * [new branch]          codex/d3-local-validation   -> origin/codex/d3-local-validation
 * [new branch]          codex/direct-gemini-api-key -> origin/codex/direct-gemini-api-key
 * [new branch]          codex/dispatch-adaptive-recovery -> origin/codex/dispatch-adaptive-recovery
 * [new branch]          codex/drivecheck            -> origin/codex/drivecheck
 * [new branch]          codex/e2e-idle              -> origin/codex/e2e-idle
 * [new branch]          codex/e2e-speed3            -> origin/codex/e2e-speed3
 * [new branch]          codex/e2e-speed4            -> origin/codex/e2e-speed4
 * [new branch]          codex/e2e-vomask            -> origin/codex/e2e-vomask
 * [new branch]          codex/e2e13-long            -> origin/codex/e2e13-long
 * [new branch]          codex/e2e18                 -> origin/codex/e2e18
 * [new branch]          codex/e2e18-end-assignment  -> origin/codex/e2e18-end-assignment
 * [new branch]          codex/e2e18-pose-diagnosis  -> origin/codex/e2e18-pose-diagnosis
 * [new branch]          codex/e2e18-teacher-pi-candidate -> origin/codex/e2e18-teacher-pi-candidate
 * [new branch]          codex/e2ewarp               -> origin/codex/e2ewarp
 * [new branch]          codex/ego-pose-continuity   -> origin/codex/ego-pose-continuity
 * [new branch]          codex/egomap70-overview     -> origin/codex/egomap70-overview
 * [new branch]          codex/egomem1               -> origin/codex/egomem1
 * [new branch]          codex/gcp3setup             -> origin/codex/gcp3setup
 * [new branch]          codex/gcp4setup             -> origin/codex/gcp4setup
 * [new branch]          codex/gcp5setup             -> origin/codex/gcp5setup
 * [new branch]          codex/gcp6setup             -> origin/codex/gcp6setup
 * [new branch]          codex/han-32-success-strict -> origin/codex/han-32-success-strict
 * [new branch]          codex/hard-maps             -> origin/codex/hard-maps
 * [new branch]          codex/integ-target-backend  -> origin/codex/integ-target-backend
 * [new branch]          codex/llmhost               -> origin/codex/llmhost
 * [new branch]          codex/local-gemini-proxy    -> origin/codex/local-gemini-proxy
 * [new branch]          codex/macprune              -> origin/codex/macprune
 * [new branch]          codex/main-study-prereg-draft -> origin/codex/main-study-prereg-draft
 * [new branch]          codex/mapbuild1             -> origin/codex/mapbuild1
 * [new branch]          codex/mast3rcmp             -> origin/codex/mast3rcmp
 * [new branch]          codex/merge-a               -> origin/codex/merge-a
 * [new branch]          codex/merge-train-453-final -> origin/codex/merge-train-453-final
 * [new branch]          codex/merge-train-453-record-binding-fix -> origin/codex/merge-train-453-record-binding-fix
 * [new branch]          codex/natural-floor-slam    -> origin/codex/natural-floor-slam
 * [new branch]          codex/nocap                 -> origin/codex/nocap
 * [new branch]          codex/noslip-off            -> origin/codex/noslip-off
 * [new branch]          codex/outputs-retention     -> origin/codex/outputs-retention
 * [new branch]          codex/pair-gpu-retry-gcp6-20261027 -> origin/codex/pair-gpu-retry-gcp6-20261027
 * [new branch]          codex/pair-grasp-endurance  -> origin/codex/pair-grasp-endurance
 * [new branch]          codex/pair-grasp-spacing    -> origin/codex/pair-grasp-spacing
 * [new branch]          codex/pair-loaded-navigation -> origin/codex/pair-loaded-navigation
 * [new branch]          codex/pair-terrain-examples -> origin/codex/pair-terrain-examples
 * [new branch]          codex/pair-transport-robustness -> origin/codex/pair-transport-robustness
 * [new branch]          codex/pair-vision-recovery  -> origin/codex/pair-vision-recovery
 * [new branch]          codex/plannerswap           -> origin/codex/plannerswap
 * [new branch]          codex/real-robot-link       -> origin/codex/real-robot-link
 * [new branch]          codex/repository-organization -> origin/codex/repository-organization
 * [new branch]          codex/review-292            -> origin/codex/review-292
 * [new branch]          codex/review-292b           -> origin/codex/review-292b
 * [new branch]          codex/review-293-294        -> origin/codex/review-293-294
 * [new branch]          codex/review-299            -> origin/codex/review-299
 * [new branch]          codex/review-299b           -> origin/codex/review-299b
 * [new branch]          codex/review-299c           -> origin/codex/review-299c
 * [new branch]          codex/review-299d           -> origin/codex/review-299d
 * [new branch]          codex/review-301            -> origin/codex/review-301
 * [new branch]          codex/review-301b           -> origin/codex/review-301b
 * [new branch]          codex/review-301c           -> origin/codex/review-301c
 * [new branch]          codex/review-301d           -> origin/codex/review-301d
 * [new branch]          codex/review-303c           -> origin/codex/review-303c
 * [new branch]          codex/review-303d           -> origin/codex/review-303d
 * [new branch]          codex/review-303e           -> origin/codex/review-303e
 * [new branch]          codex/review-303f           -> origin/codex/review-303f
 * [new branch]          codex/review-323b           -> origin/codex/review-323b
 * [new branch]          codex/review-325b           -> origin/codex/review-325b
 * [new branch]          codex/review-342            -> origin/codex/review-342
 * [new branch]          codex/review-344            -> origin/codex/review-344
 * [new branch]          codex/review-346            -> origin/codex/review-346
 * [new branch]          codex/review-347            -> origin/codex/review-347
 * [new branch]          codex/review-351            -> origin/codex/review-351
 * [new branch]          codex/review-352            -> origin/codex/review-352
 * [new branch]          codex/review-355            -> origin/codex/review-355
 * [new branch]          codex/review-356            -> origin/codex/review-356
 * [new branch]          codex/review-358            -> origin/codex/review-358
 * [new branch]          codex/review-360            -> origin/codex/review-360
 * [new branch]          codex/review-361            -> origin/codex/review-361
 * [new branch]          codex/review-362            -> origin/codex/review-362
 * [new branch]          codex/review-363            -> origin/codex/review-363
 * [new branch]          codex/review-e2e-batch-g    -> origin/codex/review-e2e-batch-g
 * [new branch]          codex/review-e2e-batch-h    -> origin/codex/review-e2e-batch-h
 * [new branch]          codex/review-e2e-batch-i    -> origin/codex/review-e2e-batch-i
 * [new branch]          codex/review-e2e-batch-j    -> origin/codex/review-e2e-batch-j
 * [new branch]          codex/review-e2e-batch-k    -> origin/codex/review-e2e-batch-k
 * [new branch]          codex/review-fixes-1        -> origin/codex/review-fixes-1
 * [new branch]          codex/review-fixes-2        -> origin/codex/review-fixes-2
 * [new branch]          codex/review-retention      -> origin/codex/review-retention
 * [new branch]          codex/review-seal-v6h1      -> origin/codex/review-seal-v6h1
 * [new branch]          codex/rgb-common-physical-recovery -> origin/codex/rgb-common-physical-recovery
 * [new branch]          codex/rgb-varied-start-tolerance -> origin/codex/rgb-varied-start-tolerance
 * [new branch]          codex/robot-clock-sync      -> origin/codex/robot-clock-sync
 * [new branch]          codex/s2-graduation         -> origin/codex/s2-graduation
 * [new branch]          codex/scenarios-v7-nocrate  -> origin/codex/scenarios-v7-nocrate
 * [new branch]          codex/sim-speed-egomap53    -> origin/codex/sim-speed-egomap53
 * [new branch]          codex/stackaudit            -> origin/codex/stackaudit
 * [new branch]          codex/ubuntu-onboarding     -> origin/codex/ubuntu-onboarding
 * [new branch]          codex/v6h1-acceptance       -> origin/codex/v6h1-acceptance
 * [new branch]          codex/warp6                 -> origin/codex/warp6
 * [new branch]          codex/warpfit               -> origin/codex/warpfit
 * [new branch]          docs/act18-c2c-v7clock-record -> origin/docs/act18-c2c-v7clock-record
 * [new branch]          docs/architecture-overhead  -> origin/docs/architecture-overhead
 * [new branch]          docs/archive-dated          -> origin/docs/archive-dated
 * [new branch]          docs/arena-to-motion        -> origin/docs/arena-to-motion
 * [new branch]          docs/current-status-20261020 -> origin/docs/current-status-20261020
 * [new branch]          docs/diagram-fix-20261115   -> origin/docs/diagram-fix-20261115
 * [new branch]          docs/e2ewarp-contract-20261018 -> origin/docs/e2ewarp-contract-20261018
 * [new branch]          docs/execution-rules-20261115 -> origin/docs/execution-rules-20261115
 * [new branch]          docs/no-sign-positions      -> origin/docs/no-sign-positions
 * [new branch]          docs/one-ceiling-camera     -> origin/docs/one-ceiling-camera
 * [new branch]          docs/page-cleanup           -> origin/docs/page-cleanup
 * [new branch]          docs/pair-excluded          -> origin/docs/pair-excluded
 * [new branch]          docs/plan-20261018          -> origin/docs/plan-20261018
 * [new branch]          docs/plan-20261114          -> origin/docs/plan-20261114
 * [new branch]          docs/plan-20261115-adopted  -> origin/docs/plan-20261115-adopted
 * [new branch]          docs/plan-final-20261018    -> origin/docs/plan-final-20261018
 * [new branch]          docs/plan-gpu-pivot-20261018 -> origin/docs/plan-gpu-pivot-20261018
 * [new branch]          docs/plan-mujoco-only       -> origin/docs/plan-mujoco-only
 * [new branch]          docs/plan-night-20261018    -> origin/docs/plan-night-20261018
 * [new branch]          docs/plan-overhead-camera   -> origin/docs/plan-overhead-camera
 * [new branch]          docs/public-wording-20261020 -> origin/docs/public-wording-20261020
 * [new branch]          docs/readme-architecture    -> origin/docs/readme-architecture
 * [new branch]          docs/readme-no-status       -> origin/docs/readme-no-status
 * [new branch]          docs/readme-rules           -> origin/docs/readme-rules
 * [new branch]          docs/redact-pi-credentials-20261020 -> origin/docs/redact-pi-credentials-20261020
 * [new branch]          docs/redact-ssid            -> origin/docs/redact-ssid
 * [new branch]          docs/research-design        -> origin/docs/research-design
 * [new branch]          docs/solo-architecture      -> origin/docs/solo-architecture
 * [new branch]          docs/solo-figure-carry      -> origin/docs/solo-figure-carry
 * [new branch]          docs/status-20261018        -> origin/docs/status-20261018
 * [new branch]          docs/system-architecture    -> origin/docs/system-architecture
 * [new branch]          dsh/act-chunk-exec          -> origin/dsh/act-chunk-exec
 * [new branch]          dsh/act-integration         -> origin/dsh/act-integration
 * [new branch]          dsh/act-takeover            -> origin/dsh/act-takeover
 * [new branch]          dsh/act18-c2-doneclock      -> origin/dsh/act18-c2-doneclock
 * [new branch]          dsh/act18-c2c-v7clock       -> origin/dsh/act18-c2c-v7clock
 * [new branch]          dsh/act18-c4-counterfactual -> origin/dsh/act18-c4-counterfactual
 * [new branch]          dsh/act18-c4-gpu            -> origin/dsh/act18-c4-gpu
 * [new branch]          dsh/act18-carry-cand-1      -> origin/dsh/act18-carry-cand-1
 * [new branch]          dsh/act18-carry-cand-2      -> origin/dsh/act18-carry-cand-2
 * [new branch]          dsh/act18-carry-cand-3      -> origin/dsh/act18-carry-cand-3
 * [new branch]          dsh/act18-carry-retrain-r1  -> origin/dsh/act18-carry-retrain-r1
 * [new branch]          dsh/act18-diag-fix          -> origin/dsh/act18-diag-fix
 * [new branch]          dsh/act18-e0-clockaudit     -> origin/dsh/act18-e0-clockaudit
 * [new branch]          dsh/act18-e1-tsreplay       -> origin/dsh/act18-e1-tsreplay
 * [new branch]          dsh/act18-r1-gate-precheck  -> origin/dsh/act18-r1-gate-precheck
 * [new branch]          dsh/act18-r3-donewindow     -> origin/dsh/act18-r3-donewindow
 * [new branch]          dsh/act18-scene-v6-fit      -> origin/dsh/act18-scene-v6-fit
 * [new branch]          dsh/crossroom-wallline      -> origin/dsh/crossroom-wallline
 * [new branch]          dsh/e2e-l2                  -> origin/dsh/e2e-l2
 * [new branch]          dsh/e2e-min                 -> origin/dsh/e2e-min
 * [new branch]          dsh/e2e-min-render-fix      -> origin/dsh/e2e-min-render-fix
 * [new branch]          dsh/e2e-min-runner          -> origin/dsh/e2e-min-runner
 * [new branch]          dsh/e2e-min-standalone      -> origin/dsh/e2e-min-standalone
 * [new branch]          dsh/e2ewarp-components-v1   -> origin/dsh/e2ewarp-components-v1
 * [new branch]          dsh/e2ewarp-contract-v1-min -> origin/dsh/e2ewarp-contract-v1-min
 * [new branch]          dsh/e2ewarp-evaluator       -> origin/dsh/e2ewarp-evaluator
 * [new branch]          dsh/gate2-selfcentric       -> origin/dsh/gate2-selfcentric
 * [new branch]          dsh/l1lite-alloc            -> origin/dsh/l1lite-alloc
 * [new branch]          dsh/nav-decay-fix           -> origin/dsh/nav-decay-fix
 * [new branch]          dsh/nav-detector-calib      -> origin/dsh/nav-detector-calib
 * [new branch]          dsh/nav-gate-mode           -> origin/dsh/nav-gate-mode
 * [new branch]          dsh/nav-gate-scene          -> origin/dsh/nav-gate-scene
 * [new branch]          dsh/nav-scene-neutral-start -> origin/dsh/nav-scene-neutral-start
 * [new branch]          dsh/nav-search              -> origin/dsh/nav-search
 * [new branch]          dsh/nav-v230-fwd24          -> origin/dsh/nav-v230-fwd24
 * [new branch]          dsh/nav-v230-r2             -> origin/dsh/nav-v230-r2
 * [new branch]          dsh/nav-v230-r3             -> origin/dsh/nav-v230-r3
 * [new branch]          dsh/nav-v230-r4             -> origin/dsh/nav-v230-r4
 * [new branch]          dsh/nav-v230-r5             -> origin/dsh/nav-v230-r5
 * [new branch]          dsh/nav-v230-r6-n1          -> origin/dsh/nav-v230-r6-n1
 * [new branch]          dsh/nav-v5-recal            -> origin/dsh/nav-v5-recal
 * [new branch]          dsh/nav-v6-light30          -> origin/dsh/nav-v6-light30
 * [new branch]          dsh/odom-unit-fix           -> origin/dsh/odom-unit-fix
 * [new branch]          dsh/pairact-carry-r1        -> origin/dsh/pairact-carry-r1
 * [new branch]          dsh/pairact-carry-r1-v2     -> origin/dsh/pairact-carry-r1-v2
 * [new branch]          dsh/pairact-carry-r1-v3     -> origin/dsh/pairact-carry-r1-v3
 * [new branch]          dsh/pairact-carry-r1-v3-shard -> origin/dsh/pairact-carry-r1-v3-shard
 * [new branch]          dsh/pairact-carry-r1-v4     -> origin/dsh/pairact-carry-r1-v4
 * [new branch]          dsh/pairact-carry-r1-v5     -> origin/dsh/pairact-carry-r1-v5
 * [new branch]          dsh/pairact-carry-r1-v6     -> origin/dsh/pairact-carry-r1-v6
 * [new branch]          dsh/pairact-carry-r1-v7     -> origin/dsh/pairact-carry-r1-v7
 * [new branch]          dsh/pairact-carry-r1-v7-1b  -> origin/dsh/pairact-carry-r1-v7-1b
 * [new branch]          dsh/pairact-carry-r1-v8     -> origin/dsh/pairact-carry-r1-v8
 * [new branch]          dsh/pairact-carry-r1-v9     -> origin/dsh/pairact-carry-r1-v9
 * [new branch]          dsh/pairact-p0-diag         -> origin/dsh/pairact-p0-diag
 * [new branch]          dsh/pairact-p1-cand-1       -> origin/dsh/pairact-p1-cand-1
 * [new branch]          dsh/pairact-p1-cand-1-a     -> origin/dsh/pairact-p1-cand-1-a
 * [new branch]          dsh/pairact-p1-cand-1-r     -> origin/dsh/pairact-p1-cand-1-r
 * [new branch]          dsh/pairact-p1-cand-2       -> origin/dsh/pairact-p1-cand-2
 * [new branch]          dsh/pairact-p1-cand-2b      -> origin/dsh/pairact-p1-cand-2b
 * [new branch]          dsh/pairact-p1-cand-2b-a    -> origin/dsh/pairact-p1-cand-2b-a
 * [new branch]          dsh/pairact-p1-cand-2b-r    -> origin/dsh/pairact-p1-cand-2b-r
 * [new branch]          dsh/pairact-p1-cand-3       -> origin/dsh/pairact-p1-cand-3
 * [new branch]          dsh/pairact-p1-cand-3-a     -> origin/dsh/pairact-p1-cand-3-a
 * [new branch]          dsh/pairact-p1-cand-3-r     -> origin/dsh/pairact-p1-cand-3-r
 * [new branch]          dsh/pairact-p2-carrypath    -> origin/dsh/pairact-p2-carrypath
 * [new branch]          dsh/pairact-p2-carrypath-a  -> origin/dsh/pairact-p2-carrypath-a
 * [new branch]          dsh/pairact-p2-carrypath-a-c -> origin/dsh/pairact-p2-carrypath-a-c
 * [new branch]          dsh/pairact-p2-carrypath-a-c2 -> origin/dsh/pairact-p2-carrypath-a-c2
 * [new branch]          dsh/pairact-p2-carrypath-a-c3 -> origin/dsh/pairact-p2-carrypath-a-c3
 * [new branch]          dsh/pairact-p2-carrypath-a-c4 -> origin/dsh/pairact-p2-carrypath-a-c4
 * [new branch]          dsh/pairact-p2-carrypath-a-c5 -> origin/dsh/pairact-p2-carrypath-a-c5
 * [new branch]          dsh/pairact-p2-carrypath-a-c5-hybrid -> origin/dsh/pairact-p2-carrypath-a-c5-hybrid
 * [new branch]          dsh/pairact-p2-carrypath-a-c5-hybrid2 -> origin/dsh/pairact-p2-carrypath-a-c5-hybrid2
 * [new branch]          dsh/pairact-p2-carrypath-a-c6 -> origin/dsh/pairact-p2-carrypath-a-c6
 * [new branch]          dsh/pairact-p2-carrypath-a-p5 -> origin/dsh/pairact-p2-carrypath-a-p5
 * [new branch]          dsh/pairact-p2-carrypath-c  -> origin/dsh/pairact-p2-carrypath-c
 * [new branch]          dsh/pairact-p2-carrypath-c2 -> origin/dsh/pairact-p2-carrypath-c2
 * [new branch]          dsh/pairact-p2-carrypath-c3 -> origin/dsh/pairact-p2-carrypath-c3
 * [new branch]          dsh/pairact-p2-carrypath-c3-admission -> origin/dsh/pairact-p2-carrypath-c3-admission
 * [new branch]          dsh/pairact-p2-carrypath-c4 -> origin/dsh/pairact-p2-carrypath-c4
 * [new branch]          dsh/pairact-p2-carrypath-c5 -> origin/dsh/pairact-p2-carrypath-c5
 * [new branch]          dsh/pairact-p2-carrypath-c5-hybrid -> origin/dsh/pairact-p2-carrypath-c5-hybrid
 * [new branch]          dsh/pairact-p2-carrypath-c5-hybrid2 -> origin/dsh/pairact-p2-carrypath-c5-hybrid2
 * [new branch]          dsh/pairact-p2-carrypath-c6 -> origin/dsh/pairact-p2-carrypath-c6
 * [new branch]          dsh/pairact-p2-carrypath-r  -> origin/dsh/pairact-p2-carrypath-r
 * [new branch]          dsh/pairact-p2-carrypath-r-c -> origin/dsh/pairact-p2-carrypath-r-c
 * [new branch]          dsh/pairact-p2-carrypath-r-c2 -> origin/dsh/pairact-p2-carrypath-r-c2
 * [new branch]          dsh/pairact-p2-carrypath-r-c3 -> origin/dsh/pairact-p2-carrypath-r-c3
 * [new branch]          dsh/pairact-p2-carrypath-r-c4 -> origin/dsh/pairact-p2-carrypath-r-c4
 * [new branch]          dsh/pairact-p2-carrypath-r-c5 -> origin/dsh/pairact-p2-carrypath-r-c5
 * [new branch]          dsh/pairact-p2-carrypath-r-c5-hybrid -> origin/dsh/pairact-p2-carrypath-r-c5-hybrid
 * [new branch]          dsh/pairact-p2-carrypath-r-c5-hybrid2 -> origin/dsh/pairact-p2-carrypath-r-c5-hybrid2
 * [new branch]          dsh/pairact-p2-carrypath-r-c6 -> origin/dsh/pairact-p2-carrypath-r-c6
 * [new branch]          dsh/pairact-p2-carrypath-r-p5 -> origin/dsh/pairact-p2-carrypath-r-p5
 * [new branch]          dsh/pairact-p5-rows-fix-20261025 -> origin/dsh/pairact-p5-rows-fix-20261025
 * [new branch]          dsh/pairact-p5-student      -> origin/dsh/pairact-p5-student
 * [new branch]          dsh/pairact-p5-student-hybrid -> origin/dsh/pairact-p5-student-hybrid
 * [new branch]          dsh/pairact-pilot-analysis  -> origin/dsh/pairact-pilot-analysis
 * [new branch]          dsh/pairact-prereg-xreview  -> origin/dsh/pairact-prereg-xreview
 * [new branch]          dsh/pairact-r1-armN         -> origin/dsh/pairact-r1-armN
 * [new branch]          dsh/pairact-r1-convert-fix  -> origin/dsh/pairact-r1-convert-fix
 * [new branch]          dsh/pairact-r1-docs-before-collect -> origin/dsh/pairact-r1-docs-before-collect
 * [new branch]          dsh/pairact-r1-dryrun       -> origin/dsh/pairact-r1-dryrun
 * [new branch]          dsh/pairact-r1-eval-prereg-v3 -> origin/dsh/pairact-r1-eval-prereg-v3
 * [new branch]          dsh/pairact-r1-k1-refreeze  -> origin/dsh/pairact-r1-k1-refreeze
 * [new branch]          dsh/pairact-r1-p5-registered -> origin/dsh/pairact-r1-p5-registered
 * [new branch]          dsh/pairact-r1-train-ready  -> origin/dsh/pairact-r1-train-ready
 * [new branch]          dsh/pairact-r1-v3s-probe-gcp2 -> origin/dsh/pairact-r1-v3s-probe-gcp2
 * [new branch]          dsh/report-auto             -> origin/dsh/report-auto
 * [new branch]          dsh/selfnav-drive           -> origin/dsh/selfnav-drive
 * [new branch]          feat/solo-pipeline          -> origin/feat/solo-pipeline
 * [new branch]          import/ckpt-solo-act-20260916 -> origin/import/ckpt-solo-act-20260916
 * [new branch]          import/wip-beamact3-20261027 -> origin/import/wip-beamact3-20261027
 * [new branch]          import/wip-bundle-20261027  -> origin/import/wip-bundle-20261027
 * [new branch]          import/wip-e2e18-20261027   -> origin/import/wip-e2e18-20261027
 * [new branch]          import/wip-e2ewarp-contract-20261027 -> origin/import/wip-e2ewarp-contract-20261027
 * [new branch]          import/wip-gcp6setup-20261027 -> origin/import/wip-gcp6setup-20261027
 * [new branch]          import/wip-llmhost-20261027 -> origin/import/wip-llmhost-20261027
 * [new branch]          import/wip-macprune-20261027 -> origin/import/wip-macprune-20261027
 * [new branch]          import/wip-mapbuild1-20261027 -> origin/import/wip-mapbuild1-20261027
 * [new branch]          import/wip-mast3rcmp-20261027 -> origin/import/wip-mast3rcmp-20261027
 * [new branch]          import/wip-reloc21-20261027 -> origin/import/wip-reloc21-20261027
 * [new branch]          import/wip-rl-act-20261027  -> origin/import/wip-rl-act-20261027
 * [new branch]          import/wip-warp-act-20261027 -> origin/import/wip-warp-act-20261027
 * [new branch]          import/wip-warp4-20261027   -> origin/import/wip-warp4-20261027
 * [new branch]          import/wip-warp5-20261027   -> origin/import/wip-warp5-20261027
 * [new branch]          kiro/disk-rules             -> origin/kiro/disk-rules
 * [new branch]          overhaul/experiments-raw-to-drive-20261113 -> origin/overhaul/experiments-raw-to-drive-20261113
 * [new branch]          overhaul/sim2real-entry-20261113 -> origin/overhaul/sim2real-entry-20261113
 * [new branch]          pair-removal/step1-experiments -> origin/pair-removal/step1-experiments
 * [new branch]          relay-oracle-linux          -> origin/relay-oracle-linux
 * [new branch]          solo-e2e/20261024           -> origin/solo-e2e/20261024
 * [new branch]          tmp/ss-on-c1f               -> origin/tmp/ss-on-c1f
 * [new branch]          ugrp/geometry-projection-intervention-v2-20261106 -> origin/ugrp/geometry-projection-intervention-v2-20261106
 * [new branch]          ugrp/history-producer-20261105T1923Z -> origin/ugrp/history-producer-20261105T1923Z
 * [new branch]          ugrp/issued-provenance-20261105T1902Z -> origin/ugrp/issued-provenance-20261105T1902Z
 * [new branch]          ugrp/pair-consumer-audit-20261105T2046Z -> origin/ugrp/pair-consumer-audit-20261105T2046Z
 * [new branch]          ugrp/pair-runner-wire-20261105T2017Z -> origin/ugrp/pair-runner-wire-20261105T2017Z
 * [new branch]          ugrp/pair-worker-audit-20261105T1952Z -> origin/ugrp/pair-worker-audit-20261105T1952Z
 * [new branch]          ugrp/raw-proposal-observer-20261106T0043Z -> origin/ugrp/raw-proposal-observer-20261106T0043Z
 * [new branch]          ugrp/solo-geometry-client-scope-20261106 -> origin/ugrp/solo-geometry-client-scope-20261106
 * [new branch]          ugrp/transport-evidence-contract-20261105T2215Z -> origin/ugrp/transport-evidence-contract-20261105T2215Z
 * [new tag]             experiment/markerless-n7-20260909 -> experiment/markerless-n7-20260909
 * [new tag]             models-20260923-v1          -> models-20260923-v1
 * [new tag]             models-20260924-action-act-v1 -> models-20260924-action-act-v1
 * [new tag]             models-20260927-vision-loc-v1 -> models-20260927-vision-loc-v1
 * [new tag]             models-20261015-act13-961aa751 -> models-20261015-act13-961aa751
 * [new tag]             models-20261015-act15-1535c8a3 -> models-20261015-act15-1535c8a3
 * [new tag]             models-20261015-grasp-act-f609979c -> models-20261015-grasp-act-f609979c
 * [new tag]             models-20261016-beamact2-v1 -> models-20261016-beamact2-v1
 * [new tag]             models-20261016-beamact3-a-v1 -> models-20261016-beamact3-a-v1
 * [new tag]             models-20261016-beamact3-b-v1 -> models-20261016-beamact3-b-v1
 * [new tag]             models-20261027-pairact-r2-step11000-v1 -> models-20261027-pairact-r2-step11000-v1
 * [new tag]             models-20261112-solo-pair-status-v1 -> models-20261112-solo-pair-status-v1
 * [new tag]             solo-v1-20261114            -> solo-v1-20261114
 * [new tag]             models-20261016-act16w-native-v1 -> models-20261016-act16w-native-v1
 * [new tag]             models-20261016-act16w-v1   -> models-20261016-act16w-v1
 * [new tag]             models-20261017-act17-v7-r1 -> models-20261017-act17-v7-r1
 * [new tag]             models-20261017-act18-v7-r1 -> models-20261017-act18-v7-r1

exit_code=0

```

## 21-quickstart-tests

- 시작: 2026-11-16T12:28:54.241734+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.717 s
- 기록기 상한: 60.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 .venv-dev/bin/python -m pytest -q tests/test_sim_quickstart.py tests/test_simulation_launch_options.py
.............................                                            [100%]
29 passed in 0.35s

exit_code=0

```

## 22-environment

- 시작: 2026-11-16T12:29:21.799287+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.165 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -c 'import os,platform,sys,sysconfig,json,subprocess,ctypes.util,shutil; from pathlib import Path; print(json.dumps({"os_release":platform.freedesktop_os_release(),"python":platform.python_version(),"platform":platform.platform(),"python_prefix":sys.prefix,"python_base_prefix":sys.base_prefix,"isolated_venv":sys.prefix!=sys.base_prefix,"venv_config":Path(".venv-dev/pyvenv.cfg").read_text(),"cuda_devices":list(map(str,Path("/dev").glob("nvidia*"))),"drm_devices":list(map(str,Path("/dev/dri").glob("renderD*"))),"cpu_count":os.cpu_count(),"cpu_affinity_count":len(os.sched_getaffinity(0)),"available_disk_bytes":shutil.disk_usage(".").free,"OSMesa":ctypes.util.find_library("OSMesa"),"EGL":ctypes.util.find_library("EGL"),"tools":{n:shutil.which(n) for n in ["git","gh","sudo","docker","podman","ffmpeg"]},"head":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"is_shallow":subprocess.check_output(["git","rev-parse","--is-shallow-repository"],text=True).strip(),"worktree_status":subprocess.check_output(["git","status","--porcelain"],text=True)},indent=2))'
{
  "os_release": {
    "NAME": "Debian GNU/Linux",
    "ID": "debian",
    "PRETTY_NAME": "Debian GNU/Linux 13 (trixie)",
    "VERSION_ID": "13",
    "VERSION": "13 (trixie)",
    "VERSION_CODENAME": "trixie",
    "DEBIAN_VERSION_FULL": "13.6",
    "HOME_URL": "https://www.debian.org/",
    "SUPPORT_URL": "https://www.debian.org/support",
    "BUG_REPORT_URL": "https://bugs.debian.org/"
  },
  "python": "3.12.14",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "python_prefix": "<checkout>/.venv-dev",
  "python_base_prefix": "<python-runtime>",
  "isolated_venv": true,
  "venv_config": "home = <python-runtime>/bin\ninclude-system-site-packages = false\nversion = 3.12.14\nexecutable = <python-runtime>/bin/python3.12\ncommand = <python-runtime>/bin/python3.12 -m venv <checkout>/.venv-dev\n",
  "cuda_devices": [],
  "drm_devices": [],
  "cpu_count": 9,
  "cpu_affinity_count": 9,
  "available_disk_bytes": 57654419456,
  "OSMesa": null,
  "EGL": "libEGL.so.1",
  "tools": {
    "git": "/usr/local/bin/git",
    "gh": "/usr/bin/gh",
    "sudo": null,
    "docker": null,
    "podman": null,
    "ffmpeg": "/usr/bin/ffmpeg"
  },
  "head": "ca954d9fa64f94303a3f645c265aff85e2af2fce",
  "is_shallow": "false",
  "worktree_status": ""
}

exit_code=0

```

## 23-pip-freeze

- 시작: 2026-11-16T12:29:22.609273+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.32 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ .venv-dev/bin/python -m pip freeze --all
absl-py==2.5.1
contourpy==1.4.0
cycler==0.12.1
etils==1.15.0
fonttools==4.68.0
fsspec==2026.9.0
glfw==2.10.2
iniconfig==2.3.1
kiwisolver==1.5.1
matplotlib==3.11.2
mujoco==3.12.0
narwhals==2.28.0
numpy==2.5.2
opencv-python-headless==5.0.0.93
ordered-set==4.1.0
packaging==26.3
pillow==12.3.0
pip==26.3
plotly==7.1.0
pluggy==1.7.0
Pygments==2.21.0
pymap3d==3.2.0
PyOpenGL==3.1.10
pyparsing==3.3.3
pytest==9.1.1
python-dateutil==4.0.0
rtree==1.4.1
ruamel.yaml==0.19.1
scipy==1.17.1
stonesoup==1.7
typing_extensions==4.16.0
tzdata==2026.6
utm==0.9.0
websockets==15.0.1
zipp==4.1.2

exit_code=0

```

## 24-first-failure-all-refs

- 시작: 2026-11-16T12:29:28.828611+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.517 s
- 기록기 상한: 45.0 s; 상한 종료: `false`

```text
$ env MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 CUDA_VISIBLE_DEVICES= PYTHONNOUSERSITE=1 .venv-dev/bin/python -m pytest -q -x tests/test_beamact2.py::test_close_never_executes_before_both_READY_GO_ACK_and_delay
.                                                                        [100%]
1 passed in 0.18s

exit_code=0

```

## 25-frozen-object-check

- 시작: 2026-11-16T12:29:29.861723+09:00
- 작업 폴더: `<checkout>`
- 종료 코드: `0`
- 실제 경과: 0.004 s
- 기록기 상한: 30.0 s; 상한 종료: `false`

```text
$ git cat-file -t 26f84d0f0ada1c33473c83cca2d3415ce51bd247
commit

exit_code=0

```
