from coverme.api import Api, CovermeApiError, DEFAULT_BASE_URL, default_backup_dir
from coverme.hooks import Hooks

import pytest
from unittest.mock import patch, AsyncMock, create_autospec, MagicMock, call

# from aiohttp import ClientResponse, ClientConnectionError, FormData
from io import IOBase
from docker import DockerClient
from docker.models.volumes import Volume
from datetime import datetime
from freezegun import freeze_time
from os.path import join, abspath, realpath, basename, dirname
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
        mock.return_value = True
        yield mock


# @pytest.fixture
def files_list():
    return ['file1', 'file2', 'file3']


@pytest.fixture
def listdir_mock():
    with patch('os.listdir') as mock:
        mock.return_value = files_list()
        yield mock


@pytest.fixture
def upload_file_mock():
    class Status:
        def progress(self):
            return 1

    def rv():
        yield Status()

    with patch('coverme.google_drive.upload_file') as mock:
        mock.return_value = rv()
        yield mock


@pytest.fixture
def folder_list_mock():
    with patch('coverme.google_drive.folder_list') as mock:
        yield mock


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
def test_backup_push_must_check_args(sut, exists_mock, creds, folder_id, file_exists, expected_exc):
    exists_mock.return_value = file_exists
    with pytest.raises(expected_exc):
        sut.backup_push([], creds, folder_id)


@pytest.mark.parametrize('files, expected_files', [
        ([], [join(default_backup_dir(), fn) for fn in files_list()]),
        (['some_file1', './some_file2', '/some_dir/some_file3'], 
         [join(default_backup_dir(), 'some_file1'), realpath(abspath('./some_file2')), '/some_dir/some_file3'])])
def test_push_must_list_backup_dir_if_no_files_list_given(sut, files, expected_files, exists_mock, listdir_mock, upload_file_mock):
    creds, folder_id = 'creds', 'folder_id'
    sut.backup_push(files, creds, folder_id)

    calls = [call(creds, fn, 'application/gzip', basename(fn), folder_id) for fn in expected_files]
    upload_file_mock.assert_has_calls(calls)


def test_backup_list_must_list_local_or_remote_folder(sut, folder_list_mock, listdir_mock, exists_mock):
    creds, folder_id = 'creds', 'folder_id'
    assert listdir_mock.return_value == sut.backup_list(creds, folder_id, remote=False, backup_dir=default_backup_dir())
    assert folder_list_mock.return_value == sut.backup_list(creds, folder_id, remote=True, backup_dir=default_backup_dir())


@pytest.mark.parametrize('creds, folder_id, file_exists, expected_exc', 
                        [(None, None, True, ValueError), 
                        (None, 'folder-id', True, ValueError), 
                        ('creds.json', 'folder-id', False, FileNotFoundError), 
                        ('creds.json', None, True, ValueError)])
def test_backup_list_must_check_args(sut, exists_mock, creds, folder_id, file_exists, expected_exc):
    exists_mock.return_value = file_exists
    with pytest.raises(expected_exc):
        sut.backup_list(creds, folder_id, True, default_backup_dir())
