import docker
import string, random, json
import tarfile
import io


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def extract_tar(path, tar_data):
    with tarfile.open(fileobj=io.BytesIO(tar_data)) as tar:
        tar.extractall(path=path)


def run():
    pass
