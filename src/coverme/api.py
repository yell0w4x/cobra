from __future__ import absolute_import

from coverme.exc import CovermeApiError
from coverme.google_drive import folder_list, upload_file

# import aiohttp
import copy
import logging
import asyncio
import inspect
import docker
import json
import os
from os.path import join, exists, realpath, abspath, basename, dirname
from urllib.parse import urljoin
from rich.console import Console
from rich.table import Table, Column
from rich import box
from rich.progress import Progress
from datetime import datetime, timezone
import string, random


DEFAULT_BASE_URL = 'unix:///var/run/docker.sock'
API_VERSION = '1.0'


def purge(obj):
    if isinstance(obj, dict):
        return dict((k, purge(v)) for k, v in obj.items() 
                    if (not isinstance(v, dict) and v is not None) or (isinstance(v, dict) and v))
    else:
        return obj


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def default_backup_dir():
    fallback = join(os.environ.get('HOME'), '.local/share')
    return join(os.environ.get('XDG_DATA_HOME', fallback), 'coverme/backup')


def default_config_dir():
    fallback = join(os.environ.get('HOME'), '.config')
    return join(os.environ.get('XDG_CONFIG_HOME', fallback), 'coverme')


def default_cache_dir():
    fallback = join(os.environ.get('HOME'), '.cache')
    return join(os.environ.get('XDG_CACHE_HOME', fallback), 'coverme')


def print_json(data, pretty=True):
    if pretty:
        print(json.dumps(data, indent=4, sort_keys=True))
    else:
        print(json.dumps(data))


class Api:
    def __init__(self, gateway=None, hooks=None):
        '''
        Creates an API instance.

        @param gateway The DockerClient instance or None. If None is specified the default one 
                        is created.
        '''

        self.__logger = logging.getLogger(__name__)
        self.__docker = gateway if gateway else docker.DockerClient(base_url=DEFAULT_BASE_URL)

# BACKUP        

    def backup_build(self, volume_names=None, dir_names=None, 
                     backup_basename='backup', host_backup_dir=default_backup_dir(), **kwargs):
        upload = kwargs.get('push', False)
        volumes = self.volumes_list(volume_names)
        docker = self.__docker
        
        utcnow = datetime.now(timezone.utc)
        backup_name = f'{backup_basename}@{utcnow:%Y%m%d.%H%M%S}'
        container_backup_dir = f'/{backup_name}'
        volume_opts = { v.name: dict(bind=join(container_backup_dir, v.name), mode='ro') for v in volumes }
        volume_names = [v.name for v in volumes]
        metadata = copy.deepcopy(volume_opts)
        host_backup_dir = abspath(host_backup_dir)
        # output dir mapped to host where the dest compressed file will reside
        volume_opts[host_backup_dir] = dict(bind='/backup', mode='rw')
        extra_vopts = dict()

        if dir_names:
            for item in dir_names:
                full_dir = realpath(abspath(item))
                base_name = basename(full_dir)
                # avoiding conflicts with volume names
                if base_name in volume_names:
                    base_name = f'{base_name}{rand_str()}'

                extra_vopts[full_dir] = dict(bind=join(container_backup_dir, base_name), mode='ro')
            metadata |= copy.deepcopy(extra_vopts)

        volume_opts |= extra_vopts
        backup_archive_fn = f'{backup_name}.tar.gz'
        os.makedirs(host_backup_dir, exist_ok=True)
        metadata_fn = join(host_backup_dir, '...')
        with open(metadata_fn, 'w') as mdf:
            json.dump(metadata, mdf)

        container_backup_archive_fn = join('/backup', backup_archive_fn)
        command=['sh', '-c', f'mv /backup/... {container_backup_dir} && tar -czvf {container_backup_archive_fn} {container_backup_dir}']
        rv = docker.containers.run('busybox', remove=True, volumes=volume_opts, command=command)

        if upload:
            self.__backup_push(host_backup_dir, backup_archive_fn, **kwargs)

        return str(rv, encoding='utf-8')


    def backup_push(self, files, creds, folder_id, backup_dir, **kwargs):
        self.__check_remote_args(creds, folder_id)

        backup_dir = realpath(abspath(backup_dir))
        if not files:
            files = [join(backup_dir, fn) for fn in os.listdir(backup_dir)]
        else:
            tmp = list()
            for fn in files:
                if fn.find('/') != -1:
                    tmp.append(realpath(abspath(fn)))
                else:
                    tmp.append(join(backup_dir, fn))
            files = tmp

        for fn in files:
            self.__backup_push(dirname(fn), basename(fn), creds=creds, folder_id=folder_id, **kwargs)


    def backup_pull(self, **kwargs):
        pass


    def backup_restore(self, **kwargs):
        pass


    def __check_remote_args(self, creds_fn, folder_id):
        if not creds_fn:
            raise ValueError('Service account key file must be specified: --creds option missing')

        if not exists(creds_fn):
            raise FileNotFoundError(f'File not found [{creds_fn}]')

        if not folder_id:
            raise ValueError('Google drive folder id must be specified: --folder-id option missing')


    def __backup_push(self, host_backup_dir, backup_archive_fn, **kwargs):
        rm = kwargs.get('rm', False)
        creds_fn = kwargs.get('creds', None)
        folder_id = kwargs.get('folder_id', None)

        self.__check_remote_args(creds_fn, folder_id)

        backup_archive_full_fn = join(host_backup_dir, backup_archive_fn)
        with Progress() as p:
            task = p.add_task(f'[white]{backup_archive_fn}', total=100)
            for status in upload_file(creds_fn, backup_archive_full_fn, 'application/gzip', backup_archive_fn, folder_id):
                if kwargs.get('print', False):
                    p.update(task, completed=status.progress() * 100)
            p.update(task, completed=100)

        if rm:
            os.remove(backup_archive_full_fn)

    
    def backup_list(self, creds, folder_id, remote, backup_dir, **kwargs):
        # filtr = kwargs.get('filter')
        if remote:
            self.__check_remote_args(creds, folder_id)

        files = folder_list(creds, folder_id) if remote else sorted(os.listdir(backup_dir))

        if kwargs.get('print', False):
            self.__print_backups(files, remote, **kwargs)

        return files


    def __print_backups(self, files, remote, **kwargs):
        json = kwargs.get('json', False)
        plain = kwargs.get('plain', False)

        if remote:
            if json:
                print_json(files)
            elif plain:
                print_id = kwargs.get('id', False)
                print('\n'.join(f.get('id') if print_id else f.get('name') for f in files))
            else:
                table = Table(Column(header='ID', header_style='bold blue', style='white'),
                            Column(header='Name', header_style='bold blue', style='white'), 
                            Column(header='Created at', header_style='bold blue', style='white'), 
                            Column(header='Size', justify='right', header_style='bold blue', style='white'), 
                            Column(header='MD5', header_style='bold blue', style='white'), 
                            box=box.ASCII)

                for f in files:
                    table.add_row(f.get('id', 'n/a'), 
                                f.get('name', 'n/a'), 
                                f.get('createdTime', 'n/a'), 
                                f.get('size', 'n/a'), 
                                f.get('md5Checksum', 'n/a'))

                Console().print(table)
        else:
            if json:
                print_json(files)
            else:
                print('\n'.join(files))


# VOLUMES

    def __print_volumes(self, volumes):
            table = Table(Column(header='Name', header_style='bold blue', style='white'), 
                          Column(header='Created at', header_style='bold blue', style='white'), 
                          Column(header='Driver', header_style='bold blue', style='white'), 
                          Column(header='Mountpoint', header_style='bold blue', style='white'), 
                          box=box.ASCII)

            for v in volumes:
                table.add_row(v.name, 
                              v.attrs.get('CreatedAt', 'n/a'), 
                              v.attrs.get('Driver', 'n/a'), 
                              v.attrs.get('Mountpoint', 'n/a'))

            Console().print(table)


    def volumes_list(self, volume_names=None, **kwargs):
        volumes = self.__docker.volumes.list()
        if volume_names:
            volumes = [v for v in volumes if v.name in volume_names]

        if kwargs.get('print', False):
            self.__print_volumes(volumes)

        return volumes


    def volumes_restore(self, volume_name, **kwargs):
        pass


# class Api:
#     def __init__(self, key, base_url=DEFAULT_BASE_URL, raise_for_error=True):
#         def create_method(func):
#             def method(*args, **kwargs):
#                 return asyncio.run(func(*args, **kwargs))
#             return method

#         self.__async_api = AsyncApi(key, base_url, raise_for_error)
#         methods = inspect.getmembers(self.__async_api, predicate=inspect.ismethod)
#         for m in methods:
#             name, func = m
#             if '__' not in name:
#                 setattr(self, name, create_method(func))
