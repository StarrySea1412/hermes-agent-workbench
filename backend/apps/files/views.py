from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import threading

from django.db import connections

from apps.files.models import UploadedFile
from apps.files.serializers import FileUploadSerializer, UploadedFileSerializer
from apps.files.validation import detect_file_type


def _index_file_async(file_id):
    """后台线程建索引：上传立即返回，索引完资料页状态自然变 indexed。"""
    from services.rag_service import index_uploaded_file

    def _run():
        try:
            uploaded = UploadedFile.objects.select_related("user").get(id=file_id)
            index_uploaded_file(uploaded)
        finally:
            connections.close_all()

    threading.Thread(target=_run, daemon=True).start()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_files(request):
    files = UploadedFile.objects.filter(user=request.user)
    serializer = UploadedFileSerializer(files, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_file(request):
    serializer = FileUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    file_obj = serializer.validated_data["file"]
    uploaded = UploadedFile.objects.create(
        user=request.user,
        file=file_obj,
        original_name=file_obj.name,
        file_type=detect_file_type(file_obj.name),
        file_size=file_obj.size,
        description=serializer.validated_data.get("description", ""),
    )

    result = UploadedFileSerializer(uploaded, context={"request": request})
    _index_file_async(uploaded.id)
    return Response(result.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reindex_file(request, file_id):
    """索引丢失或 embedding 模型更换后手动重建。"""
    try:
        uploaded = UploadedFile.objects.get(id=file_id, user=request.user)
    except UploadedFile.DoesNotExist:
        return Response({"message": "文件不存在。"}, status=status.HTTP_404_NOT_FOUND)

    _index_file_async(uploaded.id)
    return Response({"ok": True, "message": "已重新加入索引队列。"})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_file(request, file_id):
    try:
        uploaded = UploadedFile.objects.get(id=file_id, user=request.user)
    except UploadedFile.DoesNotExist:
        return Response({"message": "文件不存在。"}, status=status.HTTP_404_NOT_FOUND)

    uploaded.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
