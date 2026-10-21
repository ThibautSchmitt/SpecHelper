#!/usr/bin/env python3
"""Browser launcher used only by the official login commands."""

import os
import sys
from pathlib import Path

target = Path(os.environ["SPECHELPER_LOGIN_URL_FILE"])
target.write_text(sys.argv[-1])
