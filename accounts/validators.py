import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """Require a mixed-case password with a digit and special character."""

    def validate(self, password, user=None):
        requirements = (
            (r'[a-z]', 'at least one lowercase letter'),
            (r'[A-Z]', 'at least one uppercase letter'),
            (r'\d', 'at least one number'),
            (r'[^A-Za-z0-9]', 'at least one special character'),
        )
        missing = [message for pattern, message in requirements if not re.search(pattern, password)]
        if missing:
            raise ValidationError(
                'Password must contain ' + ', '.join(missing) + '.',
                code='password_complexity',
            )

    def get_help_text(self):
        return (
            'Your password must be at least 8 characters and contain an uppercase '
            'letter, a lowercase letter, a number, and a special character.'
        )
