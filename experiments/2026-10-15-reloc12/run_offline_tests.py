import sys,importlib.abc
class NoPlant(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] == 'mujoco': raise ImportError('reloc12: Mac physics/render imports blocked')
sys.meta_path.insert(0,NoPlant())
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
