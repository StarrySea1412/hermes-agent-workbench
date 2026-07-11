import os

from django.core.management.base import BaseCommand, CommandError

from apps.ai_config.models import AIConfig
from apps.users.local_user import get_local_user
from apps.users.models import User
from services.encryption_service import get_encryption


class Command(BaseCommand):
    help = "Sync the local AI configuration from environment variables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("AI_DEFAULT_USERNAME", "local"),
            help="User to receive the AI config. Defaults to AI_DEFAULT_USERNAME or local.",
        )
        parser.add_argument(
            "--overwrite-key",
            action="store_true",
            help="Replace an existing encrypted API key when AI_DEFAULT_API_KEY is present.",
        )

    def handle(self, *args, **options):
        provider = os.getenv("AI_DEFAULT_PROVIDER", "openai")
        base_url = os.getenv("AI_DEFAULT_BASE_URL", "").rstrip("/")
        model_name = os.getenv("AI_DEFAULT_MODEL", "").strip()
        api_key = os.getenv("AI_DEFAULT_API_KEY", "")
        username = options["username"]

        if username == "local":
            user = get_local_user()
        else:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' does not exist.")

        config = AIConfig.objects.filter(user=user).first()
        should_write_key = bool(api_key) and (options["overwrite_key"] or config is None or not config.api_key_encrypted)

        resolved_base_url = base_url or (config.base_url if config else "")
        resolved_model_name = model_name or (config.model_name if config else "")

        if config is None and (not api_key or not resolved_base_url or not resolved_model_name):
            self.stdout.write(
                self.style.WARNING(
                    "Skipped AI config sync: AI_DEFAULT_API_KEY, AI_DEFAULT_BASE_URL, and AI_DEFAULT_MODEL are required for a new config."
                )
            )
            return

        defaults = {
            "provider": provider,
            "base_url": resolved_base_url,
            "model_name": resolved_model_name,
            "temperature": float(os.getenv("AI_DEFAULT_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("AI_DEFAULT_MAX_TOKENS", "2000")),
            "is_active": True,
        }

        if should_write_key:
            defaults["api_key_encrypted"] = get_encryption().encrypt(api_key)
        elif config is None:
            self.stdout.write(
                self.style.WARNING(
                f"Skipped AI config sync for {user.username}: no AI_DEFAULT_API_KEY is configured yet."
                )
            )
            return

        config, created = AIConfig.objects.update_or_create(user=user, defaults=defaults)
        action = "created" if created else "updated"
        key_status = "key synced" if should_write_key else "existing key kept"
        self.stdout.write(
            self.style.SUCCESS(
                f"AI config {action} for {user.username}: {provider} {resolved_model_name} @ {resolved_base_url} ({key_status})."
            )
        )
