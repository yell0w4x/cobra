import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def open_mock():
    with patch('builtins.open') as mock:
        mock_enter_rv = MagicMock()
        mock.return_value.__enter__.return_value = mock_enter_rv
        yield mock


@pytest.fixture
def makedirs_mock():
    with patch('os.makedirs') as mock:
        yield mock


@pytest.fixture
def chmod_mock():
    with patch('os.chmod') as mock:
        yield mock
