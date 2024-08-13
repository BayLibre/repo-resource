#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>

import json
from io import StringIO
import unittest
from pathlib import Path
from timeit import default_timer as timer
import shutil
import repo
import xml.etree.ElementTree as ET

from . import check
from . import common


class TestCheck(unittest.TestCase):

    def setUp(self):
        self.aosp_platform_source = {
            'source': {
                'url': 'https://android.googlesource.com/platform'
            }
        }
        self.demo_manifests_source = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'revision': 'main',
                'name': 'aosp_device_fixed.xml'
            }
        }
        self.demo_manifests_source_norev = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'name': 'aosp_device_fixed.xml'
            }
        }
        self.default_rev_in_remote = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'revision': 'main',
                'name': 'default_rev_in_remote.xml'
            }
        }
        self.demo_ssh_manifests_source = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'revision': 'main',
                'name': 'baylibre_ssh_project.xml',
            }
        }
        self.demo_multiple_aosp_device_source = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'revision': 'main',
                'name': 'aosp_multiple_device_fixed.xml'
            }
        }
        self.remove_project_source = {
            'source': {
                'url': 'https://github.com/makohoek/demo-manifests.git',
                'revision': 'main',
                'name': 'aosp_remove_yukawa_project.xml'
            }
        }

    def tearDown(self):
        p = common.CACHEDIR
        if p.exists():
            shutil.rmtree(p)

    def test_input_json_fails_without_source(self):
        incomplete_data = {'source': {}}
        instream = StringIO(json.dumps(incomplete_data))
        with self.assertRaises(RuntimeError):
            check.check(instream)

    def test_invalid_manifest_url(self):
        invalid_data = {
            'source': {
                'url': 'this-is-not-an-url',
            },
        }
        instream = StringIO(json.dumps(invalid_data))
        with self.assertRaises(repo.error.GitError):
            check.check(instream)

    def test_unreachable_manifest(self):
        unreachable_data = {
            'source': {
                'url':
                'https://android.googlesource.com/platform/manifest-typo'
            },
        }
        instream = StringIO(json.dumps(unreachable_data))
        with self.assertRaises(repo.error.GitError):
            check.check(instream)

    def test_unknown_revision(self):
        unknown_revision_data = self.aosp_platform_source
        unknown_revision_data['source']['revision'] = 'unknown'
        instream = StringIO(json.dumps(unknown_revision_data))
        with self.assertRaises(SystemExit):
            check.check(instream)

    def test_unknown_manifest_name(self):
        unknown_manifest_data = self.aosp_platform_source
        unknown_manifest_data['source']['revision'] = 'master'
        unknown_manifest_data['source']['name'] = 'unknown.xml'
        instream = StringIO(json.dumps(unknown_manifest_data))
        with self.assertRaises(SystemExit):
            check.check(instream)

    def test_default_rev_in_remote(self):
        data = self.default_rev_in_remote
        instream = StringIO(json.dumps(data))
        check.check(instream)

    def test_branch_defaults_to_HEAD(self):
        no_revision_data = self.demo_manifests_source_norev
        instream = StringIO(json.dumps(no_revision_data))
        check.check(instream)

    def test_manifest_name_defaults(self):
        d = {
            'source': {
                'url': 'https://android.googlesource.com/tools/manifest',
                'revision': 'fetch_artifact-dev'
            },
        }
        instream = StringIO(json.dumps(d))
        check.check(instream)
        manifests = common.CACHEDIR / '.repo' / 'manifests'
        self.assertTrue(manifests.exists())

    # so here, we init from a public manifest
    # init is completely working fine
    # but sync will fail miserably because one of the projects
    # is un-reachable
    def test_unreachable_projects_in_manifest(self):
        unreachable_projects_data = self.demo_manifests_source
        unreachable_projects_data['source']['name'] = 'unreachable_project.xml'

        instream = StringIO(json.dumps(unreachable_projects_data))
        with self.assertRaises(TypeError):
            check.check(instream)

    def test_first_revision(self):
        data = self.demo_manifests_source
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        # we passed no version as input, so we should just get current version
        self.assertEqual(len(versions), 1)

    def test_same_revision(self):
        data = self.demo_manifests_source
        data['versions'] = [{
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n  <remote name="aosp" fetch="https://android.googlesource.com/"/>\n  \n  <default remote="aosp" revision="refs/tags/android-12.0.0_r32"/>\n  \n  <project name="device/generic/common" path="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba" upstream="refs/tags/android-12.0.0_r32" dest-branch="refs/tags/android-12.0.0_r32" groups="pdk"/>\n</manifest>\n'  # noqa: E501
        }]
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        # we passed the same version so we should only get one result
        self.assertEqual(len(versions), 1)

    # here we need a hard-coded manifest
    # which also contains hard-coded revisions to make
    # sure nothing ever moves
    def test_known_version(self):
        data = self.demo_manifests_source
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        # we passed no version as input, so we should just get current version
        self.assertEqual(len(versions), 1)
        # and we know that version
        expected_version = '<manifest><remote fetch="https://android.googlesource.com/" name="aosp"></remote><default remote="aosp" revision="refs/tags/android-12.0.0_r32"></default><project groups="pdk" name="device/generic/common" path="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba"></project></manifest>'  # noqa: E501
        version = versions[0]['version']
        self.assertEqual(version, expected_version)

    # we can reuse the same hard-coded manifest here
    # but we use a newer version (using a different git branch)
    def test_new_revision(self):
        data = self.demo_manifests_source
        data['versions'] = [{
            'version':
            '<manifest><remote fetch="https://android.googlesource.com/" name="aosp"></remote><default remote="aosp" revision="refs/tags/android-12.0.0_r32"></default><project groups="pdk" name="device/generic/common" revision="older-sha1"></project></manifest>'  # noqa: E501
        }]
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        self.assertEqual(len(versions), 2)
        expected_version = '<manifest><remote fetch="https://android.googlesource.com/" name="aosp"></remote><default remote="aosp" revision="refs/tags/android-12.0.0_r32"></default><project groups="pdk" name="device/generic/common" path="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba"></project></manifest>'  # noqa: E501
        newest_version = versions[-1]['version']
        self.assertEqual(newest_version, expected_version)

    def test_invalid_revision(self):
        data = self.demo_manifests_source
        data['versions'] = [{'version': 'invalid-version'}]
        instream = StringIO(json.dumps(data))
        with self.assertRaises(ET.ParseError):
            check.check(instream)

    @unittest.skipUnless(
        Path('development/ssh/test_key').exists(), "requires ssh test key")
    def test_ssh_private_key(self):
        data = self.demo_ssh_manifests_source

        private_test_key = Path('development/ssh/test_key')
        data['source']['private_key'] = private_test_key.read_text()

        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        # we passed no version as input, so we should just get current version
        self.assertEqual(len(versions), 1)

    @unittest.skipUnless(
        Path('development/ssh/test_key').exists(), "requires ssh test key")
    def test_ssh_private_key_without_newline(self):
        data = self.demo_ssh_manifests_source

        private_test_key = Path('development/ssh/test_key')

        # strip the trailing newline from the key. This should break
        # ssh key parsing with:
        # raise Exception('failed to add the key: {}'.format(key_file))
        # Exception: failed to add the key: /tmp/tmpzf7o24iu
        data['source']['private_key'] = private_test_key.read_text().rstrip(
            '\n')

        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        # we passed no version as input, so we should just get current version
        self.assertEqual(len(versions), 1)

    def test_ssh_private_key_without_project_access(self):
        data = self.demo_ssh_manifests_source

        # This is just a private key randomly generated with
        # ssh-keygen. It should not have access to demo_ssh_manifests_source
        data['source']['private_key'] = \
            '''-----BEGIN OPENSSH PRIVATE KEY-----
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
-----END OPENSSH PRIVATE KEY-----'''

        instream = StringIO(json.dumps(data))
        versions = []
        with self.assertRaises(TypeError):
            versions = check.check(instream)

        self.assertEqual(len(versions), 0)

    def test_ssh_private_key_without_manifest_access(self):
        data = self.demo_ssh_manifests_source

        # use a git/ssh url this time with an invalid key
        data['source']['url'] = 'git@github.com:makohoek/demo-manifests.git'

        # This is just a private key randomly generated with
        # ssh-keygen. It should not have access to demo_ssh_manifests_source
        data['source']['private_key'] = \
            '''-----BEGIN OPENSSH PRIVATE KEY-----
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
-----END OPENSSH PRIVATE KEY-----'''

        instream = StringIO(json.dumps(data))
        versions = []
        with self.assertRaises(SystemExit):
            versions = check.check(instream)

        self.assertEqual(len(versions), 0)

    # test that we can specify an amount of jobs
    # This is a little flaky because it depends on network
    def test_jobs_limit(self):
        data = self.demo_multiple_aosp_device_source

        data['source']['jobs'] = 24
        start = timer()
        instream = StringIO(json.dumps(data))
        check.check(instream)
        end = timer()
        fast_duration = end - start

        # call tearDown() manually to clear the CACHE dir
        self.tearDown()

        data['source']['jobs'] = 1
        start = timer()
        instream = StringIO(json.dumps(data))
        check.check(instream)
        end = timer()
        slow_duration = end - start

        print('fast: {} slow: {}'.format(fast_duration, slow_duration))
        self.assertTrue(fast_duration < slow_duration)

    # test that the `<remove-project>` tag is correctly handled
    # When rebuilding the Version string.
    # See: https://github.com/makohoek/repo-resource/issues/36
    def test_remove_project_version(self):
        data = self.remove_project_source
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)

        expected_version = '<manifest><remote fetch="https://android.googlesource.com/" name="aosp"></remote><remote fetch="https://gitlab.baylibre.com/baylibre/amlogic/atv/aosp/" name="baylibre"></remote><default remote="aosp" revision="refs/tags/android-13.0.0_r62"></default><project name="device/amlogic/yukawa" path="device/amlogic/yukawa" remote="baylibre" revision="0f3423ec0c103d113c2c03953b3a79bb479fd5b7"></project></manifest>'  # noqa: E501

        version = versions[0]['version']
        self.assertEqual(version, expected_version)

    def test_no_remove_project_element(self):
        data = self.remove_project_source
        instream = StringIO(json.dumps(data))
        versions = check.check(instream)
        version = versions[0]['version']
        self.assertNotIn('remove-project', version)


if __name__ == '__main__':
    unittest.main()
