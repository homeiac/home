# Docs Build Guide

To verify documentation builds correctly before pushing changes, install the documentation dependencies and run the Sphinx build locally:

```bash
pip install -r docs/requirements.txt
make -C docs html
```

The generated HTML will be placed in `docs/build/html`.
