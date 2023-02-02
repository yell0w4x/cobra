from coverme.api import Api, CovermeApiError, DEFAULT_BASE_URL, default_backup_dir
from coverme.hooks import Hooks

import pytest
from unittest.mock import patch, AsyncMock, create_autospec, MagicMock

# from aiohttp import ClientResponse, ClientConnectionError, FormData
from io import IOBase
from docker import DockerClient
from docker.models.volumes import Volume
from datetime import datetime
from freezegun import freeze_time
from os.path import join, abspath, realpath, basename
import json, copy


# VOLUMES = [
#     dict(id='volume1', name='volume1', attrs={ 'Id': 'Volume1', 'Name': 'volume1', 'CreatedAt': None, 'Driver': None, 'Mountpoint': None }),
#     dict(id='volume2', name='volume2', attrs={ 'CreatedAt': None, 'Driver': None, 'Mountpoint': None }),
#     dict(id='volume3', name='volume3', attrs={ 'CreatedAt': None, 'Driver': None, 'Mountpoint': None }),
# ]

VOLUMES = [
    { 'Id': 'Volume1', 'Name': 'volume1', 'CreatedAt': None, 'Driver': None, 'Mountpoint': None },
    { 'Id': 'Volume2', 'Name': 'volume2', 'CreatedAt': None, 'Driver': None, 'Mountpoint': None },
    { 'Id': 'Volume3', 'Name': 'volume3', 'CreatedAt': None, 'Driver': None, 'Mountpoint': None },
]
DOCKER_RUN_RV = b'files\nlist'


def make_volume_mock(attrs):
    mock = create_autospec(Volume, spec_set=False, instance=True)
    mock.id = id
    mock.name = name
    mock.attrs = attrs
    return mock


def make_volumes_list():
    return [Volume(VOLUMES[i]) for i in range(len(VOLUMES))]


@pytest.fixture
def volumes_list():
    return make_volumes_list()


@pytest.fixture
def docker_client_mock(volumes_list):
    mock = create_autospec(DockerClient, spec_set=True, instance=True)
    mock.volumes.list.return_value = volumes_list
    mock.containers.run.return_value = DOCKER_RUN_RV
    return mock


@pytest.fixture
def hooks_mock():
    return create_autospec(Hooks, spec_set=True, instance=True)


@pytest.fixture
def sut(docker_client_mock, hooks_mock):
    return Api(gateway=docker_client_mock, hooks=hooks_mock)


@pytest.fixture
def scratch_datetime():
    return datetime(year=2000, month=5, day=5, hour=0, minute=1, second=0)


@pytest.fixture
def backup_basename():
    return 'backup'


@pytest.fixture
def backup_name(backup_basename, scratch_datetime):
    return f'{backup_basename}@{scratch_datetime:%Y%m%d.%H%M%S}'


@pytest.fixture
def volume_opts(volumes_list, backup_name):
    container_backup_dir = f'/{backup_name}'
    volume_opts = { v.name: dict(bind=join(container_backup_dir, v.name), mode='ro') for v in volumes_list }
    host_backup_dir = abspath(default_backup_dir())
    # output dir mapped to host where the dest compressed file will reside
    volume_opts[host_backup_dir] = dict(bind='/backup', mode='rw')
    return volume_opts


@pytest.fixture
def dirs():
    DIR1 = '/dir1/dir1/dir1'
    DIR2 = '/dir2'
    return DIR1, DIR2


@pytest.fixture
def volume_opts_with_dirs(volume_opts, dirs, backup_name):
    container_backup_dir = f'/{backup_name}'
    # metadata = copy.deepcopy(volume_opts)
    extra_vopts = dict()
    extra_vopts[dirs[0]] = dict(bind=join(container_backup_dir, basename(dirs[0])), mode='ro')
    extra_vopts[dirs[1]] = dict(bind=join(container_backup_dir, basename(dirs[1])), mode='ro')
    # metadata |= copy.deepcopy(extra_vopts)
    return volume_opts | extra_vopts


@pytest.fixture
def open_mock():
    with patch('builtins.open') as mock:
        mock_enter_rv = MagicMock()
        mock.return_value.__enter__.return_value = mock_enter_rv
        yield mock


@pytest.fixture
def json_dump_mock():
    with patch('json.dump') as mock:
        yield mock


@pytest.fixture
def exists_mock():
    with patch('os.path.exists') as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def files_list():
    return ['file1', 'file2', 'file3']


@pytest.mark.parametrize('volume_names, expected', [(None, make_volumes_list()),
                                                    (('volume1',), [item for item in make_volumes_list() if item.name in ('volume1',)]),
                                                    (('volume1', 'volume2'), [item for item in make_volumes_list() if item.name in ('volume1', 'volume2')])])
def test_volumes_list_must_return_docker_volumes_list(sut, volume_names, expected):
    assert expected == sut.volumes_list(volume_names=volume_names)


@pytest.mark.parametrize('dir_names, expected_volume_opts', [(None, pytest.lazy_fixture('volume_opts')), 
                                                            (pytest.lazy_fixture('dirs'), pytest.lazy_fixture('volume_opts_with_dirs'))])
def test_backend_build_must_call_docker_run_with_correct_params(sut, scratch_datetime, dir_names, expected_volume_opts,
                                                                docker_client_mock, backup_name, open_mock, json_dump_mock):
    host_backup_dir=default_backup_dir()
    with freeze_time(scratch_datetime) as ft:
        rv = sut.backup_build(dir_names=dir_names, host_backup_dir=host_backup_dir)
        assert rv == str(DOCKER_RUN_RV, encoding='utf-8')
        container_backup_dir = f'/{backup_name}'
        backup_archive_fn = f'{backup_name}.tar.gz'
        container_backup_archive_fn = join('/backup', backup_archive_fn)
        command=['sh', '-c', f'mv /backup/... {container_backup_dir} && tar -czvf {container_backup_archive_fn} {container_backup_dir}']
        docker_client_mock.containers.run.assert_called_with('busybox', remove=True, 
                                                              volumes=expected_volume_opts, command=command)
        metadata = copy.deepcopy(expected_volume_opts)                                                              
        del metadata[host_backup_dir]
        metadata_fn = join(host_backup_dir, '...')
        open_mock.assert_called_with(metadata_fn, 'w')
        json_dump_mock.assert_called_with(metadata, open_mock.return_value.__enter__.return_value)


@pytest.mark.parametrize('creds, folder_id, file_exists, expected_exc', 
                        [(None, None, True, ValueError), 
                        (None, 'folder-id', True, ValueError), 
                        ('creds.json', 'folder-id', False, FileNotFoundError), 
                        ('creds.json', None, True, ValueError)])
def test_push_must_check_args(sut, exists_mock, creds, folder_id, file_exists, expected_exc):
    exists_mock.return_value = file_exists
    with pytest.raises(expected_exc):
        sut.backup_push([], creds, folder_id)


# class FormDataMatcher(FormData):
#     def __eq__(self, other):
#         return self._fields == other._fields


# @pytest.fixture
# def form_data(open_mock):
#     data = FormDataMatcher()
#     data.add_field('file', open_mock.return_value, content_type='application/octet-stream')
#     data.add_field('isPrivate', 'false')
#     return data


# @pytest.fixture
# def aiohttp_request_mock(resp_mock):
#     with patch('aiohttp.request') as mock:
#         mock.return_value.__aenter__.return_value = resp_mock
#         yield mock


# @pytest.fixture
# def err_aiohttp_request_mock(err_resp_mock):
#     with patch('aiohttp.request') as mock:
#         mock.return_value.__aenter__.return_value = err_resp_mock
#         yield mock


# @pytest.mark.asyncio                                          
# @pytest.mark.parametrize('user_id, url, kwargs, expected_result', 
#                         [(None, f'{DEFAULT_BASE_URL}/api/1.0/users/client/profile', dict(), RESPONSE_RV['result']), 
#                          (USER_ID, f'{DEFAULT_BASE_URL}/api/1.0/users/profile/{USER_ID}', dict(meta=None), RESPONSE_RV)])
# async def test_profile_must_do_proper_http_request(sut, user_id, url, kwargs, expected_result, api_key, aiohttp_request_mock):
#     result = await sut.profile(user_id, **kwargs)

#     assert expected_result == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=url, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio                                          
# async def test_profile_must_raise_if_request_fails(sut, aiohttp_request_mock):
#     aiohttp_request_mock.side_effect = ClientConnectionError

#     with pytest.raises(MindsyncApiError):
#         await sut.profile()


# @pytest.mark.asyncio                                          
# async def test_profile_must_raise_if_result_is_malformed(sut, resp_mock, aiohttp_request_mock):
#     resp_mock.json.return_value = dict()

#     with pytest.raises(MindsyncApiError):
#         await sut.profile()


# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_args', [(dict(first_name='Jim', last_name='Carrey', phone='1234567'), 
#                                             dict(lastName='Carrey', firstName='Jim',  phone='1234567'))])
# async def test_set_profile_must_do_proper_http_request(sut, args, expected_args, api_key, 
#                                                          aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.set_profile(**args)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='PUT', 
#                                             url=f'{DEFAULT_BASE_URL}/api/1.0/users/client/profile', 
#                                             json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)

# # RIGS

# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_url', [(dict(my=True), f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/my'), 
#                                                 (dict(my=False), f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs')])
# async def test_rigs_list_must_do_proper_http_request(sut, args, expected_url, api_key, aiohttp_request_mock):
#     result = await sut.rigs_list(**args)

#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rigs_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
#     result = await sut.rig_info(rig_id=RIG_ID)

#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}/state', proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rig_price_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
#     result = await sut.rig_price(rig_id=RIG_ID)

#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}/price', proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rigs_info_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
#     rv = ERROR_RESPONSE_RV
#     with pytest.raises(MindsyncApiError) as exc_info:
#         await raise_sut.rig_info(rig_id=RIG_ID)

#     exc = exc_info.value
#     assert exc.args[0] == rv['error']['code']
#     assert exc.args[1] == rv['error']['name']
#     assert exc.args[2] == rv['error']['message']
#     assert exc.args[3] == rv


# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_args, expected_result', [
#                          (dict(rig_id=RIG_ID, enable=True, power_cost=0.25, meta=None), dict(isEnable=True, powerCost=0.25), RESPONSE_RV),
#                          (dict(rig_id=RIG_ID, enable=True, power_cost=0.25), dict(isEnable=True, powerCost=0.25), RESPONSE_RV['result']),
#                          ])
# async def test_set_rig_must_do_proper_http_request(sut, args, expected_args, expected_result, api_key, 
#                                                    aiohttp_request_mock, resp_mock):
#     result = await sut.set_rig(**args)

#     assert expected_result == result
#     aiohttp_request_mock.assert_called_with(method='PUT', 
#                                             url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rigs/{RIG_ID}', 
#                                             json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)

# # RENTS

# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_args', [(dict(rig_id=RIG_ID, tariff_name='demo'), 
#                                                  dict(rigHash=RIG_ID, tariffName='demo'))])
# async def test_start_rent_must_do_proper_http_request(sut, args, expected_args, api_key, 
#                                                          aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.start_rent(**args)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='POST', 
#                                             url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/start', 
#                                             json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_start_rent_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
#     rv = ERROR_RESPONSE_RV
#     args = dict(rig_id=RIG_ID, tariff_name='demo')
#     with pytest.raises(MindsyncApiError) as exc_info:
#         rv = await raise_sut.start_rent(**args)

#     exc = exc_info.value
#     assert exc.args[0] == rv['error']['code']
#     assert exc.args[1] == rv['error']['name']
#     assert exc.args[2] == rv['error']['message']
#     assert exc.args[3] == rv


# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_args, expected_result', [(dict(rent_id=RENT_ID, meta=None), dict(hash=RENT_ID), RESPONSE_RV),
#                                                                   (dict(rent_id=RENT_ID), dict(hash=RENT_ID), RESPONSE_RV['result'])])
# async def test_stop_rent_must_do_proper_http_request(sut, args, expected_args, expected_result, api_key, 
#                                                          aiohttp_request_mock, resp_mock):
#     result = await sut.stop_rent(**args)

#     assert expected_result == result
#     aiohttp_request_mock.assert_called_with(method='POST', 
#                                             url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/stop', 
#                                             json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rent_state_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.rent_state(uuid=UUID)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}', proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rent_states_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.rent_states(uuid=UUID)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}/states', proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_rent_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.rent_state(uuid=UUID)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{UUID}', proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# @pytest.mark.parametrize('args, expected_args', [(dict(rent_id=RENT_ID, enable=True, login='login', password='password'), 
#                                                  dict(isEnable=True, login='login', password='password'))])
# async def test_set_rent_must_do_proper_http_request(sut, args, expected_args, api_key, 
#                                                          aiohttp_request_mock, resp_mock):
#     resp_mock.json.return_value = dict(result='OK')
#     result = await sut.set_rent(**args)

#     assert 'OK' == result
#     aiohttp_request_mock.assert_called_with(method='PUT', 
#                                             url=f'{DEFAULT_BASE_URL}/api/{API_VERSION}/rents/{RENT_ID}', 
#                                             json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_set_rent_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock):
#     rv = ERROR_RESPONSE_RV
#     args = dict(rent_id=RENT_ID, enable=True, login='login', password='password')
#     with pytest.raises(MindsyncApiError) as exc_info:
#         rv = await raise_sut.set_rent(**args)

#     exc = exc_info.value
#     assert exc.args[0] == rv['error']['code']
#     assert exc.args[1] == rv['error']['name']
#     assert exc.args[2] == rv['error']['message']
#     assert exc.args[3] == rv


# # CODES

# @pytest.mark.asyncio
# async def test_codes_list_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
#     result = await sut.codes_list(proxy=PROXY_URL)
#     expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes'

#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=PROXY_URL,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_create_code_must_do_proper_http_request(sut, api_key, aiohttp_request_mock, open_mock, form_data):
#     result = await sut.create_code(proxy=PROXY_URL, file=SOME_FN)
#     expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes'

#     # data = dict(file=open_mock.return_value, isPrivate='false')
#     data=form_data

#     open_mock.assert_called_with(SOME_FN, 'rb')
#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='POST', url=expected_url, proxy=PROXY_URL, 
#                                             data=form_data, headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_create_code_must_raise_on_error_if_raise_for_error_set(raise_sut, api_key, err_aiohttp_request_mock, open_mock):
#     rv = ERROR_RESPONSE_RV
#     args = dict(rent_id=RENT_ID, enable=True, login='login', password='password')
#     with pytest.raises(MindsyncApiError) as exc_info:
#         rv = await raise_sut.create_code(proxy=PROXY_URL, file=SOME_FN)

#     exc = exc_info.value
#     assert exc.args[0] == rv['error']['code']
#     assert exc.args[1] == rv['error']['name']
#     assert exc.args[2] == rv['error']['message']
#     assert exc.args[3] == rv


# @pytest.mark.asyncio
# async def test_run_code_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
#     result = await sut.run_code(code_id=CODE_ID, rent_id=RENT_ID)
#     expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes/{CODE_ID}/run'

#     data=form_data

#     assert RESPONSE_RV['result'] == result
#     expected_args = dict(rentHash=RENT_ID)
#     aiohttp_request_mock.assert_called_with(method='POST', url=expected_url,  json=expected_args, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)


# @pytest.mark.asyncio
# async def test_code_info_must_do_proper_http_request(sut, api_key, aiohttp_request_mock):
#     result = await sut.code_info(code_id=CODE_ID)
#     expected_url = f'{DEFAULT_BASE_URL}/api/{API_VERSION}/codes/{CODE_ID}'

#     assert RESPONSE_RV['result'] == result
#     aiohttp_request_mock.assert_called_with(method='GET', url=expected_url, proxy=None,
#                                             headers={'api-key': api_key}, raise_for_status=False)
