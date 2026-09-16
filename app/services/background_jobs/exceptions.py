class FileStageError(Exception):
    """Base class for a document ingestion stage failure."""


class FileUploadError(FileStageError):
    pass


class FileParsingError(FileStageError):
    pass


class FileChunkingError(FileStageError):
    pass
