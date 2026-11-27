# Docs Publishing Guide

The [Deploy Docs workflow](https://github.com/homeiac/home/actions/workflows/docs.yml)
builds Sphinx documentation on pushes to `master` and deploys its HTML artifact
directly to [GitHub Pages](https://homeiac.github.io/home/). Repository Settings →
Pages → Build and deployment → Source must be **GitHub Actions**.

## Add a blog post

Write a Markdown file in `docs/blog/`, preferably named `YYYY-MM-DD-title.md`,
with a level-one heading for its title. `docs/source/blog` is a Git symlink to
that directory, so Sphinx reads the original posts without a copying step.
The [blog index](../blog.rst) automatically includes those posts and the older
`docs/source/md/blog-*.md` posts. Existing post URLs are preserved.

## Verify locally

```bash
python -m pip install -r docs/requirements.txt
make -C docs html
python scripts/docs/check-blog-build.py
```

The verifier checks every post has HTML output and a link from the blog index,
the home page links to the blog, and `.nojekyll` exists. Sphinx creates
`.nojekyll` through its `githubpages` extension. Pull requests run the same
build and verification without deploying.

## Publish

Merge the source changes into `master`. The workflow deploys `docs/build/html`
using the official GitHub Pages actions; generated HTML is not committed.
For a manual deployment, use **Run workflow** on **Deploy Docs**, selecting
`master`. Wait for both the build and deploy jobs to succeed, then open the
[published blog](https://homeiac.github.io/home/blog.html).
