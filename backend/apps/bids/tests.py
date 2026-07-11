from io import BytesIO

from django.test import override_settings
from docx import Document
from rest_framework.test import APIClient, APITestCase

from apps.bids.models import Bid, BidChapter, BidStep
from apps.users.authentication import create_access_token
from apps.users.models import User
from services.text_utils import text_to_canvas_format


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class BidSecurityTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.other_user = User.objects.create_user(username='other', password='password123')
        self.owner_client = self._make_client(self.owner)
        self.other_client = self._make_client(self.other_user)
        self.bid = Bid.objects.create(title='Owner Bid', user=self.owner, total_chapters=1)
        self.chapter = BidChapter.objects.create(bid=self.bid, title='Chapter 1', order=0)
        self.step = BidStep.objects.create(bid=self.bid, order=0, label='Step', status='pending')

    def _make_client(self, user):
        client = APIClient()
        token = create_access_token(user.id)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    def test_bid_list_and_detail_are_scoped_to_authenticated_user(self):
        response = self.other_client.get('/api/bids')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        detail_response = self.other_client.get(f'/api/bids/{self.bid.id}')
        self.assertEqual(detail_response.status_code, 404)

    def test_bid_creation_ignores_supplied_user_id(self):
        response = self.other_client.post('/api/bids', {'title': 'New Bid', 'user_id': self.owner.id}, format='json')

        self.assertEqual(response.status_code, 201)
        created_bid = Bid.objects.get(id=response.json()['id'])
        self.assertEqual(created_bid.user_id, self.other_user.id)

    def test_bid_creation_seeds_clean_default_blueprint_content(self):
        response = self.owner_client.post('/api/bids', {'title': 'Workflow Sample'}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['title'], 'Workflow Sample')
        self.assertEqual(response.json()['steps'][0]['label'], '分析源资料')
        self.assertEqual(response.json()['chapters'][0]['title'], '项目概述')
        self.assertEqual(len(response.json()['chapters']), 5)

    def test_deleting_top_level_chapter_decrements_total_chapters(self):
        response = self.owner_client.post('/api/bids', {'title': 'Mutable Bid'}, format='json')
        self.assertEqual(response.status_code, 201)

        bid_id = response.json()['id']
        chapter_id = response.json()['chapters'][0]['id']

        delete_response = self.owner_client.delete(f'/api/bids/{bid_id}/chapters/{chapter_id}')
        self.assertEqual(delete_response.status_code, 204)

        detail_response = self.owner_client.get(f'/api/bids/{bid_id}')
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()['total_chapters'], 4)
        self.assertEqual(len(detail_response.json()['chapters']), 4)

    def test_bid_analyzer_rejects_direct_server_file_paths(self):
        response = self.owner_client.post('/api/bid-analyzer/analyze', {'file_path': 'C:\\secret.txt'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('file_path', response.json()['message'])

    def test_export_bid_includes_canvas_content_generated_from_markdown(self):
        self.chapter.content = text_to_canvas_format("# Delivery Plan\n\n- Phase 1\n- Phase 2\n\nExecution details.")
        self.chapter.save(update_fields=['content', 'updated_at'])

        response = self.owner_client.post(f'/api/bids/{self.bid.id}/export')

        self.assertEqual(response.status_code, 200)
        payload = b''.join(response.streaming_content)
        document = Document(BytesIO(payload))
        body_text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())

        self.assertIn('Owner Bid', body_text)
        self.assertIn('Chapter 1', body_text)
        self.assertIn('Delivery Plan', body_text)
        self.assertIn('Phase 1', body_text)
        self.assertIn('Execution details.', body_text)
