#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>

import json
import sys

from pathlib import Path

from repo_resource import common


def in_(instream, dest_dir='.'):
    """Fetch the resource and place it in dest_dir

    We receive on stdin the configured source
    and a precise version of the resource to fetch.

    If the desired resource version is unavailable (for example, if it was
    deleted), the script must exit with error.

    The script must emit the fetched version, and may emit metadata as a list
    of key-value pairs. This data is intended for public consumption and will
    make it upstream, intended to be shown on the build's page.
    """
    payload = json.load(instream)

    if payload['version'].get('version') is None:
        raise RuntimeError('Did not receive any version')

    config = common.source_config_from_payload(payload)
    requested_version = common.Version(payload['version']['version'])

    if config.private_key != '_invalid':
        common.add_private_key_to_agent(config.private_key)

    repo = common.Repo(workdir=Path(dest_dir))

    repo.init(config.url, config.revision, config.name)
    repo.sync(requested_version)
    fetched_version = repo.currentVersion()

    if fetched_version != requested_version:
        raise RuntimeError('Could not fetch requested version')

    metadata = repo.metadata()

    return {"version": {"version": str(fetched_version)},
            "metadata": metadata}


def main():
    print(json.dumps(in_(sys.stdin, sys.argv[1])))


if __name__ == '__main__':
    main()
