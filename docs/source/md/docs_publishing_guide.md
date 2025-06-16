# Docs Publishing Guide

This guide explains how the project publishes its documentation to the `gh-pages` branch. The GitHub Actions workflow defined in `.github/workflows/deploy_to_github.yml` builds the documentation from the `docs` folder whenever changes are pushed to `master`. The generated HTML is then committed to the `gh-pages` branch and served via GitHub Pages at [https://homeiac.github.io/home/](https://homeiac.github.io/home/).

To trigger a deployment manually, run:

```bash
make -C docs html
```

Then commit the changes under `docs/build/html` and push them to the `gh-pages` branch. Ensure the `.nojekyll` file exists in the root of `docs/build/html` so GitHub Pages serves the files correctly.

