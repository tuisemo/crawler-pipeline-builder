# Environment

Environment variables, external dependencies, and setup notes.

- Existing `.env` may provide LLM configuration for crawler generation.
- If LLM config is unavailable, generation paths should expose degraded-mode behavior while authoring/testing stays usable.
- No additional database or queue is required for MVP.
