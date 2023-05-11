from share import extract_tar, TestDoc, mongo_connect

from cobra.api import default_hooks_dir

import pytest

import tempfile
import time
import os
from os.path import join, exists
from filecmp import cmpfiles
from subprocess import check_call
from docker.errors import NotFound
from shutil import rmtree
from mongoengine import disconnect
import shutil


KEY_FN = '/test/.key.json'
# use shared volume between dind and test container to make stuff visible in bind mounts
BACKUP_DIR = '/shared/backup'
CACHE_DIR = '/shared/cache'


def compare_tars(source_tar_data, dest_tar_data, file_names):
    with tempfile.TemporaryDirectory(prefix='cobra-test-') as temp_dir:
        source_dir = join(temp_dir, '1')
        dest_dir = join(temp_dir, '2')
        extract_tar(source_dir, source_tar_data)
        extract_tar(dest_dir, dest_tar_data)
        source_dir = join(source_dir, 'files')
        dest_dir = join(dest_dir, 'files')
        return cmpfiles(source_dir, dest_dir, file_names, shallow=False)


def test_must_backup_and_restore_files_from_named_volume(client, files_volume, source_tar_data, files_container, file_names, folder_id):
    check_call(['cobra', 'backup', 'build', '--backup-dir', BACKUP_DIR, '--push', 
                '--creds', KEY_FN, '--folder-id', folder_id])

    files_container.remove(v=True, force=True)
    files_volume.remove(force=True)

    with pytest.raises(NotFound):
        client.volumes.get('files')

    check_call(['cobra', 'backup', 'pull', '--latest', '--restore', '--cache-dir', CACHE_DIR,
                '--creds', KEY_FN, '--folder-id', folder_id])

    files_volume = client.volumes.get('files')
    files_container = client.containers.create('alpine:3.17', name='files', 
        volumes=dict(files=dict(bind='/files', mode='rw')))
    stream, _ = files_container.get_archive('/files', chunk_size=None)
    dest_tar_data = next(stream)

    _, diff, errors = compare_tars(source_tar_data, dest_tar_data, file_names)
    assert not diff and not errors



MONGO_DUMP_DIR = '/shared/mongodb-dump'
BEFORE_BUILD_HOOK = f'''#!/usr/bin/env bash

# In real app stop any containers that mangle database while dumping to have consistent dump
# docker stop myapp

mkdir -p {MONGO_DUMP_DIR}
mongodump --archive={MONGO_DUMP_DIR}/mongo-dump-by-hook.tar.gz --db=test --gzip mongodb://cobra-e2e-tests-dind:27017

# Then start them again
# docker start myapp
'''

AFTER_RESTORE_HOOK = f'''#!/usr/bin/env bash

# In real app stop any containers that mangle database while restoring
# docker stop myapp

mongorestore --archive={MONGO_DUMP_DIR}/mongo-dump-by-hook.tar.gz --db=test --gzip mongodb://cobra-e2e-tests-dind:37017

# Then start them again
# docker start myapp
'''


def before_build_hook():
    return BEFORE_BUILD_HOOK


def after_restore_hook():
    return AFTER_RESTORE_HOOK


def run_mongodump(file_name, port=27017):
    check_call(['mongodump', f'--archive={file_name}', '--db=test', 
                '--gzip', f'mongodb://cobra-e2e-tests-dind:{port}'])


def put_hook(hooks_dir, hook_name, hook_content):
    os.makedirs(hooks_dir, exist_ok=True)
    hook_full_fn = join(hooks_dir, f'{hook_name}.sh')
    with open(hook_full_fn, 'w') as f:
        f.write(hook_content)
    os.chmod(hook_full_fn, 0o755)


def wait_for_port(port):
    check_call(['./wait-for-it.sh', f'cobra-e2e-tests-dind:{port}', '-t', '30'])


@pytest.fixture
def hooks_dir():
    return '/tmp/mongo-hooks'


@pytest.fixture
def hooks(hooks_dir):
    put_hook(hooks_dir, 'before_build', before_build_hook())
    put_hook(hooks_dir, 'after_restore', after_restore_hook())
    yield
    shutil.rmtree(hooks_dir)


def test_must_backup_and_restore_mongo_db_from_named_volume_via_mongodump(client, mongo_containers, hooks, hooks_dir,
                                                                          mongo_client, mongo_docs, folder_id):

    wait_for_port(27017)
    wait_for_port(37017)
    before_backup = list(TestDoc.objects())

    check_call(['cobra', 'backup', '--hooks-dir', hooks_dir, 'build', '--push', 
                '--backup-dir', BACKUP_DIR, '--dir', MONGO_DUMP_DIR,
                '--creds', KEY_FN, '--folder-id', folder_id, 
                '--exclude', 'mongo1', 'mongo2'])

    mongo_containers[0].remove(v=True, force=True)
    client.volumes.get('mongo1').remove(force=True)
    rmtree(MONGO_DUMP_DIR)

    with pytest.raises(NotFound):
        client.volumes.get('mongo1')

    check_call(['cobra', 'backup', '--hooks-dir', hooks_dir, 'pull', '--latest', 
                '--restore', '--cache-dir', CACHE_DIR,
                '--creds', KEY_FN, '--folder-id', folder_id])

    with pytest.raises(NotFound):
        client.volumes.get('mongo1')

    disconnect()
    mongo_connect(port=37017)
    after_restore = list(TestDoc.objects())

    for before, after in zip(before_backup, after_restore):
        assert before == after


def test_must_backup_and_restore_by_using_cache_dir(client, files_volume, source_tar_data, files_container, file_names):
    check_call(['cobra', 'backup', 'build', '--backup-dir', BACKUP_DIR])

    files_container.remove(v=True, force=True)
    files_volume.remove(force=True)

    with pytest.raises(NotFound):
        client.volumes.get('files')

    backup_fn = os.listdir(BACKUP_DIR)[0]
    check_call(['cobra', 'backup', 'restore', '--cache-dir', BACKUP_DIR, backup_fn])

    files_volume = client.volumes.get('files')
    files_container = client.containers.create('alpine:3.17', name='files', 
        volumes=dict(files=dict(bind='/files', mode='rw')))
    stream, _ = files_container.get_archive('/files', chunk_size=None)
    dest_tar_data = next(stream)

    _, diff, errors = compare_tars(source_tar_data, dest_tar_data, file_names)
    assert not diff and not errors
