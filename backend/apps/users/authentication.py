from datetime import datetime, timedelta

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from apps.users.models import User
from apps.users.local_user import get_local_user


class JWTAuthentication(authentication.BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        if getattr(settings, "LOCAL_SINGLE_USER_MODE", True):
            return (get_local_user(), None)

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith(self.keyword + ' '):
            return None

        token = auth_header[len(self.keyword) + 1:]
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token已过期')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('无效Token')

        user_id = payload.get('sub')
        if user_id is None:
            raise exceptions.AuthenticationFailed('无效Token')

        try:
            user = User.objects.get(id=int(user_id))
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('用户不存在')

        return (user, token)


def create_access_token(user_id: int) -> str:
    from django.conf import settings as conf
    expire = datetime.utcnow() + timedelta(minutes=conf.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {'sub': str(user_id), 'exp': expire}
    return jwt.encode(payload, conf.JWT_SECRET_KEY, algorithm='HS256')
