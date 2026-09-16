"""Tests for listing ingestion pipelines associated with a document."""

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.models.api.document.pipeline_response import PipelineResponse
from app.services.api.documents.pipelines import get_document_pipelines


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.row

    def scalars(self):
        return FakeScalars(self.rows)


class FakeSession:
    def __init__(self, document, pipelines):
        self.results = [FakeResult(row=document), FakeResult(rows=pipelines)]

    async def execute(self, _statement):
        return self.results.pop(0)


class TestDocumentPipelinesEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_returns_pipelines_for_document(self):
        document_id = uuid4()
        document = type("Document", (), {"id": document_id})()
        pipeline = type("Pipeline", (), {"document_id": document_id})()
        result = await get_document_pipelines(
            str(document_id), FakeSession(document, [pipeline])
        )

        self.assertEqual(result, [pipeline])

    def test_response_accepts_uuid_fields_from_database(self):
        document_id = uuid4()
        pipeline = type(
            "Pipeline",
            (),
            {
                "id": uuid4(),
                "document_id": document_id,
                "stage": "parsing",
                "status": "SUCCEEDED",
                "uploaded": True,
                "last_uploaded": None,
                "parsed": True,
                "last_parsed": None,
                "chunked": True,
                "last_chunked": None,
                "uploaded_at": None,
                "parsed_at": None,
                "chunked_at": None,
                "error_message": None,
                "error_stage": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )()

        response = PipelineResponse.model_validate(pipeline, from_attributes=True)

        self.assertEqual(response.id, pipeline.id)
        self.assertEqual(response.document_id, document_id)

    async def test_returns_empty_list_when_document_has_no_pipelines(self):
        document_id = uuid4()
        document = type("Document", (), {"id": document_id})()

        result = await get_document_pipelines(str(document_id), FakeSession(document, []))

        self.assertEqual(result, [])

    async def test_returns_404_when_document_does_not_exist(self):
        with self.assertRaises(HTTPException) as raised:
            await get_document_pipelines(str(uuid4()), FakeSession(None, []))

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Document not found")


if __name__ == "__main__":
    unittest.main()
