import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.files.models import UploadedFile
from apps.users.authentication import create_access_token
from apps.users.models import User


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY="test-jwt-secret-key-with-32-bytes!!",
)
class FileApiTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.user = User.objects.create_user(username="file-owner", password="password123")
        self.other_user = User.objects.create_user(username="file-other", password="password123")
        self.client = self._make_client(self.user)
        self.other_client = self._make_client(self.other_user)

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def _make_client(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user.id)}")
        return client

    def test_upload_list_and_delete_file(self):
        upload_response = self.client.post(
            "/api/files/upload",
            {
                "file": SimpleUploadedFile("runbook.md", b"# Runbook\ncontent", content_type="text/markdown"),
                "description": "Deployment checklist",
            },
            format="multipart",
        )

        self.assertEqual(upload_response.status_code, 201)
        file_id = upload_response.data["id"]
        self.assertEqual(upload_response.data["file_type"], "md")
        self.assertEqual(upload_response.data["description"], "Deployment checklist")

        list_response = self.client.get("/api/files")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["id"], file_id)

        delete_response = self.client.delete(f"/api/files/{file_id}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(UploadedFile.objects.filter(id=file_id).exists())

    def test_file_endpoints_are_scoped_to_owner(self):
        owned_file = UploadedFile.objects.create(
            user=self.user,
            file=SimpleUploadedFile("owner-notes.txt", b"owner file", content_type="text/plain"),
            original_name="owner-notes.txt",
            file_type="txt",
            file_size=10,
        )
        UploadedFile.objects.create(
            user=self.other_user,
            file=SimpleUploadedFile("other-notes.txt", b"other file", content_type="text/plain"),
            original_name="other-notes.txt",
            file_type="txt",
            file_size=10,
        )

        list_response = self.client.get("/api/files")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.data], [owned_file.id])

        delete_response = self.other_client.delete(f"/api/files/{owned_file.id}")
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(UploadedFile.objects.filter(id=owned_file.id).exists())
