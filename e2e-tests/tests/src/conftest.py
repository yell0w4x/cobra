from share import rand_str, TestDoc, mongo_connect

import pytest

import docker
import os
import tempfile
import tarfile
import hashlib
import io
from os.path import join, basename
from mongoengine import connect


FILES_NUM = 5
FILE_SIZE = 1024


def tar_content_md5(fn):
    with tarfile.open(tar_fn, 'r') as tar:
        tar.add(temp_dir)


def md5(data):
    hash = hashlib.md5()
    hash.update(data)
    return hash.hexdigest()


@pytest.fixture
def folder_id():
    try:
        return os.environ['GOOGLE_DRIVE_FOLDER_ID']
    except KeyError as e:
        raise RuntimeError('Please set GOOGLE_DRIVE_FOLDER_ID environment variable') from e


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


@pytest.fixture
def mongo_volume1(client):
    return client.volumes.create('mongo1')


@pytest.fixture
def mongo_volume2(client):
    return client.volumes.create('mongo2')


@pytest.fixture
def mongo_volumes(mongo_volume1, mongo_volume2):
    return mongo_volume1, mongo_volume2


def remove_container_safely(client, container):
    try:
        container = client.containers.get(container.name)
    except docker.errors.NotFound:
        pass
    else:
        container.remove(v=True, force=True)


@pytest.fixture
def files_container(client, files_volume, file_names, source_tar_data):
    client.images.pull('alpine:3.17')
    container = client.containers.create('alpine:3.17', name='files', 
        volumes=dict(files=dict(bind='/files', mode='rw')))
    try:
        if not container.put_archive('/', source_tar_data):
            raise RuntimeError('Unable to put files inside a container')
    except BaseException:
        container.remove()
        raise

    yield container
    remove_container_safely(client, container)


@pytest.fixture
def mongo_client():
    return mongo_connect()


@pytest.fixture
def mongo_docs():
    TestDoc(name='Jonny Walker', amount=1000, factor=0.25).save()
    TestDoc(name='Madonna', amount=10000, factor=0.55).save()
    TestDoc(name='Elvis Presley', amount=9999, factor=0.75).save()
    TestDoc(name='Jim Carrey', amount=99999, factor=1.2).save()


MONGO_DOCKER_IMAGE = 'mongo:6.0'


@pytest.fixture
def mongo_container1(client, mongo_volume1):
    client.images.pull(MONGO_DOCKER_IMAGE)
    container = client.containers.run(MONGO_DOCKER_IMAGE, name='mongo1', ports={'27017/tcp': 27017},
        volumes=dict(mongo1=dict(bind='/data/db', mode='rw')), detach=True)
    yield container
    remove_container_safely(client, container)


@pytest.fixture
def mongo_container2(client, mongo_volume2):
    client.images.pull(MONGO_DOCKER_IMAGE)
    container = client.containers.run(MONGO_DOCKER_IMAGE, name='mongo2', ports={'27017/tcp': 37017},
        volumes=dict(mongo2=dict(bind='/data/db', mode='rw')), detach=True)
    yield container
    remove_container_safely(client, container)


@pytest.fixture
def mongo_containers(mongo_container1, mongo_container2):
    return mongo_container1, mongo_container2
