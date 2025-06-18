# Python Tests Guide

This guide explains how to run the unit tests for the automation code.

## Running Tests

From the repository root run:

```bash
pytest proxmox/homelab/tests
```

The tests rely on the optional development dependencies listed in
`proxmox/homelab/pyproject.toml`. If they are not installed, use:

```bash
pip install -r docs/requirements.txt
pip install pytest
```

The suite covers core modules used to automate VM creation on Proxmox.
