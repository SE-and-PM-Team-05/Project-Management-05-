import secrets

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Create the one initial Super Admin with a one-time password (REQ-FUNC-005)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        if User.objects.filter(is_superuser=True).exists():
            raise CommandError("A Super Admin already exists; this command only sets up an empty system.")

        password = secrets.token_urlsafe(12)
        user = User.objects.create_superuser(email=email, password=password)
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        self.stdout.write(f"Super Admin {user.email} created.")
        self.stdout.write(f"One-time password: {password}")
        self.stdout.write("Log in at /admin/; you will be asked to choose a new password.")
