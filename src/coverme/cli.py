from coverme.api import Api, purge, DEFAULT_BASE_URL
from coverme.exc import CovermeCliError
from coverme.cli_handler import CliHandler

import os
import argparse
import logging
import json
import sys
from docker import DockerClient


def parse_command_line(cli_handler, args=sys.argv[1:]):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', '--help', help='Shows help message', action='store_true')
    parser.add_argument('--base-url', default=os.environ.get('DOCKER_BASE_URL', DEFAULT_BASE_URL),
                        help='Docker daemon socket base url. If not specified an attempt to use DOCKER_BASE_URL variable will be performed '
                            f'(default: {DEFAULT_BASE_URL})')
    parser.add_argument('--log-level', default='INFO', help='Logging level from standard python logging module (default: %(default)s)')
    sp = parser.add_subparsers(title='subcommands', help='Use these subcommands to backup restore your data')
    # backup
    backup_parser = sp.add_parser('backup', help='By default backups all the volumes avaialble.')
    backup_parser.set_defaults(handler=cli_handler.backup)
    backup_parser.add_argument('-v', '--volume', nargs='*', default=None, dest='volume_names', help='Volume name or id to backup')
    backup_parser.add_argument('-d', '--dir', nargs='*', default=None, dest='dir_names', help='Directory to backup')
    backup_parser.add_argument('--rm', action='store_true', default=False, help='Remove the backup from the local machine after backup uploaded to remote storage (default: %(default)s)')
    backup_parser.add_argument('--upload-goog-drive', action='store_true', default=False, help='Whether to upload created backup file to google drive folder shared to service account. '
        'Needs to designate service account credentials (default: %(default)s)')
    backup_parser.add_argument('--creds', help='Google service account credentials file in json format')
    backup_parser.add_argument('--folder-id', help='Google drive folder id the backup files will reside under')
    backup_parser.add_argument('--basename', default='backup', dest='backup_basename', help='Backup files prefix (default: %(default)s)')
    backup_sp = backup_parser.add_subparsers(title='backup subcommands', help='Backup related subcommands')
    # backup/list
    backup_list_parser = backup_sp.add_parser('list', help='List all the remote backups.')
    backup_list_parser.add_argument('--folder-id', required=True, help='Google drive folder id to list')
    backup_list_parser.add_argument('--creds', required=True, help='Google service account credentials file in json format')
    backup_list_parser.add_argument('--json', action='store_true', default=False, help='Print in json format')
    backup_list_parser.add_argument('--plain', action='store_true', default=False, help='Print a list of file names and ids')
    backup_list_parser.set_defaults(handler=cli_handler.backup_list)
    # backup/restore
    backup_list_parser = backup_sp.add_parser('restore', help='Restores given backup.')
    backup_list_parser.add_argument('--file-id', required=True, help='Google drive folder id to take backup from')
    backup_list_parser.add_argument('--folder-id', required=True, help='Google drive folder id to take backup from')
    backup_list_parser.add_argument('--creds', required=True, help='Google service account credentials file in json format')
    backup_list_parser.add_argument('--download-only', action='store_true', default=False, help='Don\'t restore, just download')
    backup_list_parser.set_defaults(handler=cli_handler.backup_list)

    # volume
    volume_parser = sp.add_parser('volume', help='Docker volumes related actions. By default lists all the volumes in table format.')
    volume_parser.set_defaults(handler=cli_handler.volumes_list)
    volume_sp = volume_parser.add_subparsers(title='volume subcommands', help='Volume related subcommands')

    args = parser.parse_args(args)
    effective_args = purge(vars(args))

    # print(args)
    # print(effective_args)

    del effective_args['help']
    # print(effective_args)

    if not effective_args:
        return None, parser

    return args, parser


def main():
    try:
        _main()
    except SystemExit:
        raise
    except CovermeCliError as e:
        print(e.args[0], file=sys.stderr)
        e.args[1].print_help()


def _main():
    cli_handler = CliHandler()
    args, parser = parse_command_line(cli_handler)
    logging.basicConfig(level=args.log_level)
    logging.debug(f'CLI Args: [{args}]')

    if args is not None and args.help:
        parser.print_help()
        return

    if args is None or not hasattr(args, 'handler'):
        raise CovermeCliError('No command specified', parser)

    api = Api(gateway=DockerClient(base_url=args.base_url))
    cli_handler.bind(api)
    dict_args = vars(args)
    # if not args.meta:
    #     dict_args.pop('meta', None)

    rv = args.handler(**dict_args, print=True)
    # print(repr(rv))
    # _print(rv, args)


def _print(rv, args):
    if args.prettify:
        print(json.dumps(rv, indent=4, sort_keys=True))
    else:
        print(json.dumps(rv))
