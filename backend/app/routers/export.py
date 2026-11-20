from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..deps import require_user
from ..schemas import ExportRequest
from ..services.segmenter import split_paragraphs

router = APIRouter(prefix="/api", tags=["export"])

MEDIA_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("/export")
def export_document(payload: ExportRequest, _: object = Depends(require_user)):
    fmt = payload.format
    filename = payload.filename or "rewritten"

    if fmt == "docx":
        from docx import Document

        doc = Document()
        for paragraph in split_paragraphs(payload.text):
            doc.add_paragraph(paragraph)
        buffer = BytesIO()
        doc.save(buffer)
        content = buffer.getvalue()
    else:
        content = payload.text.encode("utf-8")

    encoded_name = quote(f"{filename}.{fmt}")
    return Response(
        content=content,
        media_type=MEDIA_TYPES.get(fmt, "application/octet-stream"),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        },
    )
