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
    backup_list_parser.set_defaults(handler=cli_handler.backup_list)

    # volume
    volume_parser = sp.add_parser('volume', help='Docker volumes related actions. By default lists all the volumes in table format.')
    volume_parser.set_defaults(handler=cli_handler.volumes_list)
    volume_sp = volume_parser.add_subparsers(title='volume subcommands', help='Volume related subcommands')

    # volume/list
    volume_list_parser = volume_sp.add_parser('list', help='List all the volumes by default.')
    volume_parser.add_argument('--json', default=False, action='store_true', help='List in json format (default: %(default)s)')
    volume_list_parser.set_defaults(handler=cli_handler.volumes_list)
   
    # volume/restore
    # profile_set_parser = profile_sp.add_parser('set', help='Sets profile properties.')
    # profile_set_parser.set_defaults(handler=cli_handler.set_profile)
    # profile_set_parser.add_argument('--first-name', help='Set profile\'s first name')
    # profile_set_parser.add_argument('--last-name', help='Set profile\'s last name')
    # profile_set_parser.add_argument('--phone', help='Set profile\'s phone number')
    # profile_set_parser.add_argument('--gravatar', help='Set profile\'s gravatar')
    # profile_set_parser.add_argument('--nickname', help='Set profile\'s nickname')
    # profile_set_parser.add_argument('--wallet_symbol', help='Set profile\'s wallet_symbol')
    # profile_set_parser.add_argument('--wallet_address', help='Set profile\'s wallet_address')
    # profile_set_parser.add_argument('--country', help='Set profile\'s country')
    # profile_set_parser.add_argument('--city', help='Set profile\'s city')
    # # rig
    # rig_parser = sp.add_parser('rig', help='Mindsync platform rigs related actions. By default return all the rigs list.')
    # rig_sp = rig_parser.add_subparsers(title='rigs subcommands', help='Rigs related subcommands')
    # # rig/list
    # rig_list_parser = rig_sp.add_parser('list', help='Returns all rigs list across the platform by default')
    # rig_list_parser.set_defaults(handler=cli_handler.rigs_list)
    # rig_list_parser.add_argument('--my', action='store_true', help='Filter list to only my rigs')
    # # rig/info
    # rig_info_parser = rig_sp.add_parser('info', help='Returns the rig info.')
    # rig_info_parser.set_defaults(handler=cli_handler.rig_info)
    # rig_info_parser.add_argument('--id', default=None, dest='rig_id', required=True, help='Rig id to get info of')
    # # rig/price
    # rig_info_parser = rig_sp.add_parser('price', help='Returns the rig price.')
    # rig_info_parser.set_defaults(handler=cli_handler.rig_price)
    # rig_info_parser.add_argument('--id', default=None, dest='rig_id', required=True, help='Rig id to get price of')
    # # rig/set
    # rig_info_set_parser = rig_sp.add_parser('set', help='Sets account properties.')
    # rig_info_set_parser.set_defaults(handler=cli_handler.set_rig, enable=None)
    # rig_info_set_parser.add_argument('--id', default=None, dest='rig_id', required=True, help='Rig id to get info of')
    # rig_info_set_parser.add_argument('--enable', dest='enable', action='store_true', help='Enables rig')
    # rig_info_set_parser.add_argument('--disable', dest='enable', action='store_false', help='Disables rig')
    # rig_info_set_parser.add_argument('--power-cost', type=float, help='Sets the power cost')
    # # rig/tariffs
    # rig_info_set_parser = rig_sp.add_parser('tariffs', help='Get tariffs.')
    # rig_info_set_parser.set_defaults(handler=cli_handler.rig_tariffs)
    # rig_info_set_parser.add_argument('--id', default=None, dest='rig_id', help='Rig id to get tariffs of')
    # # rent
    # rent_parser = sp.add_parser('rent', help='Mindsync platform rents related actions. By default returns...')
    # rent_sp = rent_parser.add_subparsers(title='rent subcommands', help='Rent related subcommands')
    # # rent/list
    # rent_list_parser = rent_sp.add_parser('list', help='Returns all active rents list across the platform')
    # rent_list_parser.set_defaults(handler=cli_handler.rents_list)
    # rent_list_parser.add_argument('--my', action='store_true', help='Filter list to only my rents')
    # # rent/start
    # rent_start_parser = rent_sp.add_parser('start', help='Starts rent')
    # rent_start_parser.set_defaults(handler=cli_handler.start_rent)
    # rent_start_parser.add_argument('--rig-id', required=True, help='Rig id to rent')
    # rent_start_parser.add_argument('--tariff', required=True, choices=['demo', 'dynamic', 'fixed'], help='Tarrif to use')
    # # rent/stop
    # rent_stop_parser = rent_sp.add_parser('stop', help='Stops rent certain rent')
    # rent_stop_parser.set_defaults(handler=cli_handler.stop_rent)
    # rent_stop_parser.add_argument('--id', required=True, dest='rent_id', help='Rent id to stop in uuid format')
    # # rent/state
    # rent_state_parser = rent_sp.add_parser('state', help='Returns rent state')
    # rent_state_parser.set_defaults(handler=cli_handler.rent_state)
    # rent_state_parser.add_argument('--uuid', required=True, dest='uuid', help='Rent id to retrieve state for in uuid format')
    # # rent/states
    # rent_state_parser = rent_sp.add_parser('states', help='Returns rent states')
    # rent_state_parser.set_defaults(handler=cli_handler.rent_states)
    # rent_state_parser.add_argument('--uuid', required=True, dest='uuid', help='Rent id to retrieve states for in uuid format')
    # # rent/info
    # rent_info_parser = rent_sp.add_parser('info', help='Returns rent info')
    # rent_info_parser.set_defaults(handler=cli_handler.rent_info)
    # rent_info_parser.add_argument('--id', required=True, dest='rent_id', help='Rent id to retrieve info for')
    # # rent/set
    # rent_set_parser = rent_sp.add_parser('set', help='Sets rent parameters')
    # rent_set_parser.set_defaults(handler=cli_handler.set_rent)
    # rent_set_parser.add_argument('--id', required=True, dest='rent_id', help='Rent id to retrieve info for')
    # rent_set_parser.add_argument('--enable', dest='enable', action='store_true', help='Enables rent')
    # rent_set_parser.add_argument('--disable', dest='enable', action='store_false', help='Disables rent')
    # rent_set_parser.add_argument('--login', help='Protect rent with login/password')
    # rent_set_parser.add_argument('--password', help='Protect rent with login/password')
    # # code
    # code_parser = sp.add_parser('code', help='Mindsync platform codes related actions')
    # code_sp = code_parser.add_subparsers(title='code subcommands', help='Code related subcommands')
    # # code/list
    # code_list_parser = code_sp.add_parser('list', help='Returns all active codes list across the platform')
    # code_list_parser.set_defaults(handler=cli_handler.codes_list)
    # # code/create
    # code_create_parser = code_sp.add_parser('create', help='Create new code')
    # code_create_parser.set_defaults(handler=cli_handler.create_code)
    # #fixme: If ommited...
    # code_create_parser.add_argument('--file', help='Source file to use for code creation. If ommited...')
    # # code/run
    # code_run_parser = code_sp.add_parser('run', help='Run code')
    # code_run_parser.set_defaults(handler=cli_handler.run_code)
    # code_run_parser.add_argument('--id', required=True, dest='code_id', help='Code id to run')
    # code_run_parser.add_argument('--rent-id', required=True, help='Rent id to run code on')
    # # code/info
    # code_run_parser = code_sp.add_parser('info', help='Get code info')
    # code_run_parser.set_defaults(handler=cli_handler.code_info)
    # code_run_parser.add_argument('--id', required=True, dest='code_id', help='Code id to get info of')

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
