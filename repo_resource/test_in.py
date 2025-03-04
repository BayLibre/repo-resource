#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>

import json
from io import StringIO
import shutil
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from . import check
from . import common
from . import in_


class TestIn(unittest.TestCase):
    def setUp(self):
        self.demo_manifests_source = {
            'source': {
                'url': 'https://github.com/baylibre/demo-manifests.git',
                'revision': 'main',
                'name': 'aosp_device_fixed.xml'
            }
        }
        self.demo_ssh_manifests_source = {
            'source': {
                'url': 'https://github.com/baylibre/demo-manifests.git',
                'revision': 'main',
                'name': 'baylibre_ssh_project.xml',
            }
        }

    def tearDown(self):
        p = common.CACHEDIR
        if p.exists():
            shutil.rmtree(p)

    def test_fails_on_invalid_version(self):
        data = self.demo_manifests_source
        data['version'] = {'version': 'invalid-version'}
        instream = StringIO(json.dumps(data))
        with self.assertRaises(ET.ParseError):
            in_.in_(instream, str(common.CACHEDIR))

    def test_dest_dir_is_created(self):
        data = self.demo_manifests_source
        data['version'] = {
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n  <remote name="aosp" fetch="https://android.googlesource.com/"/>\n  \n  <default remote="aosp" revision="refs/tags/android-12.0.0_r32"/>\n  \n  <project name="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba" upstream="refs/tags/android-12.0.0_r32" dest-branch="refs/tags/android-12.0.0_r32" groups="pdk"/>\n</manifest>\n'  # noqa: E501
        }

        instream = StringIO(json.dumps(data))
        in_.in_(instream, str(common.CACHEDIR))

        self.assertTrue(common.CACHEDIR.exists())

    def test_sync_ok(self):
        data = {
            'source': {
                'url': 'https://android.googlesource.com/tools/manifest',
                'revision': 'fetch_artifact-dev'
            },
        }
        data['version'] = {
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n<remote name="aosp" fetch=".." review="https://android-review.googlesource.com/"/>\n<default remote="aosp" revision="master" sync-j="4"/>\n<project name="platform/prebuilts/go/linux-x86" path="prebuilts/go/linux-x86" groups="linux" clone-depth="1"/>\n<project name="tools/fetch_artifact" path="fetch_artifact"/>\n</manifest>'  # noqa: E501
        }
        instream = StringIO(json.dumps(data))
        in_.in_(instream, str(common.CACHEDIR))
        # no assert/assumption to call. repo init and sync should
        # just be called. maybe we can check for a file as well
        readme = common.CACHEDIR / 'fetch_artifact' / 'README.md'
        self.assertTrue(readme.exists())

    def test_no_manifest_version(self):
        data = self.demo_manifests_source
        instream = StringIO(json.dumps(data))
        with self.assertRaises(KeyError):
            in_.in_(instream, str(common.CACHEDIR))

    def test_valid_in(self):
        data = self.demo_manifests_source
        data['version'] = {
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n  <remote name="aosp" fetch="https://android.googlesource.com/"/>\n  \n  <default remote="aosp" revision="refs/tags/android-12.0.0_r32"/>\n  \n  <project name="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba" upstream="refs/tags/android-12.0.0_r32" dest-branch="refs/tags/android-12.0.0_r32" groups="pdk"/>\n</manifest>\n'  # noqa: E501
        }

        instream = StringIO(json.dumps(data))
        fetched_version = in_.in_(instream, str(common.CACHEDIR))

        self.assertEqual(
            common.Version(fetched_version['version']['version']).standard(),
            common.Version(data['version']['version']).standard()
        )

    def test_get_metadata(self):
        data = self.demo_manifests_source
        data['version'] = {
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n  <remote name="aosp" fetch="https://android.googlesource.com/"/>\n  \n  <default remote="aosp" revision="refs/tags/android-12.0.0_r32"/>\n  \n  <project name="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba" upstream="refs/tags/android-12.0.0_r32" dest-branch="refs/tags/android-12.0.0_r32" groups="pdk"/>\n</manifest>\n'  # noqa: E501
        }
        instream = StringIO(json.dumps(data))
        result = in_.in_(instream, str(common.CACHEDIR))
        expected_project = 'device/generic/common'
        expected_revision = '033d50e2298811d81de7db8cdea63e349a96c9ba'

        self.assertEqual(result['metadata'][0]['name'], expected_project)
        self.assertEqual(result['metadata'][0]['value'], expected_revision)

    @unittest.skipUnless(
        Path('development/ssh/test_key').exists(), "requires ssh test key")
    def test_ssh_private_key(self):

        data = self.demo_ssh_manifests_source

        private_test_key = Path('development/ssh/test_key')
        data['source']['private_key'] = private_test_key.read_text()

        instream = StringIO(json.dumps(data))
        versions = check.check(instream)

        data['version'] = versions[0]

        instream = StringIO(json.dumps(data))
        in_.in_(instream, str(common.CACHEDIR))

    def test_manifest_is_saved(self):
        data = self.demo_manifests_source
        data['version'] = {
            'version':
            '<?xml version="1.0" encoding="UTF-8"?>\n<manifest>\n  <remote name="aosp" fetch="https://android.googlesource.com/"/>\n  \n  <default remote="aosp" revision="refs/tags/android-12.0.0_r32"/>\n  \n  <project name="device/generic/common" revision="033d50e2298811d81de7db8cdea63e349a96c9ba" upstream="refs/tags/android-12.0.0_r32" dest-branch="refs/tags/android-12.0.0_r32" groups="pdk"/>\n</manifest>\n'  # noqa: E501
        }
        instream = StringIO(json.dumps(data))
        in_.in_(instream, str(common.CACHEDIR))

        saved_manifest_version = common.Version.from_file(
            common.CACHEDIR / '.repo_manifest.xml')
        expected_manifest_version = common.Version(data['version']['version'])

        self.assertEqual(saved_manifest_version, expected_manifest_version)
