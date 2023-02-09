import pytest
from unittest.mock import create_autospec, patch

from cobra.hooks import Hooks


@pytest.fixture
def disable_hooks():
    return list()


@pytest.fixture
def hooks_dir():
    return '/hooks/dir'


@pytest.fixture
def sut(hooks_dir, disable_hooks):
    return Hooks(hooks_dir=hooks_dir, disable_hooks=disable_hooks)


@pytest.fixture
def source_import_mock():
    with patch('cobra.hooks._source_import') as mock:
        return mock



def test_must_raise_if_invalid_hook_name_given_in_disable_hooks():
    with pytest.raises(ValueError):
        Hooks(disable_hooks=['asdf'])


def test_init_hooks(sut, open_mock, makedirs_mock, chmod_mock, hooks_dir):
    sut.init_hooks()
    makedirs_mock.assert_called_with(hooks_dir, exist_ok=True)
