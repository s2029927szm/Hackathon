# Repository Guidelines

## Project Structure & Module Organization

- `FoodCompass-Web/` contains the standalone browser demo: `index.html`, `app.js` (state, views, interactions), `enhancements.js` (V2 overrides), `style.css`, and `assets/` (images). Keep their relative paths intact and load `app.js` before `enhancements.js`.
- `app(1).py` implements the separate FastAPI recommendation and live-monitor prototype. `index(1).html` and `monitor(1).html` are its browser clients.
- `generate_dishes.py` generates `dishes_50.json`, the backend's 50-dish dataset. The standalone demo maintains separate sample data.
- `FoodCompass-Web/使用说明.txt` describes demo behavior and manual acceptance checks. No tests directory or dependency manifest currently exists.

## Build, Test, and Development Commands

Run commands from the repository root in PowerShell. No frontend build step is required.

- `python -m http.server 8000 --bind 127.0.0.1 --directory FoodCompass-Web` serves the standalone demo locally; open `http://127.0.0.1:8000`.
- `node --check FoodCompass-Web/app.js` and `node --check FoodCompass-Web/enhancements.js` check JavaScript syntax.
- `python -m py_compile "app(1).py" generate_dishes.py` checks Python syntax.
- `python generate_dishes.py` regenerates and overwrites the dish dataset; review resulting changes.
- In a virtual environment, `python -m pip install fastapi uvicorn openai` installs backend dependencies. Start with `python -m uvicorn "app(1):app" --reload --port 8001`.

Before using backend pages, reconcile their filenames: routes currently open `index.html` and `monitor.html`, but supplied files have `(1)` suffixes. Model calls require the configured OpenAI-compatible endpoint at `localhost:11434/v1` and model `gemma4:31b`.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions; retain existing type annotations. JavaScript uses plain scripts, camelCase identifiers, and single-quoted strings. Use two-space indentation for new multiline JavaScript. Preserve `data-action` handlers and kebab-case CSS classes. Avoid unrelated reformatting of compact files. No formatter or linter is configured.

## Testing Guidelines

No automated framework or coverage threshold is configured. Use `?qa` for frontend checks without reading or writing saved preferences. Verify onboarding, selection dialogs, swipe/Undo, solo/group wheels, responsive layouts, and console errors. Check persistence separately without `?qa`. Backend changes should exercise affected API routes and monitor updates; record model-service prerequisites.

## Commit & Pull Request Guidelines

This checkout has no Git metadata, so commit conventions cannot be inferred. Use concise imperative subjects, such as `Fix swipe undo state`. PRs should describe scope, validation, known limitations, and related issues when applicable; include screenshots for UI changes. Keep simulated multiplayer and sample nutrition data clearly identified as demo features.
