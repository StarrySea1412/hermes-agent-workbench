from apps.users.models import User


LOCAL_USERNAME = "local"


def get_local_user():
    user, created = User.objects.get_or_create(
        username=LOCAL_USERNAME,
        defaults={
            "display_name": "本地用户",
            "avatar_letter": "L",
            "is_active": True,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user
