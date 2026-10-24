"""Domain exceptions. Each one becomes a specific HTTP status in a router."""

# Shown to the caller for any failure that isn't one of the domain
# exceptions below — deliberately fixed and generic. The exception message
# itself is never safe to forward: it can carry a stack of internal detail
# (file paths, driver errors, arbitrary repr() output) that was never meant
# to reach a client. The real detail still reaches the server-side log,
# via logger.exception(...) at the point this message is used.
GENERIC_ERROR_MESSAGE = "internal error"


class TranscriptionFailedError(Exception):
    """The transcription vendor reported a definite failure."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Transcription failed: {reason}")


class SummarizationFailedError(Exception):
    """The summarization vendor failed or returned an empty response."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Summarization failed: {reason}")


class BriefingFailedError(Exception):
    """Briefing synthesis failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Briefing synthesis failed: {reason}")


class PromptNotFoundError(Exception):
    """A prompt template file could not be located on disk."""

    def __init__(self, prompt_path: str) -> None:
        self.prompt_path = prompt_path
        super().__init__(f"Prompt file not found: {prompt_path}")
