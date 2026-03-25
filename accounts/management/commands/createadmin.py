from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create an admin user'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Admin username', default='admin')
        parser.add_argument('--email', type=str, help='Admin email', default='admin@example.com')
        parser.add_argument('--password', type=str, help='Admin password', default='admin123')
        parser.add_argument('--first-name', type=str, help='Admin first name', default='Admin')
        parser.add_argument('--last-name', type=str, help='Admin last name', default='User')

    def handle(self, *args, **options):
        if User.objects.filter(username=options['username']).exists():
            self.stdout.write(
                self.style.WARNING(f"User '{options['username']}' already exists")
            )
            return

        user = User.objects.create_user(
            username=options['username'],
            email=options['email'],
            password=options['password'],
            first_name=options['first_name'],
            last_name=options['last_name'],
            role='admin'
        )

        self.stdout.write(
            self.style.SUCCESS(f"Admin user '{user.username}' created successfully!")
        )
        self.stdout.write(f"Email: {user.email}")
        self.stdout.write(f"Role: {user.get_role_display()}")
        self.stdout.write("You can now login with these credentials.")