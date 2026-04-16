"""pytest 공통 픽스처."""
import pytest


@pytest.fixture(autouse=True)
def reset_slug_state():
    """각 테스트 전에 _run_claimed_slugs를 초기화해 테스트 간 격리."""
    from simulation.slack_collector import _slug_lock, _run_claimed_slugs
    with _slug_lock:
        _run_claimed_slugs.clear()
    yield
    with _slug_lock:
        _run_claimed_slugs.clear()
