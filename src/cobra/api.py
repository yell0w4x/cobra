from __future__ import absolute_import

from cobra.exc import CobraApiError, CobraCliError, HookError
import cobra.google_drive
from cobra.aux_stuff import rand_str, print_json
from cobra.hooks import default_hooks_dir

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
    return join(os.getenv('XDG_DATA_HOME', fallback), 'cobra/backup')


def default_config_dir():
    fallback = join(os.getenv('HOME'), '.config')
    return join(os.getenv('XDG_CONFIG_HOME', fallback), 'cobra')


def default_cache_dir():
    fallback = join(os.getenv('HOME'), '.cache')
    return join(os.getenv('XDG_CACHE_HOME', fallback), 'cobra')


class Api:
    def __init__(self, gateway=None, hooks=None, log_level=logging.INFO):
        '''
        Creates an API instance.

        @param gateway The DockerClient instance or None. If None is specified the default one 
                        is created.
        '''
        log_format = '[%(asctime)s]:%(levelname)-5s:: %(message)s -- {%(filename)s:%(lineno)d:(%(funcName)s)}'
        logging.basicConfig(level=log_level, format=log_format)

        self.__logger = logging.getLogger(__name__)
        self.__docker = gateway if gateway else docker.DockerClient(base_url=DEFAULT_BASE_URL)
        self.__hooks = hooks

# BACKUP        

    def backup_build(self, include_volumes=None, exclude_volumes=None, dir_names=None, 
                     backup_basename='backup', host_backup_dir=default_backup_dir(), **kwargs):
        upload = kwargs.get('push', False)
        volumes = self.volumes_list(include_volumes, exclude_volumes)
        docker = self.__docker
        
        utcnow = datetime.now(timezone.utc)
        backup_name = f'{backup_basename}@{utcnow:%Y%m%d.%H%M%S}'
        container_backup_dir = f'/{backup_name}'
        volume_opts = { 
            v.name: dict(bind=join(container_backup_dir, v.name), 
                         mode='ro') for v in volumes 
        }
        include_volumes = [v.name for v in volumes]
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
                if base_name in include_volumes:
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

        self.__call_hook('before_build', backup_dir=host_backup_dir, 
                         filename=backup_archive_fn, docker=self.__docker)

        container_backup_archive_fn = join('/backup', backup_archive_fn)
        command=['sh', '-c', f'mv /backup/{METADATA_FN} {container_backup_dir} && tar -czvf {container_backup_archive_fn} {container_backup_dir}']
        rv = docker.containers.run('busybox', remove=True, volumes=volume_opts, command=command)

        self.__call_hook('after_build', backup_dir=host_backup_dir, 
                         filename=backup_archive_fn, docker=self.__docker)

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


    def backup_pull(self, creds, file_id, latest=False, folder_id=None,
                    restore=False, cache_dir=default_cache_dir(), **kwargs):
        if latest:
            self.__check_remote_args(creds, folder_id)
            files = cobra.google_drive.folder_list(creds, folder_id)
            if not files:
                print('No files found')
                return

            file_id = files[-1]['id']

        self.__check_remote_args1(creds, file_id)
        
        cache_dir = realpath(abspath(cache_dir))
        os.makedirs(cache_dir, exist_ok=True)
        use_cache = not kwargs.get('no_cache', False)
        gen = cobra.google_drive.download_file(creds, file_id, cache_dir, use_cache=use_cache)
        fn = next(gen)
        self.__call_hook('before_pull', cache_dir=cache_dir, filename=file_id, docker=self.__docker)
        with Progress() as p:
            task = p.add_task(f'[white]{fn}', total=100)
            try:
                while True:
                    status = next(gen)
                    if kwargs.get('print', False):
                        p.update(task, completed=status.progress() * 100)
            except StopIteration as e:
                fn = e.value

            p.update(task, completed=100)
    
        self.__call_hook('after_pull', cache_dir=cache_dir, filename=fn, docker=self.__docker)

        if restore:
            assert fn is not None
            self.__backup_restore(fn, cache_dir, **kwargs)

        return fn


    def backup_restore(self, file, cache_dir=default_cache_dir(), **kwargs):
        return self.__backup_restore(file, cache_dir, **kwargs)


    def backup_list(self, creds, folder_id, remote, backup_dir, **kwargs):
        # filtr = kwargs.get('filter')
        if remote:
            self.__check_remote_args(creds, folder_id)

        files = cobra.google_drive.folder_list(creds, folder_id) if remote else sorted(os.listdir(backup_dir))

        if kwargs.get('print', False):
            self.__print_backups(files, remote, **kwargs)

        return files


    def volumes_list(self, include_volumes=None, exclude_volumes=None, json=False, **kwargs):
        include_volumes = set(include_volumes) if include_volumes is not None else set()
        exclude_volumes = set(exclude_volumes) if exclude_volumes is not None else set()
        common = include_volumes.intersection(exclude_volumes)
        if common:
            raise CobraApiError('Include volumes list intersects with exclude volumes list')

        volumes = self.__docker.volumes.list()
        if include_volumes:
            volumes = [v for v in volumes if v.name in include_volumes]

        if exclude_volumes:
            volumes = [v for v in volumes if v.name not in exclude_volumes]

        if kwargs.get('print', False):
            self.__print_volumes(volumes, json)

        return volumes


    def init_hooks(self, hooks_dir=default_hooks_dir(), **kwargs):
        if not self.__hooks:
            return

        self.__hooks.init_hooks(hooks_dir)


    def print_default_dirs(self, **kwargs):
        print(default_backup_dir())
        print(default_cache_dir())
        # print(default_config_dir())
        print(default_hooks_dir())

#fixme: shutils quote names

    def __call_hook(self, hook_name, **kwargs):
        if not self.__hooks:
            return

        return self.__hooks(hook_name, **kwargs)


    def __backup_restore(self, file_name, cache_dir, **kwargs):
        if file_name.find('/') != -1:
            file_name = realpath(abspath(file_name))
        else:
            file_name = join(cache_dir, file_name)

        host_backup_dir = dirname(file_name)
        basename_fn = basename(file_name)

        self.__call_hook('before_restore', cache_dir=host_backup_dir, 
                          filename=basename_fn, docker=self.__docker)

        rv = subprocess.check_output(['tar', 'xvf', file_name, '-C', host_backup_dir])
        backup_name, _ = splitext(splitext(basename_fn)[0])
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

        self.__call_hook('after_restore', cache_dir=host_backup_dir, 
                         filename=basename_fn, docker=self.__docker)

        return rv


    def __check_remote_args(self, creds_fn, folder_id):
        if not creds_fn:
            raise CobraCliError('Service account key file must be specified: --creds option missing')

        if not folder_id:
            raise CobraCliError('Google drive folder id must be specified: --folder-id option missing')

        if not os.path.exists(creds_fn):
            raise FileNotFoundError(f'File not found [{creds_fn}]')


    def __check_remote_args1(self, creds_fn, file_id):
        if not creds_fn:
            raise CobraCliError('Service account key file must be specified: --creds option missing')

        if not file_id:
            raise CobraCliError('Google drive file id must be specified: --file-id option missing')

        if not os.path.exists(creds_fn):
            raise FileNotFoundError(f'File not found [{creds_fn}]')


    def __backup_push(self, host_backup_dir, backup_archive_fn, **kwargs):
        self.__call_hook('before_push', backup_dir=host_backup_dir, 
                         filename=backup_archive_fn, docker=self.__docker)

        rm = kwargs.get('rm', False)
        creds_fn = kwargs.get('creds', None)
        folder_id = kwargs.get('folder_id', None)

        self.__check_remote_args(creds_fn, folder_id)

        backup_archive_full_fn = join(host_backup_dir, backup_archive_fn)
        with Progress() as p:
            task = p.add_task(f'[white]{backup_archive_fn}', total=100)
            for status in cobra.google_drive.upload_file(
                creds_fn, backup_archive_full_fn, 'application/gzip', backup_archive_fn, folder_id):
                if kwargs.get('print', False):
                    p.update(task, completed=status.progress() * 100)
            p.update(task, completed=100)

        self.__call_hook('after_push', backup_dir=host_backup_dir, 
                         filename=backup_archive_fn, docker=self.__docker)

        if rm and exists(backup_archive_full_fn):
            os.remove(backup_archive_full_fn)

    
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
