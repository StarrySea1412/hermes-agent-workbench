from pathlib import Path

from rest_framework import serializers

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "docx", "doc", "txt", "md", "xlsx"}


def detect_file_type(filename):
    ext = Path(filename or "").suffix.lower().lstrip(".")
    return {"pdf": "pdf", "md": "md", "docx": "docx", "doc": "doc", "txt": "txt", "xlsx": "xlsx"}.get(ext, "other")


def validate_uploaded_file(file_obj):
    size = getattr(file_obj, "size", None)
    if size is None:
        raise serializers.ValidationError("Unable to determine file size.")
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise serializers.ValidationError("File size must not exceed 50MB.")

    ext = Path(getattr(file_obj, "name", "")).suffix.lower().lstrip(".")
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise serializers.ValidationError(f"Unsupported file type: {ext or 'unknown'}")

    return file_obj
