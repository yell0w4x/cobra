import pytest
from unittest.mock import create_autospec, patch, call

from cobra.hooks import Hooks, default_hook

from os.path import join
import os


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
        yield mock


@pytest.fixture
def default_hook_mock():
    with patch('cobra.hooks.default_hook') as mock:
        yield mock


@pytest.fixture
def exists_mock():
    with patch('cobra.hooks.exists') as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def check_call_mock():
    with patch('cobra.hooks.check_call') as mock:
        yield mock


def test_must_raise_if_invalid_hook_name_given_in_disable_hooks():
    with pytest.raises(ValueError):
        Hooks(disable_hooks=['asdf'])


def test_init_hooks_must_populate_files(sut, open_mock, makedirs_mock, chmod_mock, hooks_dir):
    sut.init_hooks()
    makedirs_mock.assert_called_with(hooks_dir, exist_ok=True)

    print(open_mock.method_calls)
    calls = [call(join(hooks_dir, f'{hook_name}.{ext}'), 'w') for hook_name in sut.HOOKS for ext in ('py', 'sh')]
    open_mock.assert_has_calls(calls, any_order=True)
    calls = [call(join(hooks_dir, f'{hook_name}.sh'), 0o755) for hook_name in sut.HOOKS]
    chmod_mock.assert_has_calls(calls)


def test_must_call_default_hook_if_no_py_file_exists(sut, default_hook_mock, exists_mock, hooks_dir):
    hook_name = sut.HOOKS[0]
    sut(hook_name)
    exists_mock.assert_called_with(join(hooks_dir, f'{hook_name}.py'))
    default_hook_mock.assert_called_with(hook_name=hook_name, hooks_dir=hooks_dir)


def test_must_import_hook_source_if_py_file_exists(sut, default_hook_mock, exists_mock, hooks_dir, source_import_mock):
    hook_name = sut.HOOKS[0]
    exists_mock.return_value = True
    sut(hook_name)
    fn = join(hooks_dir, f'{hook_name}.py')
    exists_mock.assert_called_with(fn)
    default_hook_mock.assert_not_called()
    source_import_mock.assert_called_with(hook_name, fn)
    source_import_mock.return_value.hook.assert_called_with(hook_name=hook_name, hooks_dir=hooks_dir)


def test_must_raise_if_invalid_hook_name_given(sut):
    with pytest.raises(ValueError):
        sut('asdf')


def test_default_hook_must_call_shell_script_if_exists(hooks_dir, exists_mock, check_call_mock):
    hook_name = Hooks.HOOKS[0]
    exists_mock.return_value = True
    default_hook(hook_name=hook_name, hooks_dir=hooks_dir, docker='docker client obj', arg1='arg1', arg2='arg2')

    script_fn = join(hooks_dir, f'{hook_name}.sh')
    exists_mock.assert_called_with(script_fn)
    check_call_mock.assert_called_with([script_fn, hook_name, hooks_dir, 'arg1', 'arg2'])


def test_default_hook_must_do_nothing_if_no_file_exists(hooks_dir, exists_mock, check_call_mock):
    hook_name = Hooks.HOOKS[0]
    default_hook(hook_name=hook_name, hooks_dir=hooks_dir, docker='docker client obj', arg1='arg1', arg2='arg2')
    check_call_mock.assert_not_called()

