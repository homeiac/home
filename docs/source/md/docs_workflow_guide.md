# Documentation Workflow Guide

This guide describes how the documentation is built and deployed.

The `.github/workflows/docs.yml` workflow installs Sphinx, builds the docs, and deploys the `docs/build/html` directory to GitHub Pages using the official `configure-pages`, `upload-pages-artifact`, and `deploy-pages` actions.

