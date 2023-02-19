from cobra.api import (Api, CobraApiError, DEFAULT_BASE_URL, 
    default_backup_dir, default_cache_dir, METADATA_FN)
from cobra.hooks import Hooks
from cobra.exc import CobraCliError

import pytest
from unittest.mock import patch, AsyncMock, create_autospec, MagicMock, call

# from aiohttp import ClientResponse, ClientConnectionError, FormData
from io import IOBase
from docker import DockerClient
from docker.models.volumes import Volume
from datetime import datetime
from freezegun import freeze_time
from os.path import join, abspath, realpath, basename, dirname, splitext
import json, copy


VOLUMES = [
    { 'Id': 'Volume1', 'Name': 'volume1', 'CreatedAt': None, 'Driver': 'local', 'Mountpoint': None, 'Options': None, 'Labels': None },
    { 'Id': 'Volume2', 'Name': 'volume2', 'CreatedAt': None, 'Driver': 'local', 'Mountpoint': None, 'Options': None, 'Labels': None },
    { 'Id': 'Volume3', 'Name': 'volume3', 'CreatedAt': None, 'Driver': 'local', 'Mountpoint': None, 'Options': None, 'Labels': None },
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
    # return Api(gateway=docker_client_mock, hooks=Hooks(hooks_dir='/home/q/work/cobra/.temp/hooks'))
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
    volume_opts = { 
        v.name: dict(bind=join(container_backup_dir, v.name), 
                        mode='ro') for v in volumes_list 
    }


    # volume_opts = { 
    #     v.name: dict(bind=join(container_backup_dir, v.name), 
    #                  mode='ro') for v in volumes_list }
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
    extra_vopts = dict()
    extra_vopts[dirs[0]] = dict(bind=join(container_backup_dir, basename(dirs[0])), mode='ro')
    extra_vopts[dirs[1]] = dict(bind=join(container_backup_dir, basename(dirs[1])), mode='ro')
    return volume_opts | extra_vopts


@pytest.fixture
def json_dump_mock():
    with patch('json.dump') as mock:
        yield mock


@pytest.fixture
def json_load_mock(volumes_metadata):
    with patch('json.load') as mock:
        mock.return_value = volumes_metadata
        yield mock


# @pytest.fixture
def files_list():
    return ['file1', 'file2', 'file3']


@pytest.fixture
def listdir_mock():
    with patch('os.listdir') as mock:
        mock.return_value = files_list()
        yield mock


class Status:
    def progress(self):
        return 1


@pytest.fixture
def upload_file_mock():
    def rv():
        yield Status()

    with patch('cobra.google_drive.upload_file') as mock:
        mock.return_value = rv()
        yield mock


def filename():
    return 'backup.tar.gz'


@pytest.fixture
def full_filename():
    return f'/some/file/{filename()}'


@pytest.fixture
def download_file_mock(full_filename):
    def rv():
        yield filename()
        yield Status()
        return full_filename

    with patch('cobra.google_drive.download_file') as mock:
        mock.return_value = rv()
        yield mock


@pytest.fixture
def folder_list_mock():
    with patch('cobra.google_drive.folder_list') as mock:
        yield mock


@pytest.fixture
def check_output_mock():
    with patch('subprocess.check_output') as mock:
        yield mock


@pytest.fixture
def volumes_metadata():
    return {
        "usb-stick": {
            "bind": "/backup@20230204.211624/usb-stick",
            "mode": "rw",
            "driver": "local",
            "options": {
                "device": "/dev/sda1",
                "type": "vfat"
            },
            "labels": {
                "16gb": "asdf",
                "mystick": "qwer"
            }
        },
        "/home/q/work/cobra/examples": {
            "bind": "/backup@20230204.211624/examples",
            "mode": "rw"
        }
    }

@pytest.mark.parametrize('include_volumes, exclude_volumes, expected', 
    [
        (None, None, make_volumes_list()),
        (('volume1',), None, [item for item in make_volumes_list() if item.name in ('volume1',)]),
        (('volume1', 'volume2'), None, [item for item in make_volumes_list() if item.name in ('volume1', 'volume2')]),
        (None, ['volume3'], [item for item in make_volumes_list() if item.name not in ('volume3',)]),
        (('volume1',), ['volume3'], [item for item in make_volumes_list() if item.name in ('volume1',)]),
        (('volume1', 'volume2'), ['volume3'], [item for item in make_volumes_list() if item.name in ('volume1', 'volume2')]),
    ])
def test_volumes_list_must_return_docker_volumes_list_according_include_and_exclude_options(sut, include_volumes, exclude_volumes, expected):
    assert expected == sut.volumes_list(include_volumes=include_volumes, exclude_volumes=exclude_volumes)


@pytest.mark.parametrize('include_volumes, exclude_volumes', [(['volume1', 'volume2'], ['volume2'])])
def test_volumes_list_must_raise_if_include_and_exlucde_lists_intersect(sut, include_volumes, exclude_volumes):
    with pytest.raises(CobraApiError):
        sut.volumes_list(include_volumes=include_volumes, exclude_volumes=exclude_volumes)


@pytest.mark.parametrize('dir_names, expected_volume_opts', [(None, pytest.lazy_fixture('volume_opts')), 
                                                            (pytest.lazy_fixture('dirs'), pytest.lazy_fixture('volume_opts_with_dirs'))])
def test_backend_build_must_call_docker_run_with_correct_params(sut, scratch_datetime, dir_names, expected_volume_opts,
                                                                docker_client_mock, backup_name, open_mock, json_dump_mock, volumes_list):
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
        exptected_metadata = copy.deepcopy(expected_volume_opts)                                                              
        del exptected_metadata[host_backup_dir]

        for v in volumes_list:
            exptected_metadata[v.name]['driver'] = v.attrs['Driver']
            exptected_metadata[v.name]['options'] = v.attrs['Options']
            exptected_metadata[v.name]['labels'] = v.attrs['Labels']

        metadata_fn = join(host_backup_dir, '...')
        open_mock.assert_called_with(metadata_fn, 'w')
        json_dump_mock.assert_called_with(exptected_metadata, open_mock.return_value.__enter__.return_value)


@pytest.mark.parametrize('creds, folder_id, file_exists, expected_exc', 
                        [(None, None, True, CobraCliError), 
                        (None, 'folder-id', True, CobraCliError), 
                        ('creds.json', 'folder-id', False, FileNotFoundError), 
                        ('creds.json', None, True, CobraCliError)])
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
                        [(None, None, True, CobraCliError), 
                        (None, 'folder-id', True, CobraCliError), 
                        ('creds.json', 'folder-id', False, FileNotFoundError), 
                        ('creds.json', None, True, CobraCliError)])
def test_backup_list_must_check_args(sut, exists_mock, creds, folder_id, file_exists, expected_exc):
    exists_mock.return_value = file_exists
    with pytest.raises(expected_exc):
        sut.backup_list(creds, folder_id, True, default_backup_dir())


@pytest.mark.parametrize('creds, file_id, file_exists, folder_id, latest, expected_exc', 
                        [(None, None, True, None, False, CobraCliError), 
                        (None, 'file-id', True, None, False, CobraCliError), 
                        ('creds.json', 'file-id', False, None, False, FileNotFoundError), 
                        ('creds.json', None, True, None, False, CobraCliError),
                        (None, None, True, None, True, CobraCliError), 
                        (None, None, True, 'folder-id', True, CobraCliError), 
                        ('creds.json', None, False, 'folder-id', True, CobraCliError),
                        ])
def test_backup_pull_must_check_args(sut, exists_mock, creds, file_id, file_exists, folder_id, latest, expected_exc):
    exists_mock.return_value = file_exists
    with pytest.raises(expected_exc):
        sut.backup_pull(creds, file_id, restore=True, cache_dir=default_cache_dir())


def test_pull_must_download_file(sut, download_file_mock, makedirs_mock, full_filename, exists_mock):
    creds, file_id = 'creds', 'file_id'
    assert full_filename == sut.backup_pull(creds, file_id, no_cache=True)
    cache_dir = default_cache_dir()
    makedirs_mock.assert_called_with(cache_dir, exist_ok=True)
    download_file_mock.assert_called_with(creds, file_id, cache_dir, use_cache=False)


@pytest.mark.parametrize('original_fn, fn', [(pytest.lazy_fixture('full_filename'), pytest.lazy_fixture('full_filename')),
                                             (filename(), join(default_cache_dir(), filename()))])
def test_restore_must_create_volumes_and_call_container_to_restore_files(sut, original_fn, fn, check_output_mock, 
                                                                         volumes_metadata, docker_client_mock, 
                                                                         open_mock, makedirs_mock, json_load_mock):
    metadata = copy.deepcopy(volumes_metadata)
    assert check_output_mock.return_value == sut.backup_restore(original_fn)
    host_backup_dir = dirname(fn)
    check_output_mock.assert_called_with(['tar', 'xvf', fn, '-C', host_backup_dir])

    backup_name, _ = splitext(splitext(basename(fn))[0])
    container_volumes_mount_dir = f'/{backup_name}'
    full_backup_archive_dir = join(host_backup_dir, backup_name)
    metadata_fn = join(full_backup_archive_dir, METADATA_FN)
    open_mock.assert_called_with(metadata_fn)
    json_load_mock.assert_called_with(open_mock.return_value.__enter__.return_value)
    makedirs_mock.assert_called_with('/home/q/work/cobra/examples', exist_ok=True)

    vol_meta = metadata['usb-stick']
    docker_client_mock.volumes.create.assert_called_with('usb-stick', driver=vol_meta['driver'], 
                                                         labels=vol_meta['labels'], driver_opts=vol_meta['options'])
    del vol_meta['driver'], vol_meta['labels'], vol_meta['options']
    metadata[host_backup_dir] = dict(bind='/backup', mode='ro')
    container_backup_archive_dir = join('/backup', backup_name, '*')
    command=['sh', '-c', f'cp -rf {container_backup_archive_dir} {container_volumes_mount_dir}']
    docker_client_mock.containers.run.assert_called_with('busybox', remove=True, volumes=metadata, command=command)

