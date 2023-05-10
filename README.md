# CoBRA - Comprehensive Backing up and Restoration Archiver

Cobra is a tool for creating, managing and restoring backups. 
It is designed to cover docker powered applications as well as it allows backing up of 
regular file system folders.

![Cobra cli](https://github.com/yell0w4x/assets/raw/main/cobra-cli.png)

## How to use

```
pip install cobra-archiver
```

### CLI

After that `cobra` command will be available from the command line.

To get the cli description please issue `cobra --help` or 
e.g. `cobra backup --help` to get help on certain command.

This will backup all the docker volumes as well as `/want/this/dir/backed/up` 
directory, but `skip-this-volume` `and-this-one`.

```bash
cobra backup build --push --dir /want/this/dir/backed/up \
    --creds /path/to/google-service-acc-key.json --folder-id google-drive-folder-id \
    --exclude skip-this-volume and-this-one
```

This restores latest backup from the given remote folder.

```bash
cobra backup pull --latest --restore \
    --creds /path/to/google-service-acc-key.json --folder-id google-drive-folder-id
```

### Remote storage

For now Google Drive only supported. If you find this project useful you can contribute 
to enhance it. Or at least you can post a feature request.

1. To have this work the [Google Service Account](https://cloud.google.com/iam/docs/service-accounts) is necessary.
   The service account id (email) looks like `<the-name-you-choose>@hip-heading-376120.iam.gserviceaccount.com`. 
2. Under the service account you've created add the key pair and download it in `.json` format. 
3. Now create the folder within your Google Drive you wish to push the backups in.
4. Share this folder with the service account (email) from step 1.

### Hooks

They are listed below.

```python
HOOKS = ('before_build', 'after_build', 'before_push', 'after_push', 
         'before_pull', 'after_pull', 'before_restore', 'after_restore')
```

One can either issue `cobra hooks init` that populates hook files to the default directory. 
Or put the hook files with the names e.g. `before_build.py` or `before_build.sh`. 
For shell script `chmod +x before_build.sh` is necessary.

Cobra searches for `.py` file first if found imports it and execute `hook` function as.

```python
hook(hook_name=hook_name, hooks_dir=hooks_dir, backup_dir=backup_dir, 
     filename=backup_filename, docker=docker_client)
```

* `hook_name` is the one from the list above
* `hooks_dir` the directory where hooks reside
* `backup_dir` the local backup directory where backup is stored 
* `filename` the backup file name
* `docker` [DockerClient](https://docker-py.readthedocs.io/en/stable/client.html#docker.client.DockerClient) object

If `.py` file is not found. The default hook is called that continue searching for `.sh` file.
If latter found it's called via `subprocess.check_call()`. With the same params except `docker`.

By default `cobra` copies and packs the content of a volume. 
To backup database with tools like `mongodump` or `pg_dump` one may use `before_build` hook
and `--exclude volume-name` from the processing.
`before_build` hook may look like this in such a case.

```bash
#!/usr/bin/env bash

# Stop any containers that mangle database while dumping to have consistent dump
docker stop my-excellent-app

MONGO_DUMP_DIR=/tmp/mongodump
mkdir -p "${MONGO_DUMP_DIR}"
mongodump --archive="${MONGO_DUMP_DIR}/mongo-dump-by-hook.tar.gz" --db=test --gzip mongodb://mongo-container-name:27017

# Then start them again
docker start my-excellent-app
```

Errors that are propagated from hooks stop farther processing. 
To see more details please inspect e2e test sources.

### Default locations

To find out paths used by cobra one can issue following. 
On my system I have this output.

```bash
$ cobra dirs
/home/q/.local/share/cobra/backup
/home/q/.cache/cobra
/home/q/.local/share/cobra/hooks
```

### Python

Minimum python version is 3.7.

```python
from cobra.api import Api
from cobra.hooks import Hooks
from docker import DockerClient

api = Api(gateway=DockerClient(), hooks=Hooks())
api.backup_build()
```

Method parameters are described in cli help `cobra backup --help` e.g.

### Security notice

This code is subject to command injection vulnerabilty. There are no such a checks. 
The caller should provide all checks on his own.

## Run tests

```bash
git clone https://github.com/yell0w4x/cobra.git
cd cobra
./run-tests --unit
```
 
The above runs unit tests. To execute end-to-end tests run is as follows. 
Note that docker must reside in the system.
To install it on Ubuntu use `wget -qO- https://get.docker.com | sudo bash`. 
On Manjaro (Arch) issue `sudo pacman -S docker`.

```bash
./run-tests --e2e --folder-id goolge-drive-folder-id --key path/to/google-service-account-key.json
```
or
```bash
GOOGLE_DRIVE_FOLDER_ID=goolge-drive-folder-id GOOGLE_SERVICE_ACC_KEY=path/to/key.json ./run-tests --e2e
```

The tests are based on pytest. All the extra arguments are passed to pytest. 
E.g. to have verbose output use `-v` or `-vv`. To show stdout `-s`. 
To run certain tests use `-k test_name` and etc. For details see the pytest docs.

```
./run-tests --help
Run cobra unit and e2e tests.

Usage:
    ./run-tests [OPTIONS] [EXTRA_ARGS]

All the EXTRA_ARGS are passed to pytest

Options:
    --help                Show help message
    --unit                Run unit tests
    --e2e                 Run e2e tests
    --skip-build          Skip building dist files
    --folder-id FOLDER_ID Google drive folder id to use as remote storage for e2e tests. 
                          If not given read from GOOGLE_DRIVE_FOLDER_ID environment variable.
    --key KEY_FN          Path to google service account key file in json format
                          If not given read from GOOGLE_SERVICE_ACC_KEY environment variable.
```
