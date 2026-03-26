## 2025-03-13 - Zip Slip Protection in Plugin Installation
**Vulnerability:** The plugin installation process was vulnerable to Zip Slip (directory traversal) because it extracted files from a ZIP archive without verifying that the resolved target paths remained within the intended destination directory.
**Learning:** Naive path concatenation using `Path` objects (`dest / member`) does not prevent traversal if the member name contains `..` components. Even if the first level is stripped, nested traversals can still occur.
**Prevention:** Always resolve the final path and check it against the destination using `target.resolve().is_relative_to(dest.resolve())`. This ensures that even with complex relative paths or symlinks, the file will not be written outside the sandbox.

## 2026-03-14 - Directory Traversal in Dotenv Injection
**Vulnerability:** The `ManifestValidator._inject_dotenv` method allowed loading `.env` files from outside the plugin directory via the `env_file` manifest parameter.
**Learning:** Even when using `Path` objects, concatenating a base directory with a user-provided relative path containing `..` can escape the intended directory if not explicitly validated after resolution.
**Prevention:** Always use `.resolve()` on the final path and verify it stays within the intended base directory using `.is_relative_to(base_dir.resolve())`.

## 2026-03-26 - Bypass of Static Security Scan via Built-in Functions
**Vulnerability:** The `ASTScanner` only checked for forbidden items during import operations (`import os`, `from os import ...`). Dangerous built-in functions like `eval()`, `exec()`, and `compile()` were included in the forbidden list but could still be called directly because the AST visitor did not inspect function call nodes.
**Learning:** Static analysis of module imports is insufficient to block built-in functions that are always available in the global namespace. A security-focused AST visitor must explicitly inspect `ast.Call` nodes.
**Prevention:** In the AST visitor, override `visit_Call` to check the function identifier against the forbidden list, ensuring that built-ins are blocked even when not explicitly imported.
