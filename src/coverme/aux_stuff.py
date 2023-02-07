import string, random, json


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def print_json(data, pretty=True):
    if pretty:
        print(json.dumps(data, indent=4, sort_keys=True))
    else:
        print(json.dumps(data))
