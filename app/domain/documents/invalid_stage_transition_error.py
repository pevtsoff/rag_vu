"""Raised when a pipeline is asked to complete a stage it is not running."""


class InvalidStageTransitionError(RuntimeError):
    """A pipeline state change that violates the stage order."""
