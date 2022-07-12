#!/usr/bin/env python

# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 (c) BayLibre, SAS
# Author: Mattijs Korpershoek <mkorpershoek@baylibre.com>
"""
Common functions for Android repo resource
"""
import hashlib

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
