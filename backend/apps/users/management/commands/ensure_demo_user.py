import os

from django.core.management.base import BaseCommand

from apps.users.models import User


class Command(BaseCommand):
    help = "Ensure that a local demo user exists for the workbench."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.getenv("DEMO_USERNAME", "admin"),
            help="Demo username to create or update.",
        )
        parser.add_argument(
            "--password",
            default=os.getenv("DEMO_PASSWORD", "admin123"),
            help="Demo password to set when creating the user, or when --force-password is used.",
        )
        parser.add_argument(
            "--display-name",
            default=os.getenv("DEMO_DISPLAY_NAME", "Admin"),
            help="Display name for the demo user.",
        )
        parser.add_argument(
            "--force-password",
            action="store_true",
            help="Reset the password even when the user already exists.",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        password = options["password"]
        display_name = options["display_name"].strip() or username
        avatar_letter = (display_name or username or "A")[0].upper()

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "display_name": display_name,
                "avatar_letter": avatar_letter,
                "is_active": True,
                "is_staff": True,
            },
        )

        dirty_fields = []
        if user.display_name != display_name:
            user.display_name = display_name
            dirty_fields.append("display_name")
        if user.avatar_letter != avatar_letter:
            user.avatar_letter = avatar_letter
            dirty_fields.append("avatar_letter")
        if not user.is_active:
            user.is_active = True
            dirty_fields.append("is_active")
        if not user.is_staff:
            user.is_staff = True
            dirty_fields.append("is_staff")

        if created or options["force_password"]:
            user.set_password(password)
            dirty_fields.append("password")

        if created:
            user.save()
        elif dirty_fields:
            dirty_fields.append("updated_at")
            user.save(update_fields=dirty_fields)

        action = "created" if created else "updated"
        password_status = "password synced" if created or options["force_password"] else "password kept"
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo user {action}: {user.username} ({password_status})."
            )
        )
