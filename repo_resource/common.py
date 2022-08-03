#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>
"""
Common functions for Android repo resource
"""
import logging
import os
import sys
import tempfile
import warnings

from contextlib import redirect_stdout
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

import ssh_agent_setup
from repo import manifest_xml
from repo import main as repo

CACHEDIR = Path('/tmp/repo-resource-cache')


def add_private_key_to_agent(private_key: str):
    tmp = tempfile.mkstemp(text=True)
    fd = tmp[0]
    keypath = tmp[1]

    if not private_key.endswith('\n'):
        logging.warning('private_key has no newline termination, adding it')
        private_key = private_key + '\n'

    try:
        os.write(fd, private_key.encode())
        os.close(fd)
        ssh_agent_setup.setup()
        ssh_agent_setup.add_key(keypath)
    # keys can be invalid, so make sure to throw in that case
    # Note that we *MUST* catch all exceptions to ensure
    # that we go through the finally block which deletes
    # the key (sensitive information) from disk
    except Exception as e:
        raise e
    finally:
        # always delete the key from the container
        os.unlink(keypath)


class SourceConfiguration(NamedTuple):
    """
    Supported source configuration items when configuring
    repo-resource in a .yml file.
    """
    url: str
    revision: str = 'HEAD'
    name: str = 'default.xml'
    private_key: str = '_invalid'


def source_config_from_payload(payload):
    if payload['source'].get('url') is None:
        raise RuntimeError('manifest url is mandatory')

    p = SourceConfiguration(**payload['source'])
    source_url = urlparse(p.url)

    if source_url.netloc == 'gitlab.com' and \
       (source_url.scheme == 'http' or source_url.scheme == 'https'):
        if not source_url.path.endswith('.git'):
            raise RuntimeError('gitlab http(s) urls must end with .git')

    return p


class Version:
    """Opaque type that represents a version for this resource
    Concourse requires this to become a string at some point
    """
    def __init__(self, version: str):
        self.__version = version

    @classmethod
    def from_file(cls, filename):
        with open(filename) as content:
            version_str = content.read()

        return Version(version_str)

    def to_file(self, filename):
        with open(filename, 'w+') as newfile:
            newfile.write(self.__version)

    def metadata(self) -> str:
        return ''

    def __repr__(self) -> str:
        return self.__version

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            return False

        return self.__version == other.__version


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

    def sync(self, version: Version = None):
        self.__change_to_workdir()
        try:
            with redirect_stdout(sys.stderr):
                if version is None:
                    repo._Main([
                        '--no-pager', 'sync', '--verbose',
                        '--current-branch', '--detach', '--no-tags',
                        '--fail-fast', '--force-sync'
                    ])
                else:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_manifest = os.path.join(tmpdir, 'manifest_tmp')
                        version.to_file(tmp_manifest)
                        repo._Main([
                            '--no-pager', 'sync', '--verbose',
                            '--current-branch', '--detach', '--no-tags',
                            '--fail-fast', '--manifest-name',
                            tmp_manifest, '--force-sync'
                        ])
        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()

    def currentVersion(self) -> Version:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = os.path.join(tmpdir, 'manifest_snapshot')
            self.__manifest_out(tmp_manifest)
            version = Version.from_file(tmp_manifest)

        return version

    def metadata(self):
        metadata = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = os.path.join(tmpdir, 'manifest_snapshot')
            self.__manifest_out(tmp_manifest)
            xm = manifest_xml.XmlManifest(
                os.path.join(self.__workdir, '.repo'), tmp_manifest)
            for p in xm.projects:
                metadata.append({'name': p.name, 'value': p.GetRevisionId()})

        return metadata

    def __manifest_out(self, filename):
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
