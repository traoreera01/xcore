## 2025-05-14 - [Enhancing CLI with Rich]
**Learning:** Transitioning from plain text to `rich` components like Panels and Status spinners significantly improves the perceived responsiveness and readability of terminal interfaces without adding heavy overhead.
**Action:** Use `rich.console.Status` for network-bound CLI operations and `rich.panel.Panel` to group related metadata for better visual hierarchy.

## 2025-05-15 - [Structured CLI Data with Rich Tables]
**Learning:** For command outputs involving multiple entity attributes (like name, version, status), using structured tables with clear headers and semantic colors (e.g., green for OK, red for error) drastically reduces cognitive load compared to manual padding.
**Action:** Prefer `rich.table.Table` over custom string formatting for any CLI output that lists more than two related properties.

## 2026-03-25 - [Standardizing Interactive CLI Prompts]
**Learning:** Using `rich.prompt.Confirm.ask` instead of manual `input()` provides a more robust and accessible experience by handling various affirmative/negative responses and providing clear visual defaults, which reduces user error in destructive actions.
**Action:** Always prefer `rich.prompt` components for interactive CLI inputs to maintain consistency and improve usability.
