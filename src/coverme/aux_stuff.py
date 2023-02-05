import string, random


def rand_str(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))
