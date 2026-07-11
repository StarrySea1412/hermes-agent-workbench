from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from apps.ai_config.models import AIConfig, GenerationTask
from apps.bids.models import Bid, BidChapter
from apps.users.authentication import create_access_token
from apps.users.models import User
from services import encryption_service
from services.encryption_service import get_encryption
from services.model_fetch_service import ModelFetchError, build_model_endpoint_candidates, fetch_model_list


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class ModelFetchServiceTests(SimpleTestCase):
    def test_builds_compatible_models_candidates(self):
        candidates = build_model_endpoint_candidates(
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        )

        self.assertEqual(
            candidates,
            [
                'https://dashscope.aliyuncs.com/compatible-mode/v1/models',
                'https://dashscope.aliyuncs.com/v1/models',
                'https://dashscope.aliyuncs.com/models',
            ],
        )

    def test_derives_models_endpoint_from_full_url(self):
        candidates = build_model_endpoint_candidates(
            base_url='https://api.example.com/v1/chat/completions',
            is_full_url=True,
        )

        self.assertEqual(candidates, ['https://api.example.com/v1/models'])

    @patch('services.model_fetch_service.urlopen')
    def test_fetch_model_list_parses_and_sorts_openai_style_response(self, mock_urlopen):
        mock_urlopen.return_value = _FakeResponse(
            b'{"data":[{"id":"zeta","owned_by":"team"},{"id":"alpha"}]}'
        )

        result = fetch_model_list(base_url='https://api.example.com/v1', api_key='sk-test')

        self.assertEqual(result['endpoint'], 'https://api.example.com/v1/models')
        self.assertEqual(result['models'], [{'id': 'alpha'}, {'id': 'zeta', 'owned_by': 'team'}])
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.example.com/v1/models')
        self.assertEqual(request.headers['Authorization'], 'Bearer sk-test')


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class GenerationTaskSecurityTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.other_user = User.objects.create_user(username='other', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.other_user.id)}')
        self.bid = Bid.objects.create(title='Owner Bid', user=self.owner, total_chapters=1)
        self.chapter = BidChapter.objects.create(bid=self.bid, title='Secret Chapter', order=0)

    def test_generate_chapter_cannot_target_another_users_chapter(self):
        response = self.client.post(
            '/api/ai-generate/chapter',
            {'chapter_id': self.chapter.id, 'mode': 'fast'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(GenerationTask.objects.count(), 0)


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class HermesSkillApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')
        self.bid = Bid.objects.create(title='Bid', user=self.user, total_chapters=1)
        self.chapter = BidChapter.objects.create(bid=self.bid, title='Implementation Plan', order=0)

    def test_list_hermes_skills(self):
        response = self.client.get('/api/hermes/skills')

        self.assertEqual(response.status_code, 200)
        self.assertIn('skills', response.data)
        self.assertTrue(
            any(skill['path'] == 'bid-writing/bid-chapter-writer' for skill in response.data['skills'])
        )

    def test_get_hermes_skill_detail(self):
        response = self.client.get('/api/hermes/skills/agent-engineering/general-operator')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['path'], 'agent-engineering/general-operator')
        self.assertIn('General Operator', response.data['title'])
        self.assertIn('body', response.data)
        self.assertTrue(response.data['body'])
        self.assertIn('metadata', response.data)

    def test_get_hermes_skill_detail_returns_404_for_unknown_skill(self):
        response = self.client.get('/api/hermes/skills/manual/not-found')

        self.assertEqual(response.status_code, 404)

    def test_generate_chapter_rejects_unknown_hermes_skill(self):
        response = self.client.post(
            '/api/ai-generate/chapter',
            {
                'chapter_id': self.chapter.id,
                'mode': 'hermes',
                'skill': 'manual/not-found',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(GenerationTask.objects.count(), 0)

    @patch('apps.ai_config.tasks.generate_chapter_task.delay', return_value=SimpleNamespace(id='task-1'))
    @patch('services.hermes_service.create_hermes_service', return_value=object())
    def test_generate_chapter_persists_requested_skill(self, _mock_hermes, _mock_delay):
        response = self.client.post(
            '/api/ai-generate/chapter',
            {
                'chapter_id': self.chapter.id,
                'mode': 'hermes',
                'skill': 'bid-writing/bid-chapter-writer',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 202)
        task = GenerationTask.objects.get()
        self.assertEqual(task.skill, 'bid-writing/bid-chapter-writer')
        self.assertEqual(response.data['skill'], 'bid-writing/bid-chapter-writer')


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
    AI_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode(),
)
class AIModelListApiTests(APITestCase):
    def setUp(self):
        encryption_service._encryption_service = None
        self.addCleanup(lambda: setattr(encryption_service, '_encryption_service', None))
        self.user = User.objects.create_user(username='config-user', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')

    @patch('apps.ai_config.views.fetch_model_list')
    def test_list_models_reuses_saved_api_key_when_no_key_is_posted(self, mock_fetch_model_list):
        AIConfig.objects.create(
            user=self.user,
            provider='openai',
            api_key_encrypted=get_encryption().encrypt('sk-saved'),
            base_url='https://api.saved.example/v1',
            model_name='gpt-test',
        )
        mock_fetch_model_list.return_value = {
            'endpoint': 'https://api.saved.example/v1/models',
            'models': [{'id': 'gpt-test'}],
        }

        response = self.client.post('/api/ai-config/models', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['models'], [{'id': 'gpt-test'}])
        self.assertEqual(mock_fetch_model_list.call_args.kwargs['api_key'], 'sk-saved')
        self.assertEqual(mock_fetch_model_list.call_args.kwargs['base_url'], 'https://api.saved.example/v1')

    @patch('apps.ai_config.views.fetch_model_list')
    def test_list_models_allows_unsaved_temporary_config(self, mock_fetch_model_list):
        mock_fetch_model_list.return_value = {
            'endpoint': 'https://api.temp.example/v1/models',
            'models': [{'id': 'temp-model'}],
        }

        response = self.client.post(
            '/api/ai-config/models',
            {'provider': 'openai', 'base_url': 'https://api.temp.example/v1', 'api_key': 'sk-temp'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['models'], [{'id': 'temp-model'}])
        self.assertEqual(mock_fetch_model_list.call_args.kwargs['api_key'], 'sk-temp')
        self.assertEqual(mock_fetch_model_list.call_args.kwargs['base_url'], 'https://api.temp.example/v1')

    @patch('apps.ai_config.views.fetch_model_list')
    def test_list_models_returns_diagnostic_for_upstream_failure(self, mock_fetch_model_list):
        mock_fetch_model_list.side_effect = ModelFetchError(
            'Failed to fetch models: connection refused',
            endpoint='https://api.failed.example/v1/models',
        )

        response = self.client.post(
            '/api/ai-config/models',
            {'provider': 'openai', 'base_url': 'https://api.failed.example/v1', 'api_key': 'sk-temp'},
            format='json',
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error_type'], 'ModelFetchError')
        self.assertEqual(response.data['endpoint'], 'https://api.failed.example/v1/models')
        self.assertIn('后端无法连接模型列表接口', response.data['hint'])

    @patch('apps.ai_config.views.fetch_model_list')
    def test_list_models_returns_400_for_client_configuration_error(self, mock_fetch_model_list):
        mock_fetch_model_list.side_effect = ModelFetchError(
            'Base URL is required to derive the models endpoint.',
            client_error=True,
        )

        response = self.client.post(
            '/api/ai-config/models',
            {'provider': 'openai', 'base_url': '', 'api_key': 'sk-temp'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['status_code'], None)
        self.assertIn('基础 URL', response.data['hint'])


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class SyncAIConfigCommandTests(APITestCase):
    @patch.dict('os.environ', {'AI_DEFAULT_API_KEY': ''}, clear=False)
    def test_sync_ai_config_skips_cleanly_without_default_key(self):
        stdout = StringIO()

        call_command('sync_ai_config', username='local', stdout=stdout)

        self.assertEqual(AIConfig.objects.count(), 0)
        self.assertIn('Skipped AI config sync', stdout.getvalue())
