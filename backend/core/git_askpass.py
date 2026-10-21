#!/usr/bin/env python3
import os
import sys

print("x-access-token" if "Username" in sys.argv[1] else os.environ["SPECHELPER_GITHUB_TOKEN"])
