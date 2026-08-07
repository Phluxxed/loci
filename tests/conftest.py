import os
import shutil
import tempfile
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_SUITE_STORE_ROOT = Path(tempfile.mkdtemp(prefix="loci-pytest-store-")).resolve()
os.environ["LOCI_BASE_DIR"] = str(_SUITE_STORE_ROOT)
os.environ["LOCI_STORE_NAMESPACE"] = "pytest"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    shutil.rmtree(_SUITE_STORE_ROOT, ignore_errors=True)

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
