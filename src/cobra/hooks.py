from cobra.exc import HookError

from subprocess import check_call
from importlib.util import spec_from_file_location, module_from_spec
from os.path import join, abspath, realpath, exists
import sys
import os
from shlex import quote


DEFAULT_PYTHON_HOOK = '''from cobra.hooks import default_hook as hook

# By default python hooks relay call to the same named shell scripts 
# like hook_name.sh located in the hooks directory. 
# E.g. before_build.py calls before_build.sh with same arguments 
# except docker client instance.
# 
# Define custom hook as follows
#
# def hook(**kwargs):
#     pass
# 
'''

DEFAULT_SHELL_HOOK = '''#!/usr/bin/env bash

# By default cobra stops on error i.e. exit 1

HOOK_NAME="${1}"
HOOKS_DIR="${2}"
BACKUP_DIR="${3}"
BACKUP_NAME="${4}"

# Note for pull and restore hooks BACKUP_DIR is the CACHE_DIR or 
# the directory where the file resides actually

echo "${@}" > "${HOOKS_DIR}/${HOOK_NAME}.log"
'''


def default_hooks_dir():
    fallback = join(os.getenv('HOME'), '.local/share')
    return join(os.getenv('XDG_DATA_HOME', fallback), 'cobra/hooks')


def default_hook(**kwargs):
    hooks_dir = kwargs['hooks_dir']
    hook_name = kwargs['hook_name']
    kwargs.pop('docker', None)
    
    script_fn = join(hooks_dir, f'{hook_name}.sh')
    if not exists(script_fn):
        return

    check_call([script_fn, *kwargs.values()])


def _source_import(module_name, fn):
    spec = spec_from_file_location(module_name, fn)
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class Hooks:
    HOOKS = ('before_build', 'after_build', 'before_push', 'after_push', 
             'before_pull', 'after_pull', 'before_restore', 'after_restore')
    stop_on_error = set(HOOKS)
     

    def __init__(self, hooks_dir=default_hooks_dir(), disable_hooks=list()):
        self.__hooks_dir = realpath(abspath(hooks_dir))
        if '*' in disable_hooks:
            disable_hooks = self.HOOKS
        else:
            for hook_name in disable_hooks:
                if hook_name not in self.HOOKS:
                    raise ValueError(f'The hook name is invalid [{hook_name}]. The only allowed are {self.HOOKS}')

        self.__disable_hooks = disable_hooks


    def __call__(self, hook_name, **kwargs):
        if hook_name not in self.HOOKS:
            raise ValueError(f'Invalid hook name specified [{hook_name}]')

        if hook_name in self.__disable_hooks:
            return

        hooks_dir = self.__hooks_dir
        fn = join(hooks_dir, f'{hook_name}.py')
        try:
            if not exists(fn):
                # return
                # fixme: If there is no python file found whether to fallback to default or not?
                return default_hook(hook_name=hook_name, hooks_dir=hooks_dir, **kwargs)

            hook = _source_import(hook_name, fn)
            return hook.hook(hook_name=hook_name, hooks_dir=hooks_dir, **kwargs)
        except BaseException as e:
            # fixme: log
            if hook_name in self.stop_on_error:
                raise HookError(f'Interrupted by {hook_name} hook exception [{repr(e)}]') from e

    
    def init_hooks(self, hooks_dir=None):
        hooks_dir = realpath(abspath(hooks_dir if hooks_dir else self.__hooks_dir))
        if hooks_dir is None:
            raise ValueError('No hooks directory has been specified')

        os.makedirs(hooks_dir, exist_ok=True)

        for hook_name in self.HOOKS:
            py_fn = join(hooks_dir, f'{hook_name}.py')
            shell_fn = join(hooks_dir, f'{hook_name}.sh')

            with open(py_fn, 'w') as f:
                f.write(DEFAULT_PYTHON_HOOK)
            with open(shell_fn, 'w') as f:
                f.write(DEFAULT_SHELL_HOOK)
            os.chmod(shell_fn, 0o755)
