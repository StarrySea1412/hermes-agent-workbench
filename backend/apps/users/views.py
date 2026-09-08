import bcrypt
from django.contrib.auth.hashers import check_password as django_check_password
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.users.authentication import create_access_token
from apps.users.models import User
from apps.users.serializers import RegisterSerializer, UserSerializer


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({"message": "用户名或密码不正确。"}, status=status.HTTP_401_UNAUTHORIZED)

    stored = user.password
    if stored.startswith(("pbkdf2_", "argon2", "scrypt")):
        valid = django_check_password(password, stored)
    else:
        try:
            valid = bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            valid = False

    if not valid:
        return Response({"message": "用户名或密码不正确。"}, status=status.HTTP_401_UNAUTHORIZED)

    token = create_access_token(user.id)
    return Response({"access_token": token, "token_type": "bearer"})


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data["username"]
    password = serializer.validated_data["password"]

    if User.objects.filter(username=username).exists():
        return Response({"message": "用户名已存在。"}, status=status.HTTP_400_BAD_REQUEST)

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User.objects.create(
        username=username,
        password=hashed,
        display_name=username,
        avatar_letter=username[0].upper(),
    )

    token = create_access_token(user.id)
    return Response({"access_token": token, "token_type": "bearer"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    old_password = request.data.get("old_password", "")
    new_password = request.data.get("new_password", "")

    if not old_password or not new_password:
        return Response({"message": "请同时提供旧密码和新密码。"}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 6:
        return Response({"message": "新密码至少需要 6 个字符。"}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    stored = user.password
    if stored.startswith(("pbkdf2_", "argon2", "scrypt")):
        valid = django_check_password(old_password, stored)
    else:
        try:
            valid = bcrypt.checkpw(old_password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            valid = False

    if not valid:
        return Response({"message": "旧密码不正确。"}, status=status.HTTP_400_BAD_REQUEST)

    user.password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user.save(update_fields=["password"])

    return Response({"message": "密码修改成功。"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_token_view(request):
    token = create_access_token(request.user.id)
    return Response({"access_token": token, "token_type": "bearer"})
