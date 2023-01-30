import pytest
from unittest.mock import patch, AsyncMock, create_autospec, MagicMock

from mindsync.api import AsyncApi, MindsyncApiError, DEFAULT_BASE_URL

from aiohttp import ClientResponse, ClientConnectionError, FormData
from io import IOBase


API_KEY = 'an-api-key'
USER_ID = 'an-user-id'
RESPONSE_RV = dict(result=dict(first_name='Elvis', last_name='Presley'), whatever='whatever')
ERROR_RESPONSE_RV = dict(error=dict(code=400, name='StatusError', message='Something wrong happens'), result=None, whatever='whatever')
RIG_ID = 'a-rig-id'
RENT_ID = 'a-rent-id'
API_VERSION = '1.0'
PROXY_URL = 'http://localhost:8080'
SOME_FN = 'filename.py'
CODE_ID = 'code-id'
RENT_ID = 'rent-id'
UUID = 'uuid'


@pytest.fixture
def api_key():
    return API_KEY


@pytest.fixture
def sut(api_key):
    return AsyncApi(api_key)


@pytest.fixture
def raise_sut(api_key):
    return AsyncApi(api_key, raise_for_error=True)


@pytest.fixture
def resp_mock():
        mock = create_autospec(spec=ClientResponse, spec_set=True, instance=True)
        mock.json.return_value = RESPONSE_RV
        return mock


@pytest.fixture
def err_resp_mock():
    mock = create_autospec(spec=ClientResponse, spec_set=True, instance=True)
    mock.json.return_value = ERROR_RESPONSE_RV
    return mock


@pytest.fixture
def open_mock():
    with patch('builtins.open') as mock:
        yield mock


class FormDataMatcher(FormData):
    def __eq__(self, other):
        return self._fields == other._fields


@pytest.fixture
def form_data(open_mock):
    data = FormDataMatcher()
    data.add_field('file', open_mock.return_value, content_type='application/octet-stream')
    data.add_field('isPrivate', 'false')
    return data


@pytest.fixture
def aiohttp_request_mock(resp_mock):
    with patch('aiohttp.request') as mock:
        mock.return_value.__aenter__.return_value = resp_mock
        yield mock


@pytest.fixture
def err_aiohttp_request_mock(err_resp_mock):
    with patch('aiohttp.request') as mock:
        mock.return_value.__aenter__.return_value = err_resp_mock
        yield mock


@pytest.mark.asyncio                                          
@pytest.mark.parametrize('user_id, url, kwargs, expected_result', 
                        [(None, f'{DEFAULT_BASE_URL}/api/1.0/users/client/profile', dict(), RESPONSE_RV['result']), 
                         (USER_ID, f'{DEFAULT_BASE_URL}/api/1.0/users/profile/{USER_ID}', dict(meta=None), RESPONSE_RV)])
async def test_profile_must_do_proper_http_request(sut, user_id, url, kwargs, expected_result, api_key, aiohttp_request_mock):
    result = await sut.profile(user_id, **kwargs)

    assert expected_result == result
    aiohttp_request_mock.assert_called_with(method='GET', url=url, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio                                          
async def test_profile_must_raise_if_request_fails(sut, aiohttp_request_mock):
    aiohttp_request_mock.side_effect = ClientConnectionError

    with pytest.raises(MindsyncApiError):
        await sut.profile()


@pytest.mark.asyncio                                          
async def test_profile_must_raise_if_result_is_malformed(sut, resp_mock, aiohttp_request_mock):
    resp_mock.json.return_value = dict()

    with pytest.raises(MindsyncApiError):
        await sut.profile()


@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_args', [(dict(first_name='Jim', last_name='Carrey', phone='1234567'), 
                                            dict(lastName='Carrey', firstName='Jim',  phone='1234567'))])
async def test_set_profile_must_do_proper_http_request(sut, args, expected_args, api_key, 
                                                         aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.set_profile(**args)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='PUT', 
                                            url=f'{DEFAULT_BASE_URL}/api/1.0/users/client/profile', 
                                            json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)

# RIGS

@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_url', [(dict(my=True), f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/my'), 
                                                (dict(my=False), f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs')])
async def test_rigs_list_must_do_proper_http_request(sut, args, expected_url, api_key, aiohttp_request_mock):
    result = await sut.rigs_list(**args)

    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rigs_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
    result = await sut.rig_info(rig_id=RIG_ID)

    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}/state', proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rig_price_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
    result = await sut.rig_price(rig_id=RIG_ID)

    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}/price', proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rigs_info_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
    rv = ERROR_RESPONSE_RV
    with pytest.raises(MindsyncApiError) as exc_info:
        await raise_sut.rig_info(rig_id=RIG_ID)

    exc = exc_info.value
    assert exc.args[0] == rv['error']['code']
    assert exc.args[1] == rv['error']['name']
    assert exc.args[2] == rv['error']['message']
    assert exc.args[3] == rv


@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_args, expected_result', [
                         (dict(rig_id=RIG_ID, enable=True, power_cost=0.25, meta=None), dict(isEnable=True, powerCost=0.25), RESPONSE_RV),
                         (dict(rig_id=RIG_ID, enable=True, power_cost=0.25), dict(isEnable=True, powerCost=0.25), RESPONSE_RV['result']),
                         ])
async def test_set_rig_must_do_proper_http_request(sut, args, expected_args, expected_result, api_key, 
                                                   aiohttp_request_mock, resp_mock):
    result = await sut.set_rig(**args)

    assert expected_result == result
    aiohttp_request_mock.assert_called_with(method='PUT', 
                                            url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}', 
                                            json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)

# RENTS

@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_args', [(dict(rig_id=RIG_ID, tariff_name='demo'), 
                                                 dict(rigHash=RIG_ID, tariffName='demo'))])
async def test_start_rent_must_do_proper_http_request(sut, args, expected_args, api_key, 
                                                         aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.start_rent(**args)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='POST', 
                                            url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/start', 
                                            json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_start_rent_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
    rv = ERROR_RESPONSE_RV
    args = dict(rig_id=RIG_ID, tariff_name='demo')
    with pytest.raises(MindsyncApiError) as exc_info:
        rv = await raise_sut.start_rent(**args)

    exc = exc_info.value
    assert exc.args[0] == rv['error']['code']
    assert exc.args[1] == rv['error']['name']
    assert exc.args[2] == rv['error']['message']
    assert exc.args[3] == rv


@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_args, expected_result', [(dict(rent_id=RENT_ID, meta=None), dict(hash=RENT_ID), RESPONSE_RV),
                                                                  (dict(rent_id=RENT_ID), dict(hash=RENT_ID), RESPONSE_RV['result'])])
async def test_stop_rent_must_do_proper_http_request(sut, args, expected_args, expected_result, api_key, 
                                                         aiohttp_request_mock, resp_mock):
    result = await sut.stop_rent(**args)

    assert expected_result == result
    aiohttp_request_mock.assert_called_with(method='POST', 
                                            url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/stop', 
                                            json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rent_state_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.rent_state(uuid=UUID)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}', proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rent_states_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.rent_states(uuid=UUID)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}/states', proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_rent_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.rent_state(uuid=UUID)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}', proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('args, expected_args', [(dict(rent_id=RENT_ID, enable=True, login='login', password='password'), 
                                                 dict(isEnable=True, login='login', password='password'))])
async def test_set_rent_must_do_proper_http_request(sut, args, expected_args, api_key, 
                                                         aiohttp_request_mock, resp_mock):
    resp_mock.json.return_value = dict(result='OK')
    result = await sut.set_rent(**args)

    assert 'OK' == result
    aiohttp_request_mock.assert_called_with(method='PUT', 
                                            url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{RENT_ID}', 
                                            json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_set_rent_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
    rv = ERROR_RESPONSE_RV
    args = dict(rent_id=RENT_ID, enable=True, login='login', password='password')
    with pytest.raises(MindsyncApiError) as exc_info:
        rv = await raise_sut.set_rent(**args)

    exc = exc_info.value
    assert exc.args[0] == rv['error']['code']
    assert exc.args[1] == rv['error']['name']
    assert exc.args[2] == rv['error']['message']
    assert exc.args[3] == rv


# CODES

@pytest.mark.asyncio
async def test_codes_list_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
    result = await sut.codes_list(proxy=PROXY_URL)
    expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes'

    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=PROXY_URL,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_create_code_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, open_mock, form_data):
    result = await sut.create_code(proxy=PROXY_URL, file=SOME_FN)
    expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes'

    # data = dict(file=open_mock.return_value, isPrivate='false')
    data=form_data

    open_mock.assert_called_with(SOME_FN, 'rb')
    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='POST', url=expected_url, proxy=PROXY_URL, 
                                            data=form_data, headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_create_code_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock, open_mock):
    rv = ERROR_RESPONSE_RV
    args = dict(rent_id=RENT_ID, enable=True, login='login', password='password')
    with pytest.raises(MindsyncApiError) as exc_info:
        rv = await raise_sut.create_code(proxy=PROXY_URL, file=SOME_FN)

    exc = exc_info.value
    assert exc.args[0] == rv['error']['code']
    assert exc.args[1] == rv['error']['name']
    assert exc.args[2] == rv['error']['message']
    assert exc.args[3] == rv


@pytest.mark.asyncio
async def test_run_code_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
    result = await sut.run_code(code_id=CODE_ID, rent_id=RENT_ID)
    expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes/{CODE_ID}/run'

    data=form_data

    assert RESPONSE_RV['result'] == result
    expected_args = dict(rentHash=RENT_ID)
    aiohttp_request_mock.assert_called_with(method='POST', url=expected_url,  json=expected_args, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)


@pytest.mark.asyncio
async def test_code_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
    result = await sut.code_info(code_id=CODE_ID)
    expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes/{CODE_ID}'

    assert RESPONSE_RV['result'] == result
    aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=None,
                                            headers={'api-key': api_key}, raise_for_status=False)
