from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.files.models import UploadedFile
from apps.files.serializers import FileUploadSerializer, UploadedFileSerializer
from apps.files.validation import detect_file_type


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
    return Response(result.data, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_file(request, file_id):
    try:
        uploaded = UploadedFile.objects.get(id=file_id, user=request.user)
    except UploadedFile.DoesNotExist:
        return Response({"message": "文件不存在。"}, status=status.HTTP_404_NOT_FOUND)

    uploaded.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
