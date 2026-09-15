from rest_framework import serializers

from apps.files.models import UploadedFile
from apps.files.validation import validate_uploaded_file


class UploadedFileSerializer(serializers.ModelSerializer):
    file_size_display = serializers.ReadOnlyField()
    file_url = serializers.SerializerMethodField()
    index_status = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = ['id', 'original_name', 'file_type', 'file_size', 'file_size_display', 'file_url', 'description', 'index_status', 'chunk_count', 'created_at']
        read_only_fields = ['id', 'original_name', 'file_type', 'file_size', 'created_at']

    def get_index_status(self, obj):
        chunk_count = self._chunk_count(obj)
        return 'indexed' if chunk_count > 0 else 'pending'

    def get_chunk_count(self, obj):
        return self._chunk_count(obj)

    def _chunk_count(self, obj):
        if not hasattr(obj, '_cached_chunk_count'):
            obj._cached_chunk_count = obj.chunks.count()
        return obj._cached_chunk_count

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
