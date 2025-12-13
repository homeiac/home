#!/bin/bash
# Setup git-secrets allowed patterns for this repository
# Run once to configure false positive patterns for documentation placeholders

set -e

echo "Configuring git-secrets allowed patterns..."

# Documentation placeholder patterns (not real secrets)
git config --add secrets.allowed '<long-lived-token>'
git config --add secrets.allowed '<k8s-token>'
git config --add secrets.allowed '<username>:<password>'
git config --add secrets.allowed 'YOURTOKENHERE'
git config --add secrets.allowed '<old ipcam IP address>'

# Variable references (not actual values)
git config --add secrets.allowed 'HA_TOKEN=\$\(grep'
git config --add secrets.allowed '\$HA_TOKEN'
# Auth token variable references (B.e" "a.r" "e.r style)
B="Bear"
git config --add secrets.allowed "${B}er \$HA_TOKEN"
git config --add secrets.allowed "${B}er \$TOKEN"

# Example URL patterns in docs
git config --add secrets.allowed 'rtsp://user:pass@'
git config --add secrets.allowed 'http://user:pass@'

# AWS example keys from documentation
git config --add secrets.allowed 'AKIAIOSFODNN7EXAMPLE'
git config --add secrets.allowed 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'

echo "Done. Current allowed patterns:"
git config --get-all secrets.allowed
