from share import extract_tar

from cobra.api import default_hooks_dir

import pytest

import tempfile
import time
import os
from os.path import join, exists
from filecmp import cmpfiles, cmp
from subprocess import check_call
from docker.errors import NotFound
from shutil import rmtree


def test_must_backup_and_restore_files_from_named_volume(client, files_volume, source_tar_data, files_container, file_names, folder_id):
    # # client.containers.run('alpine:3.17', volumes=dict(files=dict(bind='/files', mode='rw')))

    # use shared volume between dind and test container to make stuff visible in bind mounts
    check_call(['cobra', 'backup', 'build', '--backup-dir', '/shared/backup', '--push', 
                '--creds', './.key.json', '--folder-id', folder_id])

    files_container.remove(v=True, force=True)
    files_volume.remove(force=True)

    with pytest.raises(NotFound):
        client.volumes.get('files')

    check_call(['cobra', 'backup', 'pull', '--latest', '--restore', '--cache-dir', '/shared/cache',
                '--creds', './.key.json', '--folder-id', folder_id])

    files_volume = client.volumes.get('files')
    files_container = client.containers.create('alpine:3.17', name='files', 
        volumes=dict(files=dict(bind='/files', mode='rw')))
    stream, _ = files_container.get_archive('/files', chunk_size=None)
    dest_tar_data = next(stream)

    with tempfile.TemporaryDirectory(prefix='cobra-test-') as temp_dir:
        source_dir = join(temp_dir, '1')
        dest_dir = join(temp_dir, '2')
        extract_tar(source_dir, source_tar_data)
        extract_tar(dest_dir, dest_tar_data)
        source_dir = join(source_dir, 'files')
        dest_dir = join(dest_dir, 'files')
        _, diff, errors = cmpfiles(source_dir, dest_dir, file_names, shallow=False)
    
    assert not diff and not errors


MONGO_DUMP_DIR = '/shared/mongodb-dump'
BEFORE_BUILD_HOOK = f'''#!/usr/bin/env bash

mkdir -p {MONGO_DUMP_DIR}
mongodump --archive={MONGO_DUMP_DIR}/mongo-dump-by-hook.tar.gz --db=test --gzip mongodb://cobra-e2e-tests-dind:27017
'''

AFTER_RESTORE_HOOK = f'''#!/usr/bin/env bash

docker run -p 27017:27017 -v mongo:/data/db -d --rm --name mongo mongo:6.0
# sleep 1000
mongorestore --archive={MONGO_DUMP_DIR}/mongo-dump-by-hook.tar.gz --db=test --gzip mongodb://cobra-e2e-tests-dind:27017
# docker stop mongo
'''


def before_build_hook():
    return BEFORE_BUILD_HOOK


def after_restore_hook():
    return AFTER_RESTORE_HOOK


def run_mongodump(file_name):
    check_call(['mongodump', f'--archive={file_name}', '--db=test', 
                '--gzip', 'mongodb://cobra-e2e-tests-dind:27017'])


def put_hook(hooks_dir, hook_name, hook_content):
    os.makedirs(hooks_dir, exist_ok=True)
    hook_full_fn = join(hooks_dir, f'{hook_name}.sh')
    with open(hook_full_fn, 'w') as f:
        f.write(hook_content)
    os.chmod(hook_full_fn, 0o755)


def wait_for_mongo_port():
    check_call(['./wait-for-it.sh', 'cobra-e2e-tests-dind:27017', '-t', '30'])


def test_must_backup_and_restore_mongo_db_from_named_volume_via_mongodump(client, mongo_container, mongo_client, 
                                                                          mongo_docs, mongo_volume, folder_id):
    hooks_dir = '/tmp/mongo-hooks'
    put_hook(hooks_dir, 'before_build', before_build_hook())
    put_hook(hooks_dir, 'after_restore', after_restore_hook())

    # wait_for_mongo_port()
    before_backup_fn = 'mongodb-test1.tar.gz'
    run_mongodump(before_backup_fn)

    check_call(['cobra', 'backup', '--hooks-dir', hooks_dir, 'build', '--push', 
                '--backup-dir', '/shared/backup', '--dir', MONGO_DUMP_DIR,
                '--creds', './.key.json', '--folder-id', folder_id, '--exclude', 'mongo'])

    # time.sleep(1000)
    mongo_container.remove(v=True, force=True)
    mongo_volume.remove(force=True)
    rmtree(MONGO_DUMP_DIR)

    with pytest.raises(NotFound):
        client.volumes.get('mongo')

    check_call(['cobra', 'backup', '--hooks-dir', hooks_dir, 'pull', '--latest', 
                '--restore', '--cache-dir', '/shared/cache',
                '--creds', './.key.json', '--folder-id', folder_id])

    # container = client.containers.run('mongo:6.0', name='mongo', ports={'27017/tcp': 27017},
    #     volumes=dict(mongo=dict(bind='/data/db', mode='rw')), detach=True)

    # wait_for_mongo_port()
    after_restore_fn = 'mongodb-test2.tar.gz'
    run_mongodump(after_restore_fn)

    # mongo_container = client.containers.get('mongo')
    # mongo_container.remove(v=True, force=True)
    # mongo_volume = client.volumes.get('mongo')
    # mongo_volume.remove(force=True)

    assert cmp(before_backup_fn, after_restore_fn, shallow=False)
