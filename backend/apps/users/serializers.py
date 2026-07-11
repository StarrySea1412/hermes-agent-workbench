from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'avatar_letter', 'points', 'vip_level']


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3, max_length=64)
    password = serializers.CharField(min_length=6, write_only=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
