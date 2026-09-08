import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient, APITestCase

from apps.projects.models import Conversation, Project
from apps.users.authentication import create_access_token
from apps.users.models import User


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class ProjectFileValidationTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.user = User.objects.create_user(username='project-user', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')
        self.project = Project.objects.create(user=self.user, title='Project', project_type='presentation')

    def test_project_file_upload_uses_shared_validation_rules(self):
        upload = SimpleUploadedFile('malware.exe', b'not allowed', content_type='application/octet-stream')

        response = self.client.post(
            f'/api/projects/{self.project.id}/files/',
            {'files': [upload]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unsupported file type: exe', str(response.json()))


class DummyFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class DummyToolCall:
    def __init__(self, name, arguments, call_id='call-1'):
        self.id = call_id
        self.function = DummyFunction(name, arguments)


class DummyMessage:
    def __init__(self, content='', tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class DummyChoice:
    def __init__(self, message):
        self.message = message


class DummyResponse:
    def __init__(self, message):
        self.choices = [DummyChoice(message)]


class DummyHermes:
    def __init__(self):
        self.calls = 0

    def chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice='auto', extra_headers=None):
        del messages, tools, system_prompt, tool_choice, extra_headers
        self.calls += 1
        if self.calls == 1:
            return DummyResponse(DummyMessage(tool_calls=[DummyToolCall('doc_parse', '{"file_id": 123}')]))
        return DummyResponse(DummyMessage(content='这是 Hermes 的最终回答。'))


class BrokenHermes:
    def chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice='auto', extra_headers=None):
        del messages, tools, system_prompt, tool_choice, extra_headers
        raise RuntimeError('gateway failed')


class GatewayFailureReplyHermes:
    def chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice='auto', extra_headers=None):
        del messages, tools, system_prompt, tool_choice, extra_headers
        return DummyResponse(DummyMessage(content='API call failed after 3 retries: Connection error.'))


class DummyCompatAgent:
    def chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice='auto', extra_headers=None):
        del messages, tools, system_prompt, tool_choice, extra_headers
        return DummyResponse(DummyMessage(content='这是兼容链路的回答。'))


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class ConversationHermesStreamTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='chat-user', password='password123')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.user.id)}')
        self.project = Project.objects.create(user=self.user, title='Hermes Session', project_type='presentation')
        self.conversation = Conversation.objects.create(
            user=self.user,
            project=self.project,
            title='Hermes Session',
            mode='chat',
        )

    @patch('services.chat_service.registry.execute_tool', return_value={'ok': True, 'result': {'filename': 'notes.md', 'text': 'sample'}})
    @patch('services.chat_service.create_hermes_service', return_value=DummyHermes())
    def test_conversation_stream_uses_hermes_runtime_and_emits_tool_events(self, hermes_factory, execute_tool):
        response = self.client.post(
            f'/api/conversations/{self.conversation.id}/stream/',
            {'content': '帮我读取资料然后总结。'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = ''.join(
            item.decode('utf-8') if isinstance(item, bytes) else str(item)
            for item in response.streaming_content
        )

        self.assertIn('event: status', payload)
        self.assertIn('event: thought', payload)
        self.assertIn('event: tool_call', payload)
        self.assertIn('event: tool_result', payload)
        self.assertIn('event: done', payload)
        hermes_factory.assert_called_once()
        execute_tool.assert_called_once()

        assistant_message = self.conversation.messages.filter(role='assistant').latest('id')
        self.assertEqual(assistant_message.content, '这是 Hermes 的最终回答。')
        self.assertEqual(assistant_message.metadata['gateway'], 'hermes')
        self.assertEqual(assistant_message.metadata['session_id'], f'u{self.user.id}-p{self.project.id}')
        self.assertEqual(assistant_message.metadata['used_tools'], ['doc_parse'])
        self.assertEqual(len(assistant_message.metadata['tool_events']), 1)

    @patch('services.chat_service.AIService', return_value=DummyCompatAgent())
    @patch('services.chat_service.ChatService._get_config', return_value=SimpleNamespace(provider='openai'))
    @patch('services.chat_service.create_hermes_service', return_value=BrokenHermes())
    def test_conversation_stream_falls_back_to_compatible_agent_chain(self, _mock_hermes, _mock_config, _mock_ai_service):
        response = self.client.post(
            f'/api/conversations/{self.conversation.id}/stream/',
            {'content': '继续帮我推进方案。'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = ''.join(
            item.decode('utf-8') if isinstance(item, bytes) else str(item)
            for item in response.streaming_content
        )

        self.assertIn('event: status', payload)
        self.assertIn('event: done', payload)
        self.assertIn('Hermes 网关当前不可用', payload)
        self.assertIn('"diagnostic"', payload)

        assistant_message = self.conversation.messages.filter(role='assistant').latest('id')
        self.assertEqual(assistant_message.content, '这是兼容链路的回答。')
        self.assertEqual(assistant_message.metadata['gateway'], 'compat')

    @patch('services.chat_service.AIService', return_value=DummyCompatAgent())
    @patch('services.chat_service.ChatService._get_config', return_value=SimpleNamespace(provider='openai'))
    @patch('services.chat_service.create_hermes_service', return_value=GatewayFailureReplyHermes())
    def test_conversation_stream_recovers_when_gateway_returns_upstream_failure_text(self, _mock_hermes, _mock_config, _mock_ai_service):
        response = self.client.post(
            f'/api/conversations/{self.conversation.id}/stream/',
            {'content': '再试一轮。'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = ''.join(
            item.decode('utf-8') if isinstance(item, bytes) else str(item)
            for item in response.streaming_content
        )

        self.assertIn('Hermes 网关当前不可用', payload)
        self.assertIn('event: done', payload)

        assistant_message = self.conversation.messages.filter(role='assistant').latest('id')
        self.assertEqual(assistant_message.content, '这是兼容链路的回答。')
        self.assertEqual(assistant_message.metadata['gateway'], 'compat')
        self.assertNotIn('Connection error', assistant_message.content)

    @patch('services.chat_service.create_hermes_service', return_value=GatewayFailureReplyHermes())
    def test_conversation_stream_uses_local_fallback_when_gateway_reply_is_failure_text(self, _mock_hermes):
        response = self.client.post(
            f'/api/conversations/{self.conversation.id}/stream/',
            {'content': '没有配置时的保底。'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = ''.join(
            item.decode('utf-8') if isinstance(item, bytes) else str(item)
            for item in response.streaming_content
        )

        self.assertIn('Hermes 网关当前不可用', payload)
        self.assertIn('event: done', payload)

        assistant_message = self.conversation.messages.filter(role='assistant').latest('id')
        self.assertIn('Hermes 运行时这一轮暂时不可用', assistant_message.content)
        self.assertEqual(assistant_message.metadata['gateway'], 'fallback')
        self.assertNotIn('Connection error', assistant_message.content)

    @patch('apps.projects.views.ChatService.stream_turn', side_effect=RuntimeError('upstream exploded'))
    def test_conversation_stream_error_event_includes_diagnostic(self, _mock_stream_turn):
        response = self.client.post(
            f'/api/conversations/{self.conversation.id}/stream/',
            {'content': '测试失败诊断。'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = ''.join(
            item.decode('utf-8') if isinstance(item, bytes) else str(item)
            for item in response.streaming_content
        )

        self.assertIn('event: error', payload)
        self.assertIn('"diagnostic"', payload)
        self.assertIn('"error_type": "RuntimeError"', payload)
        self.assertIn('upstream exploded', payload)
