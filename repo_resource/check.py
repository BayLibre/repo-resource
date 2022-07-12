#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>
"""
Check step for an Android repo resource

This is done in a couple of steps
1. Repo init the manifest
2. Repo sync it
3. Generate a manifest snapshot
4. Compute the sha256sum of that snapshot

The sha256sum is the "manifest revision" which is passed to
Concourse as a "version"
"""

import json
import os
import sys
import hashlib
from pathlib import Path
import tempfile
import warnings
import ssh_agent_setup

from contextlib import redirect_stdout

from repo import main as repo

CACHEDIR = '/tmp/repo-resource-cache'


def sha256sum_from_file(file_location: str) -> str:
    sha256 = hashlib.sha256()
    buf_sz = 65536

    with open(file_location, 'rb') as content:
        while True:
            data = content.read(buf_sz)
            if not data:
                break
            sha256.update(data)

    return sha256.hexdigest()


def add_private_key_to_agent(private_key: str):
    tmp = tempfile.mkstemp(text=True)
    fd = tmp[0]
    keypath = tmp[1]

    try:
        os.write(fd, private_key.encode())
        os.close(fd)
        ssh_agent_setup.setup()
        ssh_agent_setup.add_key(keypath)
    # keys can be invalid, so make sure to throw
    # in that case
    except Exception as e:
        raise e
    finally:
        # always delete the key from the container
        os.unlink(keypath)


def repo_init(url, revision='HEAD', name='default.xml'):
    # Google's repo prints a lot of information to stdout.
    # Concourse expects every logs to be emitted to stderr:
    # https://concourse-ci.org/implementing-resource-types.html#implementing-resource-types
    with redirect_stdout(sys.stderr):
        repo._Main([
            '--no-pager', 'init', '--manifest-url', url, '--manifest-branch',
            revision, '--manifest-name', name, '--depth=1', '--no-tags'
        ])


def repo_sync():
    with redirect_stdout(sys.stderr):
        repo._Main([
            '--no-pager', 'sync', '--verbose', '--current-branch', '--detach',
            '--no-tags', '--fail-fast'
        ])


def repo_manifest_out(filename):
    # XXX: We can't use redirect_stdout(StringIO) to keep the manifest
    # snapshot into memory because repo._Main() seems to close
    # the StringIO immediately after being called
    with redirect_stdout(sys.stderr):
        repo._Main([
            '--no-pager', 'manifest', '--revision-as-HEAD', '--output-file',
            filename
        ])


def check(instream) -> list:
    """Checks a json formatted IOstream for new versions

    must print the array of new versions, in chronological order
    (oldest first), to stdout, including the requested version
    if it's still valid.
    """
    payload = json.load(instream)

    if payload['source'].get('url') is None:
        raise RuntimeError('manifest url is mandatory')

    # validate payload inputs
    url = payload['source']['url']
    revision = payload['source'].get('revision', 'HEAD')
    name = payload['source'].get('name', 'default.xml')
    private_key = payload['source'].get('private_key', None)

    if private_key is not None:
        add_private_key_to_agent(private_key)

    # move to CACHEDIR for all repo operations
    initial_path = Path('.').absolute()

    try:
        cache = Path(CACHEDIR)
        cache.mkdir(exist_ok=True)
        os.chdir(cache)

        # disable all terminal prompting
        # check is called from CI/automated systems so we should never
        # be "interactive"
        os.environ['GIT_TERMINAL_PROMPT'] = '0'

        # gitrepo from https://github.com/grouperenault/gitrepo
        # is not python3.10 compatible, so ignore warnings
        warnings.filterwarnings('ignore',
                                category=DeprecationWarning,
                                module='repo')

        repo_init(url, revision, name)
        repo_sync()
        repo_manifest_out('manifest_snapshot.xml')

        sha256 = sha256sum_from_file('manifest_snapshot.xml')
        new_version = {'sha256': sha256}

        versions = payload.get('versions', [])
        if versions.count(new_version) == 0:
            versions.append(new_version)

    except Exception as e:
        raise(e)

    finally:
        os.chdir(initial_path)

    return versions


def main():
    print(json.dumps(check(sys.stdin)))


if __name__ == '__main__':
    main()
