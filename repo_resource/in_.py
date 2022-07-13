#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>

import json
import sys


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
    version = payload['version']['sha256']

    return {"version": {"sha256": version}}


def main():
    print(json.dumps(in_(sys.stdin, sys.argv[1])))


if __name__ == '__main__':
    main()
