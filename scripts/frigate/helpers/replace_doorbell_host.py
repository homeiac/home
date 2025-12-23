#!/usr/bin/env python3
"""
Replace doorbell host in Frigate config.
Only modifies the go2rtc reolink_doorbell stream URL.
"""
import re
import sys

if len(sys.argv) != 3:
    print("Usage: replace_doorbell_host.py <config_file> <new_host>")
    sys.exit(1)

config_file = sys.argv[1]
new_host = sys.argv[2]

with open(config_file, 'r') as f:
    content = f.read()

# Match RTSP URL for doorbell camera (user 'frigate' with any password)
# Pattern captures: prefix (rtsp://frigate:PASS@) and suffix (:554/h264Preview)
# Only replaces the HOST portion between @ and :554
DOORBELL_USER = 'frigate'
pattern = rf'(rtsp://{DOORBELL_USER}:[^@]+@)[^:]+(:554/h264Preview)'
replacement = rf'\g<1>{new_host}\g<2>'

new_content = re.sub(pattern, replacement, content)

with open(config_file, 'w') as f:
    f.write(new_content)
