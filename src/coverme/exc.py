class CovermeApiError(RuntimeError):
    pass


class CovermeCliError(CovermeApiError):
    pass


class HookError(CovermeApiError):
    pass
