# Documentation Workflow Guide

This guide describes how the documentation is built and deployed.

Documentation is deployed automatically when changes are pushed to `master`. The
`.github/workflows/deploy_to_github.yml` workflow uses the
`JacksonMaxfield/github-pages-deploy-action-python` action to build the docs and
publish the contents of `docs/build/html` to the `gh-pages` branch.

