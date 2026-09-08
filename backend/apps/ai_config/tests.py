import json
import shutil
import tempfile
from io import StringIO
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from apps.ai_config.models import AIConfig
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
class HermesSkillApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='operator', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')

    def test_list_hermes_skills(self):
        response = self.client.get('/api/hermes/skills')

        self.assertEqual(response.status_code, 200)
        self.assertIn('skills', response.data)
        self.assertTrue(
            any(skill['path'] == 'agent-engineering/general-operator' for skill in response.data['skills'])
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


class HermesConfigSyncLoopGuardTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sync-user', password='password123')
        encryption = get_encryption()
        self.config = AIConfig.objects.create(
            user=self.user,
            provider='openai',
            base_url='https://api.example.com/v1',
            model_name='test-model',
            api_key_encrypted=encryption.encrypt('sk-test'),
            temperature=0.7,
            max_tokens=4000,
            is_active=True,
        )

    @patch('services.hermes_config_sync.load_existing_config', return_value={})
    @patch('services.hermes_config_sync.get_hermes_config_path')
    def test_sync_writes_config_for_normal_upstream(self, mock_path, _mock_existing):
        import tempfile as tempfile_module
        from pathlib import Path as FsPath

        with tempfile_module.TemporaryDirectory() as tmpdir:
            mock_path.return_value = FsPath(tmpdir) / 'config.yaml'
            from services.hermes_config_sync import sync_hermes_config_for_user

            result = sync_hermes_config_for_user(self.user)

            self.assertTrue(result['ok'])
            self.assertTrue(mock_path.return_value.exists())

    @patch('services.hermes_config_sync.load_existing_config', return_value={})
    @patch('services.hermes_config_sync._gateway_self_urls')
    @patch('services.hermes_config_sync.get_hermes_config_path')
    def test_sync_refuses_gateway_self_reference(self, mock_path, mock_self_urls, _mock_existing):
        import tempfile as tempfile_module
        from pathlib import Path as FsPath

        mock_self_urls.return_value = {'http://127.0.0.1:8642/v1'}
        with tempfile_module.TemporaryDirectory() as tmpdir:
            config_path = FsPath(tmpdir) / 'config.yaml'
            mock_path.return_value = config_path
            self.config.base_url = 'http://127.0.0.1:8642/v1'
            self.config.save()

            from services.hermes_config_sync import sync_hermes_config_for_user

            result = sync_hermes_config_for_user(self.user)

            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'], 'gateway_self_reference')
            self.assertFalse(config_path.exists())


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class CcSwitchImportTests(APITestCase):
    def setUp(self):
        import sqlite3

        self.db_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.db_dir, ignore_errors=True))

        db_path = self.db_dir + '/cc-switch.db'
        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE providers (id TEXT PRIMARY KEY, app_type TEXT, name TEXT, "
            "settings_config TEXT, is_current INTEGER DEFAULT 0, sort_index INTEGER DEFAULT 0)"
        )
        connection.execute(
            "INSERT INTO providers VALUES ('cla-1', 'claude', '测试中转', ?, 1, 0)",
            (json.dumps({'env': {
                'ANTHROPIC_AUTH_TOKEN': 'sk-cc-claude-key',
                'ANTHROPIC_BASE_URL': 'https://claude.relay.example/',
                'ANTHROPIC_MODEL': 'grok-4.5[1M]',
            }}),),
        )
        connection.execute(
            "INSERT INTO providers VALUES ('cod-1', 'codex', '测试OpenAI', ?, 0, 1)",
            (json.dumps({
                'auth': {'OPENAI_API_KEY': 'sk-cc-openai-key'},
                'config': 'model = "gpt-5.6-luna"\n[model_providers.custom]\nname = "custom"\nbase_url = "https://api.relay.example/v1"\n',
            }),),
        )
        connection.execute(
            "INSERT INTO providers VALUES ('bad-1', 'claude', '缺key', ?, 0, 2)",
            (json.dumps({'env': {'ANTHROPIC_BASE_URL': 'https://broken.example/'}}),),
        )
        connection.commit()
        connection.close()

        self.client = APIClient()
        self.user = User.objects.create_user(username='cc-user', password='password123')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')

    def test_list_providers_excludes_incomplete_and_hides_keys(self):
        with patch('apps.ai_config.cc_switch_service.get_cc_switch_db_path',
                   return_value=f'{self.db_dir}/cc-switch.db'):
            response = self.client.get('/api/ai-config/cc-switch')

        self.assertEqual(response.status_code, 200)
        providers = response.json()['providers']
        self.assertEqual([item['id'] for item in providers], ['cla-1', 'cod-1'])
        claude = providers[0]
        self.assertEqual(claude['base_url'], 'https://claude.relay.example')
        self.assertEqual(claude['model_name'], 'grok-4.5')
        self.assertNotIn('api_key', claude)

    def test_import_creates_active_config_without_exposing_key_to_client(self):
        with patch('apps.ai_config.cc_switch_service.get_cc_switch_db_path',
                   return_value=f'{self.db_dir}/cc-switch.db'), \
             patch('apps.ai_config.views._sync_hermes_config'):
            response = self.client.post(
                '/api/ai-config/cc-switch/import',
                {'provider_id': 'cla-1'},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('已导入并启用', payload['message'])

        config = AIConfig.objects.get(user=self.user)
        self.assertEqual(config.provider, 'anthropic')
        self.assertEqual(config.base_url, 'https://claude.relay.example')
        self.assertEqual(config.model_name, 'grok-4.5')
        self.assertEqual(get_encryption().decrypt(config.api_key_encrypted), 'sk-cc-claude-key')
        self.assertNotIn('sk-cc-claude-key', json.dumps(response.json()))

    def test_import_rejects_unknown_provider(self):
        with patch('apps.ai_config.cc_switch_service.get_cc_switch_db_path',
                   return_value=f'{self.db_dir}/cc-switch.db'):
            response = self.client.post(
                '/api/ai-config/cc-switch/import',
                {'provider_id': 'missing'},
                format='json',
            )

        self.assertEqual(response.status_code, 404)
