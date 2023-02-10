from share import extract_tar

import pytest

import tempfile
import time
from os.path import join
from filecmp import cmpfiles
from subprocess import check_output
import traceback


def test_smoke(client, source_tar_data, files_container, file_names, folder_id):
    # client.containers.run('alpine:3.17', volumes=dict(files=dict(bind='/files', mode='rw')))
    stream, _ = files_container.get_archive('/files', chunk_size=None)
    dest_tar_data = next(stream)

    # use shared volume between dind and test container to make stuff visible in bind mounts
    print(check_output(['cobra', 'backup', 'build', '--backup-dir', '/shared', '--push', 
                        '--creds', './.key.json', '--folder-id', folder_id]))

    with tempfile.TemporaryDirectory(prefix='cobra-test-') as temp_dir:
        source_dir = join(temp_dir, '1')
        dest_dir = join(temp_dir, '2')
        extract_tar(source_dir, source_tar_data)
        extract_tar(dest_dir, dest_tar_data)
        source_dir = join(source_dir, 'files')
        dest_dir = join(dest_dir, 'files')
        _, diff, errors = cmpfiles(source_dir, dest_dir, file_names, shallow=False)
    
    assert not diff and not errors
