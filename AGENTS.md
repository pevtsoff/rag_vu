# Python coding standards

- Keep every import at module scope. Never place imports inside functions or methods, including to work around optional dependencies or import cycles. Resolve dependencies at module scope; use `TYPE_CHECKING` for type-only imports.
- Keep each function and method to 30 lines or fewer. Split longer implementations into small, intention-revealing helpers. Prefer functions as comments: helper names should communicate the steps and make comments that merely narrate code unnecessary.
- Put each class in its own `.py` file. Name the file after the primary class using `snake_case`.
- Add type annotations to function and method parameters and return values, especially for public interfaces.
- Follow PEP 8 naming: `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- Keep comments focused on why a non-obvious decision exists; use docstrings for public modules, classes, and functions where they add useful context.
- Raise specific exceptions and preserve useful error context. Do not catch and silently discard errors.
- Follow the repository's Ruff configuration for imports, linting, and formatting (100-character line length; double quotes).
