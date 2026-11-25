#!/usr/bin/env python3
# FPP Command script for "Dynamic_RDS Transmitter State", registered from commands/descriptions.json.
# FPP runs it with the Action arg as argv[1] and replaces the whole environment with only
# MEDIADIR, FPPDIR, and SCRIPTDIR, so the normal paths are restored before handing off to
# callbacks.py - an engine launched from here inherits this environment.

import os
import sys

actions = {'Start': '--start', 'Stop': '--stop'}
action = sys.argv[1] if len(sys.argv) > 1 else ''
if action not in actions:
  print(f'Unknown action \'{action}\' - expected Start or Stop', file=sys.stderr)
  sys.exit(1)

mediaDir = os.environ.get('MEDIADIR', '/home/fpp/media')
os.environ.setdefault('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
os.environ.setdefault('LOGDIR', os.path.join(mediaDir, 'logs'))
os.environ.setdefault('CFGDIR', os.path.join(mediaDir, 'config'))

callbacks = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'callbacks.py')
# Not sys.executable - with no PATH at startup, Python can't resolve its own path and leaves it empty
os.execvp('python3', ['python3', callbacks, actions[action]])
