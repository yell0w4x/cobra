class CobraApiError(RuntimeError):
    pass


class CobraCliError(CobraApiError):
    pass


class HookError(CobraApiError):
    pass
