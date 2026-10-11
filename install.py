#!/usr/bin/env python3
"""Install from a checkout; the same installer is embedded in the one-file setup."""
import subprocess
import sys
from deploy.portable_install import main

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('Setup stopped: '+str(exc),file=sys.stderr);sys.exit(1)
