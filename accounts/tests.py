import re

from django.core import mail
from django.test import TestCase, override_settings

from .models import User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailVerificationTests(TestCase):
	def test_registration_requires_email_verification(self):
		response = self.client.post(
			"/accounts/register/",
			{
				"first_name": "Dashing",
				"last_name": "Bonnie",
				"email": "dashingbonnie@gmaa.com",
				"password1": "StrongPass1@",
				"password2": "StrongPass1@",
			},
		)

		self.assertRedirects(response, "/accounts/login/")
		user = User.objects.get(email="dashingbonnie@gmaa.com")
		self.assertFalse(user.is_active)
		self.assertFalse(user.is_email_verified)
		self.assertEqual(len(mail.outbox), 1)

		link = re.search(r"http://testserver/accounts/verify-email/[^\s]+", mail.outbox[0].body).group(0)
		verify_response = self.client.get(link.replace("http://testserver", ""))

		self.assertRedirects(verify_response, "/accounts/login/")
		user.refresh_from_db()
		self.assertTrue(user.is_active)
		self.assertTrue(user.is_email_verified)
