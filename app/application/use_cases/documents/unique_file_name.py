"""A free file name for an upload that must not be confused with an existing document."""

from pathlib import PurePosixPath

from app.application.ports.unit_of_work import UnitOfWork

FIRST_SUFFIX = 2


async def unique_file_name(uow: UnitOfWork, file_name: str) -> str:
    """``law.pdf`` stays as is when free, otherwise becomes ``law_2.pdf``, ``law_3.pdf``, …"""
    if not await uow.documents.exists_with_file_name(file_name):
        return file_name
    path = PurePosixPath(file_name)
    number = FIRST_SUFFIX
    while await uow.documents.exists_with_file_name(f"{path.stem}_{number}{path.suffix}"):
        number += 1
    return f"{path.stem}_{number}{path.suffix}"
