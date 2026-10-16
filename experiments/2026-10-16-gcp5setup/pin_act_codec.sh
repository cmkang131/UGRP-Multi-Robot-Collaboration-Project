#!/bin/bash
# PyTorch extra-index selects 0.10.0+cu128 for ==0.10.0 (PEP440 local version).
# gcp2's measured freeze is the plain PyPI 0.10.0 wheel; restore that exact version.
set -euo pipefail
/home/ugrp/ugrp-rl1b-act-env/bin/pip install --no-deps --force-reinstall --index-url https://pypi.org/simple torchcodec==0.10.0
/home/ugrp/ugrp-rl1b-act-env/bin/pip freeze > /home/ugrp/ugrp-sim/setup/act-freeze.txt
