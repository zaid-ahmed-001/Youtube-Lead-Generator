# Contributing to YouTube Lead Generator

First off, thank you for considering contributing to YouTube Lead Generator! It's people like you that make open-source such a great community.

## Development Setup

1. **Fork the repository** and clone it locally.
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```
3. **Install dependencies**:
   We recommend installing both standard and development dependencies.
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. **Environment Variables**:
   Copy `.env.example` to `.env` and configure your API keys (YouTube Data API v3 and Google Gemini AI).
5. **Code Style**:
   We enforce formatting using `black` and `isort`. Pre-commit hooks are configured to run automatically.
   ```bash
   pre-commit install
   ```

## Workflow

1. Create a branch for your feature or bug fix: `git checkout -b feature/your-feature-name`.
2. Write your code and tests (we use `pytest`). Ensure tests pass by running `pytest`.
3. Commit your changes.
4. Push to your fork and submit a Pull Request to the `main` branch.

## Pull Request Guidelines

- Ensure any install or build dependencies are removed before the end of the layer when doing a build.
- Update the README.md with details of changes to the interface.
- Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent.

Thank you!
