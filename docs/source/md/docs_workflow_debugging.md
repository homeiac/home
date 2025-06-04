# Documentation Workflow Debugging

This guide explains how to build the Sphinx documentation locally and test the GitHub Pages deployment workflow using `act`.

## Building docs locally

```bash
cd docs
make html
```

Open `docs/build/html/index.html` in your browser to view the generated documentation.

## Testing the workflow

Install [`act`](https://github.com/nektos/act) and run:

```bash
act -j build
```

This will execute the `build` job from `.github/workflows/docs.yml` using a local runner.
