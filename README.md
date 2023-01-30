# Mindsync platform API for python

[Mindsync](https://mindsync.ai) is a platform that provides unified access to connect the required capabilities for the AI industry. It brings together businesses, the best talents, services, and solutions in the AI field in one single ecosystem to provide access to scalable task-solving resources and democratize machine learning capacities.

## Run tests

```bash
git clone git@github.com:mindsync-ai/mindsync-api-python.git
cd mindsync-api-python
./run-tests
```

## How to use

```
pip install mindsync
```

### CLI

After that `mindsync` command will be available from the command line.

To get the cli description please use `mindsync --help` or e.g. `mindsync profile --help` to get help on certain command.
Api key and api base url can be specified by environment variables `MINDSYNC_API_KEY` and `MINDSYNC_BASE_URL`.

To get own profile issue one of these with correct api key. Api key is available within the [Mindsync platform](https://app.mindsync.ai/)
under profile/account section.

```bash
mindsync --api-key fd3f8479b0b6b9868bff9bfadfefe69d --prettify profile
MINDSYNC_API_KEY=fd3f8479b0b6b9868bff9bfadfefe69d mindsync --prettify profile
```

### Python

Mindsync provides both async and non-async api version. They have the same interface.

```python
from mindsync.api import AsyncApi

API_KEY = 'fd3f8479b0b6b9868bff9bfadfefe69d'

async def get_profile():
    api = AsyncApi(API_KEY)
    return await api.profile()
```

And blocking version.

```python
from mindsync.api import Api

API_KEY = 'fd3f8479b0b6b9868bff9bfadfefe69d'

api = Api(API_KEY)
print(api.profile())
```

## Examples
```
$ examples/run 
Runs an example(s).

Usage:
    MINDSYNC_API_KEY=... MINDSYNC_BASE_URL=... examples/run EXAMPLE_NAME [EXAMPLE_NAME...]

Arguments:
    EXAMPLE_NAME   Example file name

Options:
    --help         Shows help message
```

```
cd examples
MINDSYNC_API_KEY=16b2e0cd2feacd54c8a872205e70cd56 MINDSYNC_BASE_URL=https://api.mindsync.ai ./run create_n_run_code.py
```

## REST API

The REST API reference is available here https://app.swaggerhub.com/apis-docs/mindsync.ai/mindsync-api/1.2.0.

## Resources 
- www: https://mindsync.ai
- telegram: https://t.me/mindsyncai
- linkedin: https://www.linkedin.com/company/12984228/
- facebook: https://fb.me/mindsync.ai.official/
- medium: https://medium.com/mindsync-ai
