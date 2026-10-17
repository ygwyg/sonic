import os

import numpy as np
import pytest

from sonic.config import OFDMConfig, PRESETS

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "sonic")


@pytest.fixture(scope="session")
def python_source() -> bytes:
    with open(os.path.join(PKG, "config.py"), "rb") as f:
        return f.read()


@pytest.fixture(scope="session")
def small_cfg() -> OFDMConfig:
    """A fast configuration for tests (short payloads decode in < 1 s)."""
    return PRESETS["default"]


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)
