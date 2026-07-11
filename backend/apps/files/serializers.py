from rest_framework import serializers

from apps.files.models import UploadedFile
from apps.files.validation import validate_uploaded_file


class UploadedFileSerializer(serializers.ModelSerializer):
    file_size_display = serializers.ReadOnlyField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = ['id', 'original_name', 'file_type', 'file_size', 'file_size_display', 'file_url', 'description', 'created_at']
        read_only_fields = ['id', 'original_name', 'file_type', 'file_size', 'created_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        if obj.file:
            return obj.file.url
        return None


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    description = serializers.CharField(max_length=500, required=False, default='')

    def validate_file(self, value):
        return validate_uploaded_file(value)
