#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>
"""
Common functions for Android repo resource
"""
import hashlib
import os
import sys
import tempfile
import warnings

from contextlib import redirect_stdout
from pathlib import Path
from typing import NamedTuple

import ssh_agent_setup
from repo import main as repo

CACHEDIR = Path('/tmp/repo-resource-cache')


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


class SourceConfiguration(NamedTuple):
    """
    Supported source configuration items when configuring
    repo-resource in a .yml file.
    """
    url: str
    revision: str = 'HEAD'
    name: str = 'default.xml'
    private_key: str = None


def source_config_from_payload(payload):
    if payload['source'].get('url') is None:
        raise RuntimeError('manifest url is mandatory')

    p = SourceConfiguration(**payload['source'])

    return p


class Repo:
    """
    Wrapper around gitrepo to perform operations
    such as init/sync and manifest
    """

    def __init__(self, workdir=CACHEDIR):
        self.__workdir = workdir
        self.__oldpwd = None
        workdir.mkdir(parents=True, exist_ok=True)

        # gitrepo from https://github.com/grouperenault/gitrepo
        # is not python3.10 compatible, so ignore warnings
        warnings.filterwarnings('ignore',
                                category=DeprecationWarning,
                                module='repo')

        # disable all terminal prompting
        # Repo is intended to be used in CI/automated systems so we
        # should never be "interactive"
        os.environ['GIT_TERMINAL_PROMPT'] = '0'

    def __change_to_workdir(self):
        # move to work directory for all repo operations
        self.__oldpwd = Path('.').absolute()
        os.chdir(self.__workdir)

    def __restore_oldpwd(self):
        os.chdir(self.__oldpwd)

    def init(self, url, revision='HEAD', name='default.xml'):
        self.__change_to_workdir()
        try:
            # Google's repo prints a lot of information to stdout.
            # Concourse expects every logs to be emitted to stderr:
            # https://concourse-ci.org/implementing-resource-types.html#implementing-resource-types
            with redirect_stdout(sys.stderr):
                repo._Main([
                    '--no-pager', 'init', '--manifest-url', url,
                    '--manifest-branch', revision, '--manifest-name', name,
                    '--depth=1', '--no-tags'
                ])
        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()

    def sync(self):
        self.__change_to_workdir()
        try:
            with redirect_stdout(sys.stderr):
                repo._Main([
                    '--no-pager', 'sync', '--verbose', '--current-branch',
                    '--detach', '--no-tags', '--fail-fast'
                ])
        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()

    def manifest_out(self, filename):
        self.__change_to_workdir()
        try:
            # XXX: We can't use redirect_stdout(StringIO) to keep the manifest
            # snapshot into memory because repo._Main() seems to close
            # the StringIO immediately after being called
            with redirect_stdout(sys.stderr):
                repo._Main([
                    '--no-pager', 'manifest', '--revision-as-HEAD',
                    '--output-file',
                    os.path.join(self.__oldpwd / filename)
                ])
        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()
