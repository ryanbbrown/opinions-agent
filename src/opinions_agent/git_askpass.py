#!/usr/bin/env python3
"""Noninteractive git askpass helper. The token stays in the process environment."""

from __future__ import annotations

import os
import sys

prompt = sys.argv[1] if len(sys.argv) > 1 else ""
print("x-access-token" if "Username" in prompt else os.environ.get("OPINIONS_GIT_TOKEN", ""))
