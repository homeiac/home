# Agents Guidelines

This repository uses AI agents to maintain infrastructure-as-code. Follow these rules when contributing:

## Commit Messages

- Open a GitHub issue for each change and reference it in every commit.
- Start with a short summary (under 50 characters).
- Add a blank line followed by a detailed explanation.

## Testing

- Only run tests when Python files are modified.
- Execute `pytest` from the repository root.
- Measure coverage with `coverage run -m pytest` and generate reports using `coverage html`.
- Validate types with `mypy`.
- Check style with `flake8` and ensure formatting with `black --check`.

## Markdown

- Ensure all Markdown files pass `markdownlint` before committing.

## Pull Requests

- Keep pull requests focused and reference the related GitHub issue.
- All checks must pass before merging.
