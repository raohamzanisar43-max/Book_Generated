"""Status values used across the workflow.

Plain string constants keep the stored values identical to the original schema, so
existing rows remain valid and comparisons against database values are exact.
"""
from typing import Literal


class OutlineStatus:
    PENDING = "pending"
    GENERATING = "generating"
    REVIEW_NEEDED = "review_needed"
    APPROVED = "approved"


class ChapterStatus:
    PENDING = "pending"
    GENERATING = "generating"  # being written by a background job
    REVIEW_NEEDED = "review_needed"
    APPROVED = "approved"
    FAILED = "failed"  # background job failed; can be retried


class NotesStatus:
    """Editor decision used for outline, chapter and final review gates.

    yes             -> editor supplied notes; regenerate (outline/chapter) or pause (final)
    no              -> no decision yet; workflow stays paused
    no_notes_needed -> approved; workflow continues
    """

    YES = "yes"
    NO = "no"
    NO_NOTES_NEEDED = "no_notes_needed"


NotesStatusValue = Literal["yes", "no", "no_notes_needed"]


class BookOutputStatus:
    IN_PROGRESS = "in_progress"
    READY = "ready"
    COMPILED = "compiled"


class LogLevel:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
