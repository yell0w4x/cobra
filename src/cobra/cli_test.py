from cobra.cli_handler import CliHandler
from cobra.cli import parse_command_line
from cobra.api import DEFAULT_BASE_URL, default_backup_dir, default_hooks_dir, default_cache_dir

from argparse import Namespace
import os

import pytest
from unittest.mock import create_autospec


BASE_URL = 'https://whatever'


@pytest.fixture
def cli_handler_mock():
    return create_autospec(CliHandler(), spec_set=True)


@pytest.fixture
def base_url():
    return BASE_URL


@pytest.mark.parametrize('cli_args, expected_args', [
                                                # PROFILE
                                                 (['--base-url', BASE_URL, 'backup', 'build', '--include', 'volume1', 'volume2', '--exclude', 'volume3', '--dir', 'dir1', 'dir2'], 
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=BASE_URL, log_level='INFO', handler='backup_build', 
                                                           host_backup_dir=default_backup_dir(), backup_basename='backup', hooks_dir=default_hooks_dir(), 
                                                           hook_off=[], creds=None, folder_id=None, push=False, rm=False, 
                                                           include_volumes=['volume1', 'volume2'], exclude_volumes=['volume3'], dir_names=['dir1', 'dir2'])), 
                                                 (['backup', 'push', 'filename1', 'filename2', '--creds', 'key.json', '--folder-id', 'asdf', '--rm'], 
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='backup_push', 
                                                           backup_dir=default_backup_dir(), hooks_dir=default_hooks_dir(), rm=True,
                                                           creds='key.json', folder_id='asdf', hook_off=[], files=['filename1', 'filename2'])), 
                                                 (['backup', 'list', '--remote', '--creds', 'key.json', '--folder-id', 'asdf'], 
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='backup_list', 
                                                           backup_dir=default_backup_dir(), hooks_dir=default_hooks_dir(), json=False, plain=False,
                                                           creds='key.json', folder_id='asdf', hook_off=[], filter=None, remote=True, id=False)), 
                                                 (['backup', 'pull', '--file-id', 'file-id', '--creds', 'key.json', '--no-cache'],
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='backup_pull', 
                                                           latest=False, folder_id=None, cache_dir=default_cache_dir(), hooks_dir=default_hooks_dir(), no_cache=True,
                                                           creds='key.json', file_id='file-id', hook_off=[], restore=False)), 
                                                 (['backup', 'restore', 'filename'],
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='backup_restore', 
                                                           cache_dir=default_cache_dir(), hooks_dir=default_hooks_dir(), 
                                                           file='filename', hook_off=[])), 
                                                 (['volume', 'list', '--json'],
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='volumes_list', 
                                                           json=True)), 
                                                 (['hooks', 'init', '--hooks-dir', '/hooks/dir'],
                                                 Namespace(help=False, tls=False, cert_dir=None, base_url=DEFAULT_BASE_URL, log_level='INFO', handler='init_hooks', 
                                                           hooks_dir='/hooks/dir')), 
                                                ])
def test_parse_command_line_must_setup_right_command_handler(cli_handler_mock, cli_args, expected_args):
    args, _ = parse_command_line(cli_handler_mock, args=cli_args)
    print(args)
    assert args.handler
    args.handler(**vars(args))

    method_name = expected_args.handler
    expected_args.handler = getattr(cli_handler_mock, method_name)
    called_method = getattr(cli_handler_mock, method_name)
    called_method.assert_called_with(**vars(expected_args))
