# Docs Symlink Guide

This repository uses symbolic links in `docs/source/md` to include Markdown files from other directories in the Sphinx build.

The `guides` subfolder contains links to files under `proxmox/guides`. If any links break, recreate them using `ln -sf <source> <destination>`.

