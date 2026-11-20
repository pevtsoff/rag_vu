from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base whose metadata Alembic compares against."""
