from mindsync.cli_handler import CliHandler
from mindsync.api import Api, AsyncApi
from mindsync.exc import MindsyncCliError

import pytest
from unittest.mock import create_autospec, Mock

from argparse import Namespace
import inspect


API_KEY = 'does-not-matter'
BASE_URL = 'https://whatever'
RIG_ID = 'a-rig-id'
PROFILE_ID = 'a-profile-id'
RENT_ID = 'a-rent-id'
USER_ID = 'some-user-id'


@pytest.fixture
def api_mock():
    api = Api(key='dosnt-matter')
    return create_autospec(api, spec_set=True)


@pytest.fixture
def sut(api_mock):
    sut = CliHandler()
    sut.bind(api_mock)
    return sut


@pytest.fixture
def empty_sut():
    return CliHandler()


# in this test check only few of methods for delegate logic, the second test checks that all methods exist
@pytest.mark.parametrize('kwargs, expected_kwargs, method, rv', [
                                                            (dict(id=USER_ID, prettify=False, whatever='whatever'), 
                                                            dict(id=USER_ID, prettify=False, whatever='whatever'), 
                                                            'profile', '{}'),
                                                            (dict(prettify=False, first_name='first_name', last_name='last_name', phone='phone',
                                                                       gravatar='gravatar', nickname='nickname', wallet_symbol='wallet_symbol',
                                                                       wallet_address='wallet_address', country='country', city='city'), 
                                                            dict(prettify=False, first_name='first_name', last_name='last_name', phone='phone',
                                                                 gravatar='gravatar', nickname='nickname', wallet_symbol='wallet_symbol',
                                                                 wallet_address='wallet_address', country='country', city='city'), 
                                                            'set_profile', '{}'),
                                                            (dict(my=True, prettify=False, whatever='whatever'), 
                                                            dict(my=True, prettify=False, whatever='whatever'), 
                                                            'rigs_list', '{}'),
                                                            ])
def test_cli_handler_must_delegate_to_right_api(sut, api_mock, kwargs, expected_kwargs, method, rv):
    mock_f = getattr(api_mock, method)
    mock_f.return_value = rv
    sut_f = getattr(sut, method)
    sut_f(**kwargs)
    mock_f.assert_called_with(**expected_kwargs)


def test_cli_handler_must_define_all_the_methods(sut):
        original_methods = { name for name, _ in inspect.getmembers(AsyncApi, predicate=inspect.isfunction) if '__' not in name }
        sut_methods = { name for name, _ in inspect.getmembers(sut, predicate=inspect.isfunction) if '__' not in name }
        assert original_methods == sut_methods


def test_cli_handler_must_raise_if_not_binded(empty_sut):
    with pytest.raises(ValueError):
        empty_sut.bind(None)

    with pytest.raises(MindsyncCliError):
        empty_sut.profile()

    with pytest.raises(MindsyncCliError):
        empty_sut.rigs_list()