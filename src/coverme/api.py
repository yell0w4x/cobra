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
from os.path import join, exists, realpath, abspath, basename
from urllib.parse import urljoin
from rich.console import Console
from rich.table import Table, Column
from rich import box
from rich.progress import Progress
from datetime import datetime, timezone
import string, random


def purge(obj):
    if isinstance(obj, dict):
        return dict((k, purge(v)) for k, v in obj.items() 
                    if (not isinstance(v, dict) and v is not None) or (isinstance(v, dict) and v))
    else:
        return obj


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


DEFAULT_BASE_URL = 'unix:///var/run/docker.sock'
API_VERSION = '1.0'


class Api:
    def __init__(self, gateway=None):
        '''
        Creates an API instance.

        @param gateway The DockerClient instance or None. If None is specified the default one 
                        is created.
        '''

        self.__logger = logging.getLogger(__name__)
        self.__docker = gateway if gateway else docker.DockerClient(base_url=DEFAULT_BASE_URL)

# BACKUP        

    def backup(self, volume_names=None, dir_names=None, backup_basename='backup', **kwargs):
        upload = kwargs.get('upload_goog_drive', False)
        rm = kwargs.get('rm', False)
        creds_fn = kwargs.get('creds', None)
        folder_id = kwargs.get('folder_id', None)

        volumes = self.volumes_list(volume_names)
        docker = self.__docker
        
        utcnow = datetime.now(timezone.utc)
        backup_name = f'{backup_basename}@{utcnow:%Y%m%d.%H%M%S}'
        backup_dir = f'/{backup_name}'
        volume_opts = { v.name: dict(bind=join(backup_dir, v.name), mode='ro') for v in volumes }
        volume_names = [v.name for v in volumes]
        metadata = copy.deepcopy(volume_opts)
        host_backup_dir = join(os.getcwd(), 'backup')
        # output dir mapped to host where the dest compressed file will reside
        volume_opts[host_backup_dir] = dict(bind='/backup', mode='rw')
        extra_vopts = dict()

        if dir_names:
            for item in dir_names:
                full_dir = realpath(abspath(item))
                basedir = basename(full_dir)
                # avoiding conflicts with volume names
                if basedir in volume_names:
                    basedir = f'{basedir}{rand_str()}'

                extra_vopts[full_dir] = dict(bind=join(backup_dir, basedir), mode='ro')
                metadata |= copy.deepcopy(extra_vopts)

        volume_opts |= extra_vopts
        backup_archive_fn = f'{backup_name}.tar.gz'
        os.makedirs(host_backup_dir, exist_ok=True)
        metadata_fn = join(host_backup_dir, '...')
        with open(metadata_fn, 'w') as mdf:
            json.dump(metadata, mdf)

        container_backup_archive_fn = join('/backup', backup_archive_fn)
        command=['sh', '-c', f'mv /backup/... {backup_dir} && tar -czvf {container_backup_archive_fn} {backup_dir}']
        rv = docker.containers.run('busybox', remove=True, volumes=volume_opts, command=command)

        if upload:
            if not creds_fn:
                raise ValueError('Service account key file must be specified')

            if not folder_id:
                raise ValueError('Google drive folder id must be specified')

            if not exists(creds_fn):
                raise FileNotFoundError(f'File not found [{creds_fn}]')

            backup_archive_full_fn = join(host_backup_dir, backup_archive_fn)
            with Progress() as p:
                task = p.add_task(f'[white]{backup_archive_fn}', total=100)
                for status in upload_file(creds_fn, backup_archive_full_fn, 'application/gzip', backup_archive_fn, folder_id):
                    if kwargs.get('print', False):
                        p.update(task, completed=status.progress() * 100)
                p.update(task, completed=100)

        if rm:
            os.remove(backup_archive_full_fn)

        return str(rv, encoding='utf-8')

    
    def backup_list(self, creds, folder_id, **kwargs):
        files = folder_list(creds, folder_id)
        if kwargs.get('print', False):
            self.__print_backups(files)
        return files


    def __print_backups(self, files):
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
