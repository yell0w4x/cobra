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

    def backup(self, volume_names=None, dir_names=None, basename='backup', **kwargs):
        upload = kwargs.get('upload_goog_drive', False)
        rm = kwargs.get('rm', False)
        creds_fn = kwargs.get('creds', None)
        folder_id = kwargs.get('folder_id', None)

        volumes = self.volumes_list(volume_names)
        docker = self.__docker
        
        utcnow = datetime.now(timezone.utc)
        backup_name = f'{basename}@{utcnow:%Y%m%d.%H%M%S}'
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
        # command=['tar', '-czvf', container_backup_archive_fn, volumes_dir]
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
                    if kwargs('print', False):
                        p.update(task, completed=status.progress() * 100)
                p.update(task, completed=100)

        if rm:
            os.remove(backup_archive_full_fn)
            # vopts = { host_backup_dir: dict(bind='/backup', mode='rw') }
            # docker.containers.run('busybox', remove=True, volumes=vopts,
            #                       command=['rm', container_backup_archive_fn])

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


# VOLUME

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
        # volumes = self.volumes_list(volume_names)
        # docker = self.__docker
        
        # utcnow = datetime.now(timezone.utc)
        # volumes_name = f'volumes-{utcnow:%Y%m%d.%H%M%S}'
        # volumes_dir = f'/{volumes_name}'
        # volume_opts = { v.name: dict(bind=join(volumes_dir, v.name), mode='ro') for v in volumes }
        # volume_opts[join(os.getcwd(), 'backup')] = dict(bind='/backup', mode='rw')
        # rv = docker.containers.run('busybox', remove=True, volumes=volume_opts,
        #                            command=['tar', '-czvf', join('/backup', f'{volumes_name}.tar.gz'), volumes_dir])
        # return str(rv, encoding='utf-8')



#     async def set_profile(self, *, first_name=None, last_name=None, phone=None, gravatar=None, 
#                           nickname=None, wallet_symbol=None, wallet_address=None, country=None, city=None, **kwargs):
#         '''Sets profile info.'''

#         args = dict(lastName=last_name, 
#                     firstName=first_name, 
#                     phone=phone, 
#                     gravatar=gravatar, 
#                     nickname=nickname, 
#                     wallet=dict(symbol=wallet_symbol, address=wallet_address), 
#                     country=country,
#                     city=city)

#         args = purge(purge(args))
#         if not args:
#             raise MindsyncApiError('Invalid arguments, nothing to set')

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/users/client/profile')
#         return await self.__put(url, args, 'Unable to set profile', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))

# # RIGS

# # fixme: actually use params
#     async def rigs_list(self, my=False, sort_by='rating', sort_dir='DESC', offset=1, limit=50, **kwargs):
#         '''Gets rigs list.

#         @param my Filter list to my rigs
#         @param sort_by Designate the field to sort resulted list. Allows 'rating', 'cpu', 'gpuList',
#                        'is_available'
#         @return Returns rigs list in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rigs/my' if my else f'/api/{API_VERSION}/rigs')
#         return await self.__get(url, 'Unable to get rigs list', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rig_info(self, rig_id, **kwargs):
#         '''Gets rig info.

#         @param rig_id Rig's identifier within the platform.
#         @return Returns rig information in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rigs/{rig_id}/state')
#         return await self.__get(url, 'Unable to get rig info', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rig_price(self, rig_id, **kwargs):
#         '''Gets rig price.

#         @param rig_id Rig's identifier within the platform.
#         @return Returns rig price information in JSON.
#         '''

#         return await self.__get(url=urljoin(self.__base_url, f'/api/{API_VERSION}/rigs/{rig_id}/price'), 
#                                 err_message='Unable to get rig price', 
#                                 result_field=None if 'meta' in kwargs else 'result',
#                                 proxy=kwargs.get('proxy', None))


#     async def set_rig(self, rig_id, enable, power_cost, **kwargs):
#         '''Sets rig parameters.

#         @param rig_id Rig's identifier within the platform.
#         @param enable Whether rig is enabled, bool.
#         @param power_cost The cost of the power, float number.
#         @return Returns the result of operation metadata.
#         '''
#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rigs/{rig_id}')
#         args = purge(dict(isEnable=enable, powerCost=power_cost))
#         if not args:
#             raise MindsyncApiError('Invalid arguments, nothing to set')

#         return await self.__put(url, args, 'Unable to set rig parameters', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rig_tariffs(self, rig_id, **kwargs):
#         '''Gets rig tariffs for all or certain rig.

#         @param rig_id Rig's identifier within the platform.
#         @return Returns tariffs information in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rigs/tariffs' if rig_id is None else f'/api/2.0/rigs/{rig_id}/tariffs')
#         return await self.__get(url, 'Unable to get rig tarrifs', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))

# # RENTS

#     async def rents_list(self, my=False, sort_by='rating', sort_dir='DESC', offset=1, limit=50, **kwargs):
#         '''Gets rents list.

#         @param my Filter list to my rents
#         @param sort_by Designate the field to sort resulted list. Allows 'rating', 'cpu', 'gpuList',
#                        'is_available'
#         @param sort_dir Sort direction.
#         @return Returns active rents list in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/owner' if my else f'/api/{API_VERSION}/rents')
#         return await self.__get(url, 'Unable to get rents list', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def start_rent(self, rig_id, tariff_name, **kwargs):
#         '''Starts rent.

#         @param rig_id Rig's identifier within the platform.
#         @param tariff_name The tariff name to start the rent within. 
#             Use RENT_DEMO, RENT_FIXED, RENT_DYNAMIC names to set the value.
#         @return Returns the result of operation metadata.
#         '''
        
#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/start')
#         args = purge(dict(rigHash=rig_id, tariffName=tariff_name))
#         if not args:
#             raise MindsyncApiError('Invalid arguments')

#         return await self.__post(url, args, 'Unable to start rent', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def stop_rent(self, rent_id, **kwargs):
#         '''Stops rent.

#         @param rent_id Rents's identifier in uuid format.
#         @return Returns the result of operation metadata.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/stop')
#         args = purge(dict(hash=rent_id))
#         if not args:
#             raise MindsyncApiError('Invalid arguments')

#         return await self.__post(url, args, 'Unable to stop rent', 
#                                  None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rent_state(self, uuid, **kwargs):
#         '''Returns rent state.

#         @param uuid ??.
#         @return Returns rent state in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/{uuid}')
#         return await self.__get(url, 'Unable to get rent state', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rent_states(self, uuid, **kwargs):
#         '''Returns rent state.

#         @param uuid ??.
#         @return Returns rent states in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/{uuid}/states')
#         return await self.__get(url, 'Unable to get rent states', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def rent_info(self, rent_id, **kwargs):
#         '''Returns rent info.

#         @param rent_id Rents's identifier.
#         @return Returns rent info in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/{rent_id}')
#         return await self.__get(url, 'Unable to get rent info', 
#                                 None if 'meta' in kwargs else 'result', proxy=kwargs.get('proxy', None))


#     async def set_rent(self, rent_id, enable, login, password, **kwargs):
#         '''Sets rent parameters.

#         @param rent_id Rent's identifier within the platform.
#         @param enable ...
#         @param login Protect your rent with login/password
#         @param password Protect your rent with login/password
#         @return Returns the result of operation metadata.
#         '''
#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/rents/{rent_id}')
#         args = purge(dict(isEnable=enable, login=login, password=password))
#         if not args:
#             raise MindsyncApiError('Invalid arguments, nothing to set')

#         return await self.__put(url, args, 'Unable to set rent parameters', 
#                                 None if 'meta' in kwargs else 'result', 
#                                 proxy=kwargs.get('proxy', None))


#     # CODES
#     async def codes_list(self, offset=1, limit=50, **kwargs):
#         '''Gets codes list.

#         @return Returns codes list in JSON.
#         '''

#         return await self.__get(url=urljoin(self.__base_url, f'/api/{API_VERSION}/codes'), 
#                                 err_message='Unable to get codes list', 
#                                 result_field=None if 'meta' in kwargs else 'result',
#                                 proxy=kwargs.get('proxy', None))



#     async def create_code(self, file=None, private=False, **kwargs):
#         '''Create new code from file or deafult template.

#         @param file If str then used as filename to read and use content as code. If no file given default template is used.
#             If bytes is used as content directly.
#         @param private Whether created code is marked as private.
#         @return Returns the result of operation metadata.
#         '''
        
#         data = aiohttp.FormData()
#         data.add_field('file', open(file, 'rb') if isinstance(file, str) else file, content_type='application/octet-stream')
#         data.add_field('isPrivate', str(private).lower())

#         return await self.__post_multipart(url=urljoin(self.__base_url, f'/api/{API_VERSION}/codes'),
#                                         #    data=dict(file=open(file, 'rb'), isPrivate=str(private).lower()),
#                                            data=data,
#                                            err_message='Unable to create code', 
#                                            result_field=None if 'meta' in kwargs else 'result',
#                                            proxy=kwargs.get('proxy', None))


#     async def code_info(self, code_id, **kwargs):
#         '''Gets code info with given id.

#         @param code_id The code id (hash) to use.
#         @return Returns code info in JSON.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/codes/{code_id}')
#         return await self.__get(url, 'Unable to get code info', 
#                                 None if 'meta' in kwargs else 'result', 
#                                 proxy=kwargs.get('proxy', None))


#     async def run_code(self, code_id, rent_id, **kwargs):
#         '''Runs code with given id.

#         @param code_id The code id (hash) to use.
#         @param rent_id The rent id (hash) to use.
#         @return Returns the result of operation metadata.
#         '''

#         url = urljoin(self.__base_url, f'/api/{API_VERSION}/codes/{code_id}/run')
#         args = purge(dict(rentHash=rent_id))
#         if not args:
#             raise MindsyncApiError('Invalid arguments')

#         return await self.__post(url, args, 'Unable to run code', None if 'meta' in kwargs else 'result')


#     async def __get(self, url, err_message, result_field='result', proxy=None):
#         logger = self.__logger
#         logger.debug(f'Get [{url}]')
#         try:
#             async with aiohttp.request(method='GET', url=url, proxy=proxy,
#                                        headers={'api-key': self.__key}, 
#                                        raise_for_status=False) as resp:
#                     result = await resp.json()
#                     logger.debug(f'Result: {result}')
#                     self.__raise_for_error(result)
#                     return result[result_field] if result_field is not None else result
#         except MindsyncApiError as e:
#             raise
#         except BaseException as e:
#             self.__logger.debug(f'{err_message} [{repr(e)}]')
#             raise MindsyncApiError(err_message) from e    



#     async def __put(self, url, args, err_message, result_field='result', proxy=None):
#         logger = self.__logger
#         logger.debug(f'Put [url: {url}; args {args}]')
#         try:
#             async with aiohttp.request(method='PUT', url=url, 
#                                        json=args, 
#                                        proxy=proxy,
#                                        headers={'api-key': self.__key}, 
#                                        raise_for_status=False) as resp:
#                     result = await resp.json()
#                     logger.debug(f'Result: {result}')
#                     self.__raise_for_error(result)
#                     return result[result_field] if result_field is not None else result
#         except MindsyncApiError as e:
#             raise
#         except BaseException as e:
#             self.__logger.debug(f'{err_message} [{repr(e)}]')
#             raise MindsyncApiError(err_message) from e    


#     async def __post(self, url, args, err_message, result_field='result', proxy=None):
#         logger = self.__logger
#         logger.debug(f'Post [url: {url}; args {args}]')
#         try:
#             async with aiohttp.request(method='POST', url=url, json=args, proxy=proxy,
#                                        headers={'api-key': self.__key}, 
#                                        raise_for_status=False) as resp:
#                     result = await resp.json()
#                     logger.debug(f'Result: {result}')
#                     self.__raise_for_error(result)
#                     return result[result_field] if result_field is not None else result
#         except MindsyncApiError as e:
#             raise
#         except BaseException as e:
#             self.__logger.debug(f'{err_message} [{repr(e)}]')
#             raise MindsyncApiError(err_message) from e    


#     async def __post_multipart(self, url, data, err_message, result_field='result', proxy=None):
#         logger = self.__logger
#         logger.debug(f'Post [url: {url}; data: {data}]')
#         try:
#             async with aiohttp.request(method='POST', url=url, data=data, proxy=proxy,
#                                        headers={'api-key': self.__key}, 
#                                        raise_for_status=False) as resp:
#                     result = await resp.json()
#                     logger.debug(f'Result: {result}')
#                     self.__raise_for_error(result)
#                     return result[result_field] if result_field is not None else result
#         except MindsyncApiError as e:
#             raise
#         except BaseException as e:
#             self.__logger.debug(f'{err_message} [{repr(e)}]')
#             raise MindsyncApiError(err_message) from e    


#     def __raise_for_error(self, result):
#         if self.__raise:
#             assert 'error' in result
#             if result['error'] is not None:
#                 raise MindsyncApiError(result['error']['code'], result['error']['name'], result['error']['message'], result)


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
