from share import rand_str

import pytest

import docker
import os
import tempfile
import tarfile
import hashlib
import io
from os.path import join, basename


FILES_NUM = 5
FILE_SIZE = 1024


# def md5(fn):
#     with open(fn, 'rb') as f:
#         hash = hashlib.md5()
#         hash.update(f.read())
#         return hash.hexdigest()


def tar_content_md5(fn):
    with tarfile.open(tar_fn, 'r') as tar:
        tar.add(temp_dir)


def md5(data):
    hash = hashlib.md5()
    hash.update(data)
    return hash.hexdigest()



@pytest.fixture
def folder_id():
    return '100d96r89SxvJvm7ZUqFCOztaiZv6sBIA'


@pytest.fixture
def client():
    return docker.from_env()


@pytest.fixture
def file_names():
    return [rand_str() for _ in range(FILES_NUM)]


@pytest.fixture
def source_tar_data(file_names):
    def mangle_name(info):
        info.name = join('files', basename(info.name))
        return info

    with tempfile.TemporaryDirectory() as temp_dir:
        file_names = [join(temp_dir, fn) for fn in file_names]
        tar_fn = f'/tmp/{rand_str()}.tar'
        tar_io = io.BytesIO()
        with tarfile.open(tar_fn, 'w', format=tarfile.GNU_FORMAT) as tar:
            for fn in file_names:
                with open(fn, 'w') as f:
                    f.write(rand_str(FILE_SIZE))

                tar.add(fn, filter=mangle_name)

        with open(tar_fn, 'rb') as f:
            return f.read()


@pytest.fixture
def files_volume(client):
    return client.volumes.create('files')
    # client.volumes.create('mongodb')
    # client.volumes.create('postgres')


@pytest.fixture
def files_container(client, files_volume, file_names, source_tar_data):
    client.images.pull('alpine:3.17')
    files_container = client.containers.create('alpine:3.17', name='files', 
        volumes=dict(files=dict(bind='/files', mode='rw')))
    try:
        if not files_container.put_archive('/', source_tar_data):
            raise RuntimeError('Unable to put files inside a container')
    except BaseException:
        files_container.remove()
        raise

    yield files_container

    try:
        files_container = client.containers.get(files_container.name)
    except docker.errors.NotFound:
        pass
    else:
        files_container.remove()
