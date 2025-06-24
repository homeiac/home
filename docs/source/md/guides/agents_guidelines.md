# Agent Guidelines

This guide explains the expectations for contributions made with or by AI agents.

## Commit workflow

1. Open a GitHub issue describing the change.
2. Reference that issue in each commit message.
3. Keep the summary under 50 characters and include a detailed description after a blank line.

## Testing and quality

- Run `pytest` and generate coverage reports when Python files change.
- Check formatting with `black --check` and style with `flake8`.
- Ensure type hints pass `mypy`.
- All Markdown files should pass `markdownlint`.

Following these steps keeps the repository consistent and reliable.
