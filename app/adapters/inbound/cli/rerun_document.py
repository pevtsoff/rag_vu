"""Restart a document's pipeline from a stage (replaces the old manual chunking script).

``python -m app.adapters.inbound.cli.rerun_document DOCUMENT_ID --stage chunking``
"""

import argparse
import asyncio
from uuid import UUID

from app.application.use_cases.documents.rerun_pipeline import RerunPipeline
from app.bootstrap.infrastructure import Infrastructure
from app.config.app_settings import get_settings
from app.domain.documents.pipeline_stage import PipelineStage


async def main(document_id: UUID, stage: PipelineStage) -> None:
    infrastructure = Infrastructure(get_settings())
    try:
        pipeline = await RerunPipeline(infrastructure.unit_of_work).execute(
            document_id, stage, force_run=True
        )
    finally:
        await infrastructure.dispose()
    print(f"Pipeline {pipeline.id} started at {stage} for document {document_id}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_id", type=UUID)
    parser.add_argument(
        "--stage", type=PipelineStage, choices=list(PipelineStage), default=PipelineStage.CHUNKING
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    asyncio.run(main(arguments.document_id, arguments.stage))
