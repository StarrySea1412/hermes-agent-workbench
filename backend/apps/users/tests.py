from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.logs.models import RequestLog
from apps.bids.models import Bid
from apps.users.authentication import create_access_token
from apps.users.models import User


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class LoginLoggingTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='alice', password='wonderland')

    def test_login_response_token_is_masked_in_request_logs(self):
        response = self.client.post('/api/auth/login', {'username': 'alice', 'password': 'wonderland'}, format='json')

        self.assertEqual(response.status_code, 200)
        log_entry = RequestLog.objects.get(path='/api/auth/login')
        self.assertEqual(log_entry.request_body['password'], '******')
        self.assertEqual(log_entry.response_body['access_token'], '******')
        self.assertEqual(log_entry.response_body['token_type'], 'bearer')


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class UserBidAccessTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.other_user = User.objects.create_user(username='other', password='password123')
        self.bid = Bid.objects.create(title='Owner Bid', user=self.owner, total_chapters=0)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.other_user.id)}')

    def test_user_bid_route_forbids_access_to_other_users(self):
        response = self.client.get(f'/api/users/{self.owner.id}/bids')

        self.assertEqual(response.status_code, 403)


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY='test-jwt-secret-key-with-32-bytes!!',
)
class DemoUserCommandTests(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_ensure_demo_user_command_creates_loginable_account(self):
        stdout = StringIO()

        call_command(
            'ensure_demo_user',
            username='admin',
            password='admin123',
            force_password=True,
            stdout=stdout,
        )

        user = User.objects.get(username='admin')
        self.assertTrue(user.is_staff)
        self.assertIn('Demo user', stdout.getvalue())

        response = self.client.post('/api/auth/login', {'username': 'admin', 'password': 'admin123'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.data)
