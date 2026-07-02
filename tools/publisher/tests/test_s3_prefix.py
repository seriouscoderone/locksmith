from locksmith_publisher.s3_client import S3


class _FakePaginator:
    def __init__(self, keys):
        self._keys = keys
        self.seen_prefix = None

    def paginate(self, *, Bucket, Prefix):
        self.seen_prefix = Prefix
        return [{"Contents": [{"Key": k} for k in self._keys]}]


class _FakeClient:
    def __init__(self, keys):
        self._pag = _FakePaginator(keys)

    def get_paginator(self, _name):
        return self._pag


def _s3(keys):
    s = S3.__new__(S3)
    s.client = _FakeClient(keys)
    return s


def test_default_prefix_is_releases():
    s = _s3(["releases/1.2.3/Locksmith-1.2.3.dmg"])
    assert s.list_release_versions(bucket="b") == ["1.2.3"]
    assert s.client._pag.seen_prefix == "releases/"


def test_branded_prefix_enumerates_under_it():
    s = _s3(["usurance/releases/0.3.0/Usurance-0.3.0.dmg"])
    got = s.list_release_versions(bucket="b", prefix="usurance/releases")
    assert got == ["0.3.0"]
    assert s.client._pag.seen_prefix == "usurance/releases/"
