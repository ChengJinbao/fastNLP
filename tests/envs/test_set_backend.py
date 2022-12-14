import os
import pytest

from fastNLP.envs.set_backend import dump_fastnlp_backend
from tests.helpers.utils import Capturing
from fastNLP.envs.distributed import rank_zero_rm


def test_dump_fastnlp_envs():
    filepath = None
    try:
        if 'CONDA_DEFAULT_ENV' in os.environ:
            with Capturing() as output:
                dump_fastnlp_backend(backend="torch")
            filepath = os.path.join(os.path.expanduser('~'), '.fastNLP', 'envs', os.environ['CONDA_DEFAULT_ENV']+'.json')
            assert filepath in output[0]
            assert os.path.exists(filepath)
        else:
            with pytest.raises(RuntimeError):
                dump_fastnlp_backend(backend="torch")
    finally:
        rank_zero_rm(filepath)
