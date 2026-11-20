"""Docling converter configured for Russian and English OCR of scanned PDFs."""

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    HeadingHierarchyOptions,
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

OCR_LANGUAGES = ["rus", "eng"]


def create_document_converter() -> DocumentConverter:
    pdf_options = PdfPipelineOptions()
    pdf_options.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)
    pdf_options.generate_picture_images = True
    pdf_options.do_ocr = True
    pdf_options.ocr_options = TesseractCliOcrOptions(lang=OCR_LANGUAGES)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )
