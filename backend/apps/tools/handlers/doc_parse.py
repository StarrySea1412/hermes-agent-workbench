"""Read text from an uploaded document for use inside agent runs."""

from apps.files.models import UploadedFile
from services.document_analyzer import DocumentAnalyzer

META = {
    "source": "builtin",
    "runtime": "full",
    "notes": "Reads uploaded files without relying on the model provider.",
}

SCHEMA = {
    "name": "doc_parse",
    "description": "Extract plain text from an uploaded PDF, DOCX, TXT, or Markdown file so the agent can inspect it.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "integer",
                "description": "Uploaded file ID that belongs to the current user.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum number of characters to return. Defaults to 6000.",
            },
        },
        "required": ["file_id"],
    },
}


def handle(args, context=None):
    file_id = args.get("file_id")
    if not file_id:
        return {"ok": False, "error": "Missing file_id."}
    max_chars = int(args.get("max_chars") or 6000)

    user_id = (context or {}).get("user_id")
    queryset = UploadedFile.objects.all()
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    try:
        uploaded = queryset.get(id=file_id)
    except UploadedFile.DoesNotExist:
        return {"ok": False, "error": f"File not found or not accessible: file_id={file_id}"}

    try:
        text = DocumentAnalyzer().extract_text(uploaded.file.path) or ""
    except Exception as exc:
        return {"ok": False, "error": f"Document parsing failed: {exc}"}

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return {
        "ok": True,
        "result": {
            "filename": uploaded.original_name,
            "text": text,
            "truncated": truncated,
        },
    }
