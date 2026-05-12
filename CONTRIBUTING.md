# Contributing to GM AI Automation Tool

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to `gemini-manager`. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## 🛠️ Development Setup

1.  **Fork and Clone**
    ```bash
    git clone https://github.com/YOUR_USERNAME/gemini-manager.git
    cd gemini-manager
    ```

2.  **Set up a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    Install the package in editable mode with all dev dependencies:
    ```bash
    pip install -e .[dev]
    ```

## 🧪 Running Tests

We use `pytest` for testing. Ensure you run the full suite before submitting a PR.

```bash
# Run all tests
pytest tests/

# Run tests with coverage
pytest --cov=src/gemini_manager tests/
```

## 📐 Code Style

We strictly adhere to community standards to keep the codebase clean.

*   **Formatting**: We use [Black](https://github.com/psf/black).
*   **Linting**: We use [Ruff](https://github.com/astral-sh/ruff).

Run the formatters before committing:

```bash
black .
ruff check . --fix
```

## 🐛 Reporting Bugs

Bugs are tracked as GitHub issues. When filing an issue, please include:

*   Your operating system name and version.
*   Any details about your local setup that might be helpful in troubleshooting.
*   Detailed steps to reproduce the bug.

## 🚀 Pull Request Process

1.  Ensure any install or build dependencies are removed before the end of the layer when doing a build.
2.  Update the README.md with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations and container parameters.
3.  Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent.
4.  You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.
