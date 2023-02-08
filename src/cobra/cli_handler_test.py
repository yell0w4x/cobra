from cobra.cli_handler import CliHandler
from cobra.api import Api
from cobra.exc import CobraCliError

import pytest
from unittest.mock import create_autospec, Mock

from argparse import Namespace
import inspect


BASE_URL = 'https://whatever'


@pytest.fixture
def api_mock():
    return create_autospec(Api, spec_set=True, instance=True)


@pytest.fixture
def sut(api_mock):
    sut = CliHandler()
    sut.bind(api_mock)
    return sut


@pytest.fixture
def empty_sut():
    return CliHandler()


# in this test check only few of methods for delegate logic, the second test checks that all methods exist
@pytest.mark.parametrize('kwargs, expected_kwargs, method', [
                                                            (dict(volume_names=['asdf'], dir_names=['qwer'], backup_basename='backup', host_backup_dir='/path/to/whatever', base_url=BASE_URL, log_level='INFO', whatever='whatever'), 
                                                             dict(volume_names=['asdf'], dir_names=['qwer'], backup_basename='backup', host_backup_dir='/path/to/whatever', base_url=BASE_URL, log_level='INFO', whatever='whatever'), 
                                                             'backup_build'),
                                                            (dict(creds='asdf', file_id='qwer'), 
                                                             dict(creds='asdf', file_id='qwer'),
                                                            'backup_pull')])
def test_cli_handler_must_delegate_to_right_api(sut, api_mock, kwargs, expected_kwargs, method):
    mock_f = getattr(api_mock, method)
    sut_f = getattr(sut, method)
    sut_f(**kwargs)
    mock_f.assert_called_with(**expected_kwargs)


def test_cli_handler_must_define_all_the_methods(sut):
        original_methods = { name for name, _ in inspect.getmembers(Api, predicate=inspect.isfunction) if '__' not in name }
        sut_methods = { name for name, _ in inspect.getmembers(sut, predicate=inspect.isfunction) if '__' not in name }
        assert original_methods == sut_methods


def test_cli_handler_must_raise_if_not_binded(empty_sut):
    with pytest.raises(ValueError):
        empty_sut.bind(None)

    for name, func in inspect.getmembers(empty_sut, predicate=inspect.isfunction):
        if '__' not in name:
            with pytest.raises(CobraCliError):
                func()
