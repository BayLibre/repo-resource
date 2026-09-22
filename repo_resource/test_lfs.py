#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>

import json
from io import StringIO
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import check
from . import common
from . import in_


class TestGitLfs(unittest.TestCase):
    def _checkout_lfs_project(self, git_lfs):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / 'project'
            manifests = root / 'manifests'

            def git(path, *args):
                return subprocess.check_output(
                    ['git', '-C', str(path), *args],
                    stderr=subprocess.STDOUT,
                )

            for path in (project, manifests):
                path.mkdir()
                git(path, 'init', '-b', 'main')
                git(path, 'config', 'user.name', 'repo-resource')
                git(path, 'config', 'user.email',
                    'repo-resource@concourse-ci.org')

            git(project, 'lfs', 'install', '--local')
            git(project, 'lfs', 'track', '*.bin')
            payload = b'\x00Git LFS test payload\n'
            (project / 'payload.bin').write_bytes(payload)
            git(project, 'add', '.gitattributes', 'payload.bin')
            git(project, 'commit', '-s', '-m', 'Add LFS fixture')

            (manifests / 'default.xml').write_text(
                '<manifest>\n'
                f'<remote name="local" fetch="{root.as_uri()}/"/>\n'
                '<default remote="local" revision="main"/>\n'
                '<project name="project"/>\n'
                '</manifest>\n'
            )
            git(manifests, 'add', 'default.xml')
            git(manifests, 'commit', '-s', '-m', 'Add manifest fixture')

            data = {'source': {
                'url': manifests.as_uri(),
                'revision': 'main',
                'jobs': 1,
                'check_jobs': 1,
            }}
            if git_lfs:
                data['source']['git_lfs'] = True
            data['version'] = check.check(StringIO(json.dumps(data)))[-1]
            dest = root / 'checkout'
            result = in_.in_(StringIO(json.dumps(data)), str(dest))
            self.assertEqual(result['version'], data['version'])
            contents = (dest / 'project' / 'payload.bin').read_bytes()
            if git_lfs:
                self.assertEqual(contents, payload)
            else:
                self.assertTrue(contents.startswith(
                    b'version https://git-lfs.github.com/spec/v1\n'))

    def test_git_lfs_downloads_objects(self):
        self._checkout_lfs_project(git_lfs=True)

    def test_git_lfs_defaults_to_pointer_files(self):
        self._checkout_lfs_project(git_lfs=False)

    def tearDown(self):
        if common.CACHEDIR.exists():
            shutil.rmtree(common.CACHEDIR)
