import pytest
from unittest.mock import create_autospec, patch, call

from cobra.hooks import Hooks

from os.path import join


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

    # calls = [call(join(hooks_dir, f'{hook_name}.{ext}'), 'w') for hook_name in sut.HOOKS for ext in ('py', 'sh')]
    # open_mock.assert_has_calls(calls)
    # calls = [call(join(hooks_dir, f'{hook_name}.sh'), 'w') for hook_name in sut.HOOKS]
    # chmod_mock.assert_has_calls(calls)
