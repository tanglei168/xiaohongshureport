from pathlib import Path

import pytest


@pytest.fixture
def fixture_html() -> callable:
    fixture_dir = Path(__file__).parent / "fixtures"

    def load(name: str) -> str:
        return (fixture_dir / name).read_text(encoding="utf-8")

    return load
