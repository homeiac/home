# Documentation Workflow Guide

Documentation is deployed automatically when documentation, publishing scripts,
or `.github/workflows/docs.yml` changes are pushed to `master`.

The workflow installs `docs/requirements.txt`, runs `make -C docs html`, and
verifies that all blog posts appear in the rendered site and blog index.
It uploads `docs/build/html` with `actions/upload-pages-artifact` and publishes
it with `actions/deploy-pages`. Pull requests build and verify without deploying.

Posts in `docs/blog/` are included through the `docs/source/blog` symlink.
The blog index also includes the existing `docs/source/md/blog-*.md` posts.
No generated HTML commits or separate publishing branch are needed.

See the [publishing guide](docs_publishing_guide.md) for local checks and manual
deployment instructions.
