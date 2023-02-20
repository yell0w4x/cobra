from cobra.api import Api, purge, DEFAULT_BASE_URL, default_backup_dir, \
    default_cache_dir
from cobra.exc import CobraCliError
from cobra.cli_handler import CliHandler
from cobra.hooks import Hooks, default_hooks_dir


import os
import argparse
import logging
import json
import sys
from docker import DockerClient
import docker
from os.path import join


def parse_command_line(cli_handler, args=sys.argv[1:]):
    parser = argparse.ArgumentParser(add_help=False, prog='cobra', description='Comprehensive Backing up and Restoration Archiver')
    parser.add_argument('-h', '--help', help='Shows help message', action='store_true')
    parser.add_argument('--base-url', default=os.environ.get('DOCKER_HOST', DEFAULT_BASE_URL),
                        help='Docker daemon socket base url. If not specified an attempt to use DOCKER_HOST variable will be performed '
                            '(default: %(default)s)')
    parser.add_argument('--tls', action='store_true', default=os.environ.get('DOCKER_TLS_VERIFY', False),
                        help='Make docker cli use tls. If not specified an attempt to use DOCKER_TLS_VERIFY variable will be performed '
                            '(default: %(default)s)')
    parser.add_argument('--cert-dir', type=str, default=os.environ.get('DOCKER_CERT_PATH', None), help='Path to ca and client certificates')
    parser.add_argument('--log-level', default='INFO', help='Logging level from standard python logging module (default: %(default)s)')
    sp = parser.add_subparsers(title='subcommands', help='Use these subcommands to backup restore your data')
    # backup
    backup_parser = sp.add_parser('backup', help='Backup realated stuff')
    backup_parser.add_argument('--hooks-dir', default=default_hooks_dir(), help='Specifies hooks directory to search for hooks (default: %(default)s)')
    backup_parser.add_argument('--hook-off', default=list(), nargs='*', metavar='HOOK_NAME', help='Disable all or certain hooks. To disable all pass \'*\' (default: %(default)s)')
    backup_sp = backup_parser.add_subparsers(title='subcommands', help='Backup related subcommands')
    # backup/build
    backup_build_parser = backup_sp.add_parser('build', help='Build backup. By default backups all the volumes avaialble.')
    backup_build_parser.set_defaults(handler=cli_handler.backup_build)
    backup_build_parser.add_argument('-i', '--include', nargs='*', dest='include_volumes', metavar='VOLUME', help='Volume name or id to include into backup')
    backup_build_parser.add_argument('-x', '--exclude', nargs='*', dest='exclude_volumes', metavar='VOLUME', help='Volume name or id to exclude from backup')
    backup_build_parser.add_argument('-d', '--dir', nargs='*', dest='dir_names', metavar='DIR', help='Directory to backup')
    backup_build_parser.add_argument('--rm', action='store_true', default=False, help='Remove the backup from the local machine after backup uploaded to remote storage (default: %(default)s). Only if push specified.')
    backup_build_parser.add_argument('--push', action='store_true', default=False, help='Whether to upload created backup file to google drive folder shared to service account. '
        'Needs to designate service account credentials (default: %(default)s)')
    backup_build_parser.add_argument('--backup-dir', default=default_backup_dir(), dest='host_backup_dir', metavar='BACKUP_DIR', help='The directory to store backups (default: %(default)s)')
    backup_build_parser.add_argument('--creds', metavar='FILENAME', help='Google service account credentials file in json format')
    backup_build_parser.add_argument('--folder-id', help='Google drive folder id the backup files will reside under')
    backup_build_parser.add_argument('--basename', default='backup', dest='backup_basename', metavar='BASENAME', help='Backup files prefix (default: %(default)s)')
    # backup/push
    backup_push_parser = backup_sp.add_parser('push', help='Push backup file to a storage')
    backup_push_parser.add_argument('files', nargs='*', help='A file names space seprated list to push. To designate exact file on file system include path like \'./file/to/push\' for current directory. If no path given the files are looked for in backup directory either default or specified by --backup-dir option. If no files given then all files from default or desiginated by --backup-dir option are taken')
    backup_push_parser.add_argument('--backup-dir', default=default_backup_dir(), help='The directory to store backups (default: %(default)s)')
    backup_push_parser.add_argument('--creds', help='Google service account credentials file in json format')
    backup_push_parser.add_argument('--folder-id', help='Google drive folder id the backup files will reside under')
    backup_push_parser.add_argument('--rm', action='store_true', default=False, help='Remove the backup from the local machine after backup uploaded to remote storage (default: %(default)s). Only if push specified.')
    backup_push_parser.set_defaults(handler=cli_handler.backup_push)
    # backup/list
    backup_list_parser = backup_sp.add_parser('list', help='List backup files by default on locally.')
    backup_list_parser.add_argument('--remote', action='store_true', default=False, help='List remote files instead of local (default: %(default)s)')
    backup_list_parser.add_argument('--folder-id', help='Google drive folder id to list')
    backup_list_parser.add_argument('--creds', help='Google service account credentials file in json format')
    backup_list_parser.add_argument('--json', action='store_true', default=False, help='Print in json format (default: %(default)s)')
    backup_list_parser.add_argument('--plain', action='store_true', default=False, help='Print a list of file names and ids (default: %(default)s)')
    backup_list_parser.add_argument('--id', action='store_true', default=False, help='Print a file id instead of name in case of --plain (default: %(default)s)')
    backup_list_parser.add_argument('--backup-dir', default=default_backup_dir(), help='The directory to store backups (default: %(default)s)')
    backup_list_parser.add_argument('--filter', help='File name should include pattern, to exclude prepend the pattern with \'not\' (default: %(default)s)')
    backup_list_parser.set_defaults(handler=cli_handler.backup_list)
    # backup/pull
    backup_pull_parser = backup_sp.add_parser('pull', help='Pulls given backup from remote storage')
    backup_pull_parser.add_argument('--file-id', default=None, help='Google drive file id to pull')
    backup_pull_parser.add_argument('--latest', action='store_true', default=False, help='Get latest file to pull. Note that the file name is not checked (default: %(default)s)')
    backup_pull_parser.add_argument('--folder-id', default=None, help='Google drive folder id to pull from')
    backup_pull_parser.add_argument('--creds', required=True, help='Google service account credentials file in json format')
    backup_pull_parser.add_argument('--restore', action='store_true', default=False, help='Restore backup after download (default: %(default)s)')
    backup_pull_parser.add_argument('--cache-dir', default=default_cache_dir(), help='The directory to store downloaded backup files (default: %(default)s)')
    backup_pull_parser.add_argument('--no-cache', action='store_true', default=False, help='Ignore files that reside in cache directory and download from remote storage (default: %(default)s)')
    backup_pull_parser.set_defaults(handler=cli_handler.backup_pull)
    # backup/restore
    backup_restore_parser = backup_sp.add_parser('restore', help='Restores given backup.')
    backup_restore_parser.add_argument('file', help='A backup archive to restore from. To designate exact file on file system include path like \'./file/to/restore\' for current directory. If no path given the file is looked for in a directory either default or specified by --cache-dir option')
    backup_restore_parser.add_argument('--cache-dir', default=default_cache_dir(), help='The directory where temporary backup files are stored (default: %(default)s)')
    backup_restore_parser.set_defaults(handler=cli_handler.backup_restore)
    # backup/rm
    # backup_rm_parser = backup_sp.add_parser('rm', help='Remove backup.')
    # backup_rm_parser.add_argument('--file-id', required=True, help='Google drive folder id to take backup from')
    # backup_rm_parser.add_argument('--backup-dir', default=default_backup_dir(), dest='host_backup_dir', help='The directory to store backups (default: %(default)s)')
    # backup_rm_parser.add_argument('--creds', required=True, help='Google service account credentials file in json format')
    # backup_rm_parser.add_argument('--cache-dir', default=default_cache_dir(), help='The directory to store downloaded backup files (default: %(default)s)')
    # backup_rm_parser.set_defaults(handler=cli_handler.backup_restore)
    # volume
    volume_parser = sp.add_parser('volume', help='Docker volumes related actions. By default lists all the volumes in table format.')
    volume_parser.set_defaults(handler=cli_handler.volumes_list)
    volume_parser.add_argument('--json', action='store_true', default=False, help='Print in json format')
    # volume/list
    volume_sp = volume_parser.add_subparsers(title='volume subcommands', help='Volume related subcommands')
    volume_list_parser = volume_sp.add_parser('list', help='List volumes.')
    volume_list_parser.add_argument('--json', action='store_true', default=False, help='Print in json format')
    volume_list_parser.set_defaults(handler=cli_handler.volumes_list)
    # hooks
    hooks_parser = sp.add_parser('hooks', help='Hooks related stuff')
    hooks_sp = hooks_parser.add_subparsers(title='subcommands', help='Hooks related subcommands')
    hooks_init_parser = hooks_sp.add_parser('init', help='Initialize hooks in hooks directory. NOTE that all the hook files will be overwritten!')
    hooks_init_parser.add_argument('--hooks-dir', default=default_hooks_dir(), help='Specifies hooks directory to search for hooks (default: %(default)s)')
    hooks_init_parser.set_defaults(handler=cli_handler.init_hooks)
    # dirs
    dirs_parser = sp.add_parser('dirs', help='Print default directories used by cobra')
    dirs_parser.set_defaults(handler=cli_handler.print_default_dirs)
    dirs_sp = dirs_parser.add_subparsers(title='dirs subcommands')
    dirs_list_parser = dirs_sp.add_parser('list', help='List default directories.')
    dirs_list_parser.set_defaults(handler=cli_handler.print_default_dirs)

    args = parser.parse_args(args)
    effective_args = purge(vars(args))
    del effective_args['help']

    if not effective_args:
        return None, parser

    return args, parser


def main():
    try:
        _main()
    except SystemExit:
        raise
    except CobraCliError as e:
        print(e.args[0], file=sys.stderr)
        e.args[1].print_help()


def _main():
    if sys.version_info < (3, 7):
        RuntimeError(f'Incompatible python version [{sys.version_info}], must be at least 3.7')

    cli_handler = CliHandler()
    args, parser = parse_command_line(cli_handler)
    logging.basicConfig(level=args.log_level)
    logging.debug(f'CLI Args: [{args}]')

    if args is not None and args.help:
        from cobra.banner import BANNER
        print(BANNER)
        parser.print_help()
        return

    if args is None or not hasattr(args, 'handler'):
        raise CobraCliError('No command specified', parser)

    args = vars(args)
    if args.get('tls'):
        cert_dir = args.get('cert_dir')
        client_cert = join(cert_dir, 'cert.pem'), join(cert_dir, 'key.pem')
        ca_cert = join(cert_dir, 'ca.pem')
        tls_config = docker.tls.TLSConfig(ca_cert=ca_cert, client_cert=client_cert, verify=True)
        api = Api(gateway=DockerClient(base_url=args.get('base_url'), tls=tls_config), 
                                       hooks=Hooks(hooks_dir=args.get('hooks_dir', default_hooks_dir()), 
                                                   disable_hooks=args.get('hook_off', list())),
                                       log_level=args['log_level'])
    else:
        api = Api(gateway=DockerClient(base_url=args.get('base_url')), 
                                       hooks=Hooks(hooks_dir=args.get('hooks_dir', default_hooks_dir()), 
                                                   disable_hooks=args.get('hook_off', list())),
                                       log_level=args['log_level'])

    cli_handler.bind(api)
    args['handler'](**args, print=True)
