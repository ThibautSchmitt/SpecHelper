#!/usr/bin/env python3
"""Provide a single fetch process with its isolated source credential."""

import os
import sys

print(
    os.environ.get("SPECHELPER_GIT_USERNAME", "x-access-token")
    if "Username" in sys.argv[1]
    else os.environ.get("SPECHELPER_GIT_TOKEN", os.environ.get("SPECHELPER_GITHUB_TOKEN", ""))
)
