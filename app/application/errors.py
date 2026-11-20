"""Application-level exceptions translated by inbound adapters (HTTP, CLI, jobs)."""


class ApplicationError(Exception):
    """Base class for expected application failures."""


class DocumentNotFoundError(ApplicationError):
    """The requested document does not exist."""


class NodeNotFoundError(ApplicationError):
    """The requested node does not exist or cannot be rendered."""


class NoActivePipelineError(ApplicationError):
    """A rerun without force was requested but no pipeline is running."""


class ConcurrencyConflictError(ApplicationError):
    """A concurrent writer changed the same data; the operation can be retried."""


class StorageError(ApplicationError):
    """A file could not be staged, moved, or verified."""


class EmptyStageResultError(ApplicationError):
    """A stage has nothing to work on or produced nothing."""


class StageJobError(ApplicationError):
    """A pipeline stage job failed; the pipeline has been marked failed."""


class AnswerGenerationError(ApplicationError):
    """The chat model did not return a usable answer."""


class LawImportError(ApplicationError):
    """A law document could not be fetched or parsed."""
