class CovermeApiError(RuntimeError):
    pass


class CovermeCliError(CovermeApiError):
    pass
