"""Review tests only: forbid real output reads and physics/model/network use."""
import os
import sys


def review_guard(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.realpath(os.fsdecode(args[0]))
        if '/Users/changmin/projects/ugrp/outputs/' in path or '/outputs/final-pair-' in path:
            raise RuntimeError('REVIEW_364: real experiment output access forbidden')
    if event == 'import' and args and str(args[0]).split('.')[0] in {
        'mujoco', 'torch', 'torchvision', 'openai', 'anthropic', 'google.genai',
    }:
        raise RuntimeError('REVIEW_364: physics/model import forbidden')
    if event == 'socket.connect':
        raise RuntimeError('REVIEW_364: test network forbidden')


sys.addaudithook(review_guard)
