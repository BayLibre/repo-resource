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
4. Compute the version of that snapshot
"""

import json
import sys

from repo_resource import common


def check(instream) -> list:
    """Checks a json formatted IOstream for new versions

    must print the array of new versions, in chronological order
    (oldest first), to stdout, including the requested version
    if it's still valid.
    """
    payload = json.load(instream)

    if payload['source'].get('url') is None:
        raise RuntimeError('manifest url is mandatory')

    config = common.source_config_from_payload(payload)

    if config.private_key is not None:
        common.add_private_key_to_agent(config.private_key)

    repo = common.Repo()

    repo.init(config.url, config.revision, config.name)
    repo.sync()
    repo.manifest_out('manifest_snapshot.xml')

    version = common.version_from_file('manifest_snapshot.xml')
    new_version = {'version': version}

    versions = payload.get('versions', [])
    if versions.count(new_version) == 0:
        versions.append(new_version)

    return versions


def main():
    print(json.dumps(check(sys.stdin)))


if __name__ == '__main__':
    main()
