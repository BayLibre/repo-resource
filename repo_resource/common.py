#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>
"""
Common functions for Android repo resource
"""
import atexit
import logging
import os
import sys
import tempfile
import warnings
import git
import re
import xml.etree.ElementTree as ET

from contextlib import redirect_stdout
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse
from multiprocessing import Pool

import ssh_agent_setup
from repo import manifest_xml
from repo import main as repo


DEFAULT_CHECK_JOBS = 2
CACHEDIR = Path('/tmp/repo-resource-cache')
SHA1_PATTERN = re.compile(r'^[0-9a-f]{40}$')
EXCLUDE_ATTRS = {'dest-branch', 'upstream'}
# Elements available at
# https://gerrit.googlesource.com/git-repo/+/master/docs/manifest-format.md
TAGS = [
  'remote',
  'default',
  'manifest-server',
  'project',
  'extend-project',
  'annotation',
  'copyfile',
  'linkfile',
  'remove-project',
  'include',
  'superproject',
  'contactinfo'
]


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


def remove_private_key_from_agent():
    ssh_agent_setup._kill_agent()
    # don't call _kill_agent twice via exit()
    atexit.unregister(ssh_agent_setup._kill_agent)


def is_sha1(s):
    return re.match(SHA1_PATTERN, s)


def multi_run_wrapper(args):
    return getRevision(*args)


def getRevision(remote, remoteUrl, project, branch):
    """
    Get latest commit sha1 for revision
    with git ls-remote command for each project
    without downloading the whole repo
    """
    try:
        with redirect_stdout(sys.stderr):
            # return tuple (remote/project, branch, revision)
            print('Fetching revision for {}/{} - {}...'.format(
                remote, project, branch))
            if is_sha1(branch):
                return (remote + '/' + project, branch, branch)
            g = git.cmd.Git()

            headRef = branch
            # v1.0^{} is the commit referring to tag v1.0
            # git ls-remote returns the tag sha1 if left as is
            if branch.startswith('refs/tags'):
                headRef += '^{}'

            url, revList = (
                remote + '/' + project,
                g.ls_remote(remoteUrl+'/'+project, headRef).split()
            )

            # convert revision list to revision dict:
            # ['SHA1', 'refs/heads/XXXX', 'SHA1', 'refs/heads/YYYY']
            # -> {'refs/heads/XXXX': 'SHA1', 'refs/heads/YYYY': 'SHA1'}
            revDict = dict([(b, a)
                            for a, b in zip(revList[::2], revList[1::2])])

            if branch.startswith('refs/tags'):
                rev = headRef
            else:
                rev = 'refs/heads/' + branch

            print('{} - {}: {}'.format(url, branch, revDict[rev]))

            # return url, branch (without any suffix) and revision
            return (url, branch, revDict[rev])
    except Exception as e:
        with redirect_stdout(sys.stderr):
            print('Cannot fetch project {}/{}'.format(remoteUrl, project))
            print(e)


class SourceConfiguration(NamedTuple):
    """
    Supported source configuration items when configuring
    repo-resource in a .yml file.
    """
    url: str
    revision: str = 'HEAD'
    name: str = 'default.xml'
    private_key: str = '_invalid'
    depth: int = -1
    jobs: int = 0
    check_jobs: int = DEFAULT_CHECK_JOBS
    rewrite: str = None


def source_config_from_payload(payload):
    if payload['source'].get('url') is None:
        raise RuntimeError('manifest url is mandatory')

    p = SourceConfiguration(**payload['source'])
    source_url = urlparse(p.url)

    if (
        source_url.netloc == 'gitlab.com' and
        re.fullmatch('https?', source_url.scheme)
       ):
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

    def standard(self) -> str:
        try:
            root = ET.fromstring(self.__version)
            for element in root:
                if element.tag not in TAGS:
                    root.remove(element)
            # Sort entries in manifest by element position in TAGS
            # Default 999 if element not found in TAGS table (comes last)
            # and name alphabetically
            sorted_xml = sorted(root, key=lambda x: (
                TAGS.index(x.tag) if x.tag in TAGS else 999,
                x.get('name') or ""))
            manifest = ET.Element('manifest')
            manifest.extend(sorted_xml)
            return ET.canonicalize(
                ET.tostring(manifest),
                strip_text=True,
                exclude_attrs=EXCLUDE_ATTRS
            )
        except ET.ParseError as e:
            with redirect_stdout(sys.stderr):
                print('Version is not valid xml')
                raise e

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

    def __init__(self, url, revision='HEAD', name='default.xml',
                 depth=-1, workdir=CACHEDIR):
        self.__workdir = workdir
        self.__oldpwd = None
        self.__url = url
        self.__revision = revision
        self.__name = name
        self.__depth = depth
        self.__version: Version = None
        self.__remote_url = {}
        self.__remote_revision = {}
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

    def __add_remote_url(self, remote, url):
        self.__remote_url[remote] = url

    def __add_remote_revision(self, remote, rev):
        self.__remote_revision[remote] = rev

    def __get_remote_url(self, remote):
        return self.__remote_url[remote]

    def __get_remote_revision(self, remote):
        return self.__remote_revision.get(remote)

    def set_rewrite(self, matrix: dict = None):
        if matrix is None:
            return self

        with redirect_stdout(sys.stderr), \
                tempfile.TemporaryDirectory() as tempdir:
            gitrepo = git.Repo.init(tempdir)
            print("Applying rewrite rules")
            for from_url, to_url in matrix.items():
                print('{} -> {}'.format(from_url, to_url))
                gitrepo \
                    .config_writer(config_level='global') \
                    .set_value(
                        'url "{}"'.format(to_url),
                        "insteadOf", from_url
                    ) \
                    .release()
        return self

    def init(self):
        self.__change_to_workdir()
        try:
            # Google's repo prints a lot of information to stdout.
            # Concourse expects every logs to be emitted to stderr:
            # https://concourse-ci.org/implementing-resource-types.html#implementing-resource-types  # noqa: E501
            with redirect_stdout(sys.stderr):
                repo_cmd = [
                    '--no-pager', 'init', '--quiet', '--manifest-url',
                    self.__url, '--manifest-name',
                    self.__name, '--no-tags',
                ]
                if self.__depth > 0:
                    repo_cmd.append('--depth={}'.format(self.__depth))

                if self.__revision is not None:
                    repo_cmd.append(
                        '--manifest-branch={}'.format(self.__revision)
                    )

                print('Downloading manifest from {}'.format(self.__url))
                repo._Main(repo_cmd)
                print('repo has been initialized in {}'.format(self.__workdir))
            return self

        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()

    def sync(self, version: Version, jobs: int = 0):
        self.__change_to_workdir()
        try:
            with redirect_stdout(sys.stderr):
                repo_cmd = [
                    '--no-pager', 'sync', '--verbose',
                    '--current-branch', '--detach', '--no-tags',
                    '--fail-fast', '--force-sync'
                ]

                if jobs > 0:
                    repo_cmd.append('--jobs={}'.format(jobs))

                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_manifest = os.path.join(tmpdir, 'manifest_tmp')
                    version.to_file(tmp_manifest)
                    repo_cmd.append(
                        '--manifest-name={}'.format(tmp_manifest))
                    repo._Main(repo_cmd)
                if os.listdir(self.__workdir) == []:
                    raise Exception('Sync failed. Is manifest correct?')
            return self
        except Exception as e:
            raise (e)
        finally:
            self.__restore_oldpwd()

    # Update self.__version after repo sync
    def update_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = os.path.join(tmpdir, 'manifest_snapshot')
            self.__manifest_out(tmp_manifest)
            self.__version = Version.from_file(tmp_manifest)

    def save_manifest(self, filename):
        with redirect_stdout(sys.stderr):
            full_path = self.__workdir / filename
            print('Saving manifest to {}'.format(full_path))
            self.__version.to_file(full_path)
        return self

    def currentVersion(self) -> Version:
        return self.__version

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

    def resolve_manifest_include(self, manifest):
        for idx, element in enumerate(list(manifest.iter())):
            if element.tag == 'include':
                sub_manifest_name = element.get('name')
                sub_xml = ET.parse('.repo/manifests/'+sub_manifest_name)
                sub_manifest = sub_xml.getroot()

                # resolve recursively include in sub manifests
                self.resolve_manifest_include(sub_manifest)

                # insert sub manifest in the parent without 'manifest' elements
                for sub_element in reversed(list(sub_manifest.iter())):
                    if sub_element.tag != 'manifest':
                        manifest.insert(idx, sub_element)

                # remove 'include' element
                manifest.remove(element)

    def update_manifest(self, jobs):
        projects = []
        removed_projects = []

        jobs = jobs or DEFAULT_CHECK_JOBS
        self.__change_to_workdir()
        try:
            with redirect_stdout(sys.stderr):
                print('Updating project revisions in manifest')
                xml = ET.parse('.repo/manifests/'+self.__name)
                manifest = xml.getroot()
                self.resolve_manifest_include(manifest)

                for r in manifest.findall('remote'):
                    url = r.get('fetch').rstrip('/')
                    if not re.match("[a-zA-Z]+://", url):
                        url = re.sub('/[a-z-.]*$', '/', self.__url) + url
                    self.__add_remote_url(r.get('name'), url)
                    if (rev := r.get('revision')) is not None:
                        self.__add_remote_revision(r.get('name'), rev)

                # Get default values from manifest
                defaults = manifest.find('default')
                if defaults is not None:
                    defaultRemote = defaults.get('remote')
                    defaultBranch = defaults.get('revision') \
                        or self.__get_remote_revision(defaultRemote)

                # Handle <remove-project /> element:
                # - Should not be present in final XML (for version)
                # - Should remove first matching project by name
                for p in manifest.findall('remove-project'):
                    project = p.get('name')
                    removed_projects.append(project)
                    manifest.remove(p)

                for p in manifest.findall('project'):
                    project = p.get('name')
                    if project in removed_projects:
                        manifest.remove(p)
                        removed_projects.remove(project)
                    # If there are no more projects to remove, we can
                    # skip parsing the rest of the projects
                    if not removed_projects:
                        break

                for p in manifest.findall('project'):
                    project = p.get('name')
                    projectBranch = p.get('revision') or defaultBranch
                    projectRemote = p.get('remote') or defaultRemote
                    projectRemoteUrl = self.__get_remote_url(projectRemote)
                    projects.append((projectRemote, projectRemoteUrl,
                                     project, projectBranch))

                with Pool(jobs) as pool:
                    revisionList = pool.map(multi_run_wrapper, projects)

                # Update revisions
                for p in manifest.findall('project'):
                    project = p.get('name')
                    projectBranch = p.get('revision') or defaultBranch
                    projectRemote = p.get('remote') or defaultRemote
                    # find revision of the project in revisionList
                    for url, branch, rev in revisionList:
                        if (
                            projectRemote + "/" + project == url
                            and branch == projectBranch
                        ):
                            projectRev = rev
                            break
                    p.set('revision', projectRev)

                self.__version = Version(
                    ET.canonicalize(
                        ET.tostring(manifest, encoding='unicode'),
                        strip_text=True
                    )
                )
            return self

        except FileNotFoundError as e:
            with redirect_stdout(sys.stderr):
                print('cannot open', '.repo/manifests/'+self.__name)
                raise e
        except TypeError as e:
            with redirect_stdout(sys.stderr):
                print('Error fetching some project repo')
                raise e
        except Exception as e:
            raise e
        finally:
            self.__restore_oldpwd()
