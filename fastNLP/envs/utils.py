import os
import math
import time
from importlib.util import find_spec
from typing import Callable
import importlib
from pkg_resources import DistributionNotFound
from packaging.version import Version
import subprocess
import pkg_resources

__all__ = []

def _module_available(module_path: str) -> bool:
    """Check if a path is available in your environment.

    >>> _module_available('os')
    True
    >>> _module_available('bla.bla')
    False
    """
    try:
        return find_spec(module_path) is not None
    except AttributeError:
        # Python 3.6
        return False
    except ModuleNotFoundError:
        # Python 3.7+
        return False


def _get_version(package, use_base_version: bool = False):
    try:
        pkg = importlib.import_module(package)
    except (ModuleNotFoundError, DistributionNotFound):
        return False
    try:
        if hasattr(pkg, "__version__"):
            pkg_version = Version(pkg.__version__)
        else:
            # try pkg_resources to infer version
            pkg_version = Version(pkg_resources.get_distribution(package).version)
    except TypeError:
        # this is mocked by Sphinx, so it should return True to generate all summaries
        return True
    if use_base_version:
        pkg_version = Version(pkg_version.base_version)
    return pkg_version


def _compare_version(package: str, op: Callable, version: str, use_base_version: bool = False) -> bool:
    """Compare package version with some requirements.

    >>> _compare_version("torch", operator.ge, "0.1")
    True
    """
    try:
        pkg = importlib.import_module(package)
    except (ModuleNotFoundError, DistributionNotFound):
        return False
    try:
        if hasattr(pkg, "__version__"):
            pkg_version = Version(pkg.__version__)
        else:
            # try pkg_resources to infer version
            pkg_version = Version(pkg_resources.get_distribution(package).version)
    except TypeError:
        # this is mocked by Sphinx, so it should return True to generate all summaries
        return True
    if use_base_version:
        pkg_version = Version(pkg_version.base_version)
    return op(pkg_version, Version(version))

def get_gpu_count() -> int:
    """
    利用命令行获取 ``gpu`` 数目的函数

    :return: 显卡数目，如果没有显卡设备则为-1
    """
    try:
        lines = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv'])
        # 经分割后还要除去头部和尾部的换行符
        return len(lines.split(b"\n")) - 2
    except:
        return -1

def get_global_seed():
    seed = os.getenv("FASTNLP_GLOBAL_SEED", None)
    if seed is not None:
        return int(seed)
    seed = int(math.modf(time.time())[0] * 1000000)
    os.environ["FASTNLP_GLOBAL_SEED"] = f"{seed}"

    return seed
