import docker
import string, random, json
import tarfile
import io
from mongoengine import Document, StringField, IntField, FloatField, connect


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def extract_tar(path, tar_data):
    with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
        tar.extractall(path=path)


def mongo_connect(port=27017):
    return connect(db='test', host='cobra-e2e-tests-dind', port=port, uuidRepresentation='standard')


class TestDoc(Document):
    __test__ = False

    name = StringField()
    amount = IntField()
    factor = FloatField()
