"""Generated script formatting and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..workflow_schemas import FormatScriptRequest, FormatScriptResponse, SaveScriptRequest, SaveScriptResponse


@dataclass
class ScriptFormattingError(Exception):
    error: str

    def __str__(self):
        return self.error


@dataclass
class ScriptPersistenceError(Exception):
    error_code: str
    error: str

    def __str__(self):
        return f"{self.error_code}: {self.error}"


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _normalize_script_text(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.rstrip().replace("\t", "    ") for line in normalized.split("\n")]
    compacted = "\n".join(normalized_lines).strip("\n")
    return f"{compacted}\n" if compacted else ""


def _resolve_workspace_path(relative_path: str) -> Path:
    candidate = (relative_path or "").strip().replace("\\", "/")
    if not candidate:
        raise ScriptPersistenceError(
            error_code="relative_path_required",
            error="A non-empty relative_path is required to save a script.",
        )
    raw_path = Path(candidate)
    if raw_path.is_absolute():
        raise ScriptPersistenceError(
            error_code="absolute_path_not_allowed",
            error="Scripts must be saved using a path relative to the project root.",
        )

    target = (WORKSPACE_ROOT / raw_path).resolve()
    try:
        target.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ScriptPersistenceError(
            error_code="path_outside_workspace",
            error="The requested relative_path resolves outside the project workspace.",
        ) from exc
    return target


def format_script(request: FormatScriptRequest) -> FormatScriptResponse:
    """Format generated script text for easier editing and saving."""
    content = request.content or ""
    if not content.strip():
        raise ScriptFormattingError("Script content is required for formatting.")

    normalized = _normalize_script_text(content)
    warnings: list[str] = []
    formatter = "basic"

    if request.language.strip().lower() == "python":
        try:
            import black  # type: ignore

            normalized = black.format_str(normalized, mode=black.FileMode())
            formatter = "black"
        except ImportError:
            warnings.append("Black is not installed; applied whitespace-only normalization.")
        except Exception as exc:
            warnings.append(f"Black could not format this script; kept normalized text ({exc}).")

    return FormatScriptResponse(
        success=True,
        formatted_content=normalized,
        changed=normalized != content,
        formatter=formatter,
        warnings=warnings,
    )


def save_script(request: SaveScriptRequest) -> SaveScriptResponse:
    """Persist edited script text inside the repository workspace."""
    content = request.content or ""
    if not content.strip():
        raise ScriptPersistenceError(
            error_code="script_content_required",
            error="Script content is required before saving to a project file.",
        )

    target_path = _resolve_workspace_path(request.relative_path)
    existed_before = target_path.exists()
    if existed_before and not request.overwrite:
        raise ScriptPersistenceError(
            error_code="target_exists",
            error="Target file already exists. Enable overwrite to replace it.",
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_script_text(content)
    target_path.write_text(normalized, encoding="utf-8")

    relative = target_path.relative_to(WORKSPACE_ROOT).as_posix()
    return SaveScriptResponse(
        success=True,
        relative_path=relative,
        absolute_path=str(target_path),
        bytes_written=len(normalized.encode("utf-8")),
        created=not existed_before,
        overwritten=existed_before,
    )
