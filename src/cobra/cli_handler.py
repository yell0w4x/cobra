from cobra.api import Api
from cobra.exc import CobraCliError

# import json
import inspect


class CliHandler:
    def __init__(self):
        # make method stubs
        def create_method(name):
            def method(**kwargs):
                try:
                    api = self.__api
                except AttributeError:
                    raise CobraCliError('Api object is not binded')

                func = getattr(api, name)
                return func(**kwargs)
            return method

        methods = inspect.getmembers(Api, predicate=inspect.isfunction)
        for m in methods:
            name, _ = m
            if '__' not in name:
                setattr(self, name, create_method(name))


    def bind(self, api):
        if not isinstance(api, Api):
            raise ValueError('Invalid argument')

        self.__api = api
