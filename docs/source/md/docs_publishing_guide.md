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
Subfolders under `docs/blog/` are included too; no manual index edit is needed.

## Verify locally

```bash
python -m pip install -r docs/requirements.txt
python -m unittest discover -s scripts/docs/tests -v
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

## What makes a deployment successful

The build produces `blog-publication.json`, recording the commit and SHA-256
digest of every rendered post, the blog index, and the home page. A copy is
saved separately as the expected publication manifest.

After GitHub Pages deploys, the workflow fetches the public manifest and every
listed HTML page. It requires the exact commit and file contents from this
build. Missing pages, stale content, HTTP errors, authentication failures, or a
failed Pages deployment make the workflow fail. Live checks retry briefly for
CDN propagation, with a ten-minute limit on the entire deployment job.

Regression tests exercise missing output, omitted navigation, stale pages,
HTTP failures, and automatic discovery of a newly added nested post using
a real Sphinx build. These tests run before every build, including pull requests.

Check the **Deploy Docs** run, not just the Pages action: its final live
verification step must pass. A failed run includes a publication-failure summary.
GitHub Actions notifications follow your GitHub notification preferences.
