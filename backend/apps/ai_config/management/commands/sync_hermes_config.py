import os

from django.core.management.base import BaseCommand, CommandError

from apps.users.local_user import get_local_user
from apps.users.models import User
from services.hermes_config_sync import sync_hermes_config_for_user


class Command(BaseCommand):
    help = "Sync the active AI config into the local Hermes runtime config."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("AI_DEFAULT_USERNAME", "local"),
            help="User to receive the Hermes config. Defaults to AI_DEFAULT_USERNAME or local.",
        )
        parser.add_argument("--user-id", type=int, help="Explicit user id to sync.")

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        username = options["username"]

        if user_id:
            user = User.objects.filter(id=user_id).first()
            if user is None:
                raise CommandError(f"User id '{user_id}' does not exist.")
        elif username == "local":
            user = get_local_user()
        else:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' does not exist.")

        result = sync_hermes_config_for_user(user)
        if not result.get("ok"):
            raise CommandError("No active AI config found for the selected user.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Hermes config synced for {user.username}: {result['model_name']} -> {result['path']}"
            )
        )
