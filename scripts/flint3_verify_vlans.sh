#!/bin/sh
# Show VLAN1 and VLAN40 configuration
set -eu
swconfig dev switch1 show | sed -n '/VLAN 1/,+3p;/VLAN 40/,+3p'
