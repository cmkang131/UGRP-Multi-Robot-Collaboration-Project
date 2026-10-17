"""Run scripts/replay_e2e_vomask.py (saved RGB + issued commands, no simulation) with camera_calib off or measured_v1.
usage: python -m scripts.replay_vomask_calib <off|measured_v1> --raw-root ... --image-root ... --ledger-root ... --output ..."""
import sys
from harness import camera_calib
mode = sys.argv.pop(1)
camera_calib.set_mode(mode)
from scripts import replay_e2e_vomask as R
R.main()
print('camera_calib', camera_calib.status())
