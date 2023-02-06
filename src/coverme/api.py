from __future__ import absolute_import

from coverme.exc import CovermeApiError, CovermeCliError
import coverme.google_drive
from coverme.aux_stuff import rand_str

# import aiohttp
import copy
import logging
import asyncio
import inspect
import docker
import json
import os
import subprocess
from os.path import join, exists, realpath, abspath, basename, dirname, splitext
from urllib.parse import urljoin
from rich.console import Console
from rich.table import Table, Column
from rich import box
from rich.progress import Progress
from datetime import datetime, timezone


DEFAULT_BASE_URL = 'unix:///var/run/docker.sock'
API_VERSION = '1.0'
METADATA_FN = '...'


def purge(obj):
    if isinstance(obj, dict):
        return dict((k, purge(v)) for k, v in obj.items() 
                    if (not isinstance(v, dict) and v is not None) or (isinstance(v, dict) and v))
    else:
        return obj


def default_backup_dir():
    fallback = join(os.getenv('HOME'), '.local/share')
    return join(os.getenv('XDG_DATA_HOME', fallback), 'coverme/backup')


def default_config_dir():
    fallback = join(os.getenv('HOME'), '.config')
    return join(os.getenv('XDG_CONFIG_HOME', fallback), 'coverme')


def default_cache_dir():
    fallback = join(os.getenv('HOME'), '.cache')
    return join(os.getenv('XDG_CACHE_HOME', fallback), 'coverme')


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
        volume_opts = { 
            v.name: dict(bind=join(container_backup_dir, v.name), 
                         mode='ro') for v in volumes 
        }
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
        for v in volumes:
            metadata[v.name]['driver'] = v.attrs['Driver']
            metadata[v.name]['options'] = v.attrs['Options']
            metadata[v.name]['labels'] = v.attrs['Labels']

        metadata_fn = join(host_backup_dir, METADATA_FN)
        with open(metadata_fn, 'w') as mdf:
            json.dump(metadata, mdf)

        container_backup_archive_fn = join('/backup', backup_archive_fn)
        command=['sh', '-c', f'mv /backup/{METADATA_FN} {container_backup_dir} && tar -czvf {container_backup_archive_fn} {container_backup_dir}']
        rv = docker.containers.run('busybox', remove=True, volumes=volume_opts, command=command)

        if upload:
            self.__backup_push(host_backup_dir, backup_archive_fn, **kwargs)

        return str(rv, encoding='utf-8')


    def backup_push(self, files, creds, folder_id, backup_dir=default_backup_dir(), **kwargs):
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


    def backup_pull(self, creds, file_id, restore=False, cache_dir=default_cache_dir(), **kwargs):
        self.__check_remote_args1(creds, file_id)

        os.makedirs(cache_dir, exist_ok=True)
        fn = None
        with Progress() as p:
            task = p.add_task(f'[white]{file_id}', total=100)
            try:
                gen = coverme.google_drive.download_file(creds, file_id, cache_dir)
                while True:
                    status = next(gen)
                    if kwargs.get('print', False):
                        p.update(task, completed=status.progress() * 100)
            except StopIteration as e:
                fn = e.value

            p.update(task, completed=100)
        
        if restore:
            assert fn is not None
            self.__backup_restore(fn, cache_dir, **kwargs)

        return fn


    def backup_restore(self, file, cache_dir=default_cache_dir(), **kwargs):
        return self.__backup_restore(file, cache_dir, **kwargs)

#fixme: shutils quote names

    def __backup_restore(self, file_name, cache_dir, **kwargs):
        if file_name.find('/') != -1:
            file_name = realpath(abspath(file_name))
        else:
            file_name = join(cache_dir, file_name)

        host_backup_dir = dirname(file_name)
        rv = subprocess.check_output(['tar', 'xvf', file_name, '-C', host_backup_dir])
        backup_name, _ = splitext(splitext(basename(file_name))[0])
        container_volumes_mount_dir = f'/{backup_name}'
        full_backup_archive_dir = join(host_backup_dir, backup_name)
        metadata_fn = join(full_backup_archive_dir, METADATA_FN)
        with open(metadata_fn) as f:
            metadata = json.load(f)
        
        for vol_name, meta in metadata.items():
            if vol_name.find('/') != -1:
                os.makedirs(vol_name, exist_ok=True)
                meta['mode'] = 'rw'
            else:
                meta['mode'] = 'rw'
                self.__docker.volumes.create(vol_name, driver=meta['driver'], 
                                             labels=meta['labels'], driver_opts=meta['options'])
                del meta['driver'], meta['labels'], meta['options']

        metadata[host_backup_dir] = dict(bind='/backup', mode='ro')
        container_backup_archive_dir = join('/backup', backup_name, '*')
        command=['sh', '-c', f'cp -rf {container_backup_archive_dir} {container_volumes_mount_dir}']
        self.__docker.containers.run('busybox', remove=True, volumes=metadata, command=command)
        return rv


    def __check_remote_args(self, creds_fn, folder_id):
        if not creds_fn:
            raise CovermeCliError('Service account key file must be specified: --creds option missing')

        if not folder_id:
            raise CovermeCliError('Google drive folder id must be specified: --folder-id option missing')

        if not os.path.exists(creds_fn):
            raise FileNotFoundError(f'File not found [{creds_fn}]')


    def __check_remote_args1(self, creds_fn, file_id):
        if not creds_fn:
            raise CovermeCliError('Service account key file must be specified: --creds option missing')

        if not file_id:
            raise CovermeCliError('Google drive file id must be specified: --file-id option missing')

        if not os.path.exists(creds_fn):
            raise FileNotFoundError(f'File not found [{creds_fn}]')


    def __backup_push(self, host_backup_dir, backup_archive_fn, **kwargs):
        rm = kwargs.get('rm', False)
        creds_fn = kwargs.get('creds', None)
        folder_id = kwargs.get('folder_id', None)

        self.__check_remote_args(creds_fn, folder_id)

        backup_archive_full_fn = join(host_backup_dir, backup_archive_fn)
        with Progress() as p:
            task = p.add_task(f'[white]{backup_archive_fn}', total=100)
            for status in coverme.google_drive.upload_file(
                creds_fn, backup_archive_full_fn, 'application/gzip', backup_archive_fn, folder_id):
                if kwargs.get('print', False):
                    p.update(task, completed=status.progress() * 100)
            p.update(task, completed=100)

        if rm:
            os.remove(backup_archive_full_fn)

    
    def backup_list(self, creds, folder_id, remote, backup_dir, **kwargs):
        # filtr = kwargs.get('filter')
        if remote:
            self.__check_remote_args(creds, folder_id)

        files = coverme.google_drive.folder_list(creds, folder_id) if remote else sorted(os.listdir(backup_dir))

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

    def __print_volumes(self, volumes, is_json=False):
        if is_json:
            for v in volumes:
                print_json(v.attrs)
        else:
            table = Table(Column(header='Name', header_style='bold blue', style='white'), 
                          Column(header='Created at', header_style='bold blue', style='white'), 
                          Column(header='Driver', header_style='bold blue', style='white'), 
                          Column(header='Mountpoint', header_style='bold blue', style='white'), 
                          Column(header='Options', header_style='bold blue', style='white'), 
                          Column(header='Labels', header_style='bold blue', style='white'), 
                          box=box.ASCII)

            for v in volumes:
                table.add_row(v.name, 
                              v.attrs.get('CreatedAt', 'n/a'), 
                              v.attrs.get('Driver', 'n/a'), 
                              v.attrs.get('Mountpoint', 'n/a'),
                              json.dumps(v.attrs.get('Options', 'n/a')),
                              json.dumps(v.attrs.get('Labels', 'n/a'))
                )

            Console().print(table)


    def volumes_list(self, volume_names=None, json=False, **kwargs):
        volumes = self.__docker.volumes.list()
        if volume_names:
            volumes = [v for v in volumes if v.name in volume_names]

        if kwargs.get('print', False):
            self.__print_volumes(volumes, json)

        return volumes



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
