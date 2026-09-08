from django.core import mail
from django.contrib.auth import authenticate
from django.test import TestCase, override_settings

from .forms import UserRegistrationForm
from .models import User


class RegistrationTests(TestCase):
	def test_registration_does_not_require_email_verification(self):
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
		self.assertTrue(user.is_active)
		self.assertTrue(user.is_email_verified)

		login_response = self.client.post(
			"/accounts/login/",
			{
				"email": "dashingbonnie@gmaa.com",
				"password": "StrongPass1@",
			},
		)
		self.assertEqual(login_response.status_code, 302)
		self.assertNotEqual(login_response.url, "/accounts/login/")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
	def test_password_reset_redirects_to_done_page(self):
		User.objects.create_user(
			email="reset@example.com",
			password="StrongPass1@",
			first_name="Reset",
			last_name="User",
		)

		response = self.client.post(
			"/accounts/password-reset/",
			{"email": "reset@example.com"},
		)

		self.assertRedirects(response, "/accounts/password-reset/done/")
		self.assertEqual(len(mail.outbox), 1)


class AdminUserAuthenticationTests(TestCase):
	def test_admin_created_user_can_authenticate_by_email(self):
		user = User.objects.create_user(
			email="admin-created@example.com",
			password="StrongPass1@",
			first_name="Admin",
			last_name="Created",
		)

		self.assertTrue(user.has_usable_password())
		self.assertIsNotNone(
			authenticate(email="admin-created@example.com", password="StrongPass1@")
		)


class RolePermissionTests(TestCase):
	def make_user(self, role):
		return User.objects.create_user(
			email=f"{role.lower()}@example.com",
			password="StrongPass1@",
			first_name=role,
			last_name="User",
			role=role,
		)

	def test_staff_has_transactional_permissions_only(self):
		user = self.make_user("STAFF")
		self.assertTrue(user.has_permission("record_sales"))
		self.assertTrue(user.has_permission("submit_expenses"))
		self.assertTrue(user.has_permission("update_stock_counts"))
		self.assertFalse(user.has_permission("manage_products"))
		self.assertFalse(user.has_permission("export_reports"))

	def test_business_owner_role_choices_exclude_owner_and_system_admin(self):
		form = UserRegistrationForm(
			allow_role=True,
			allowed_roles=["MANAGER", "STAFF", "ACCOUNTANT"],
		)
		self.assertEqual(
			set(form.fields["role"].choices),
			{
				("MANAGER", "Business Manager"),
				("STAFF", "Staff Member"),
				("ACCOUNTANT", "Accountant / Bookkeeper"),
			},
		)

	def test_system_admin_can_select_every_role(self):
		form = UserRegistrationForm(
			allow_role=True,
			allowed_roles=[role for role, _ in User.ROLE_CHOICES],
		)
		self.assertEqual(
			set(form.fields["role"].choices),
			set(User.ROLE_CHOICES),
		)

	def test_authenticated_pages_include_dashboard_back_link(self):
		user = self.make_user("OWNER")
		self.client.force_login(user)
		response = self.client.get("/accounts/profile/")
		self.assertContains(response, 'title="Back to dashboard"')

	def test_accountant_has_financial_permissions_only(self):
		user = self.make_user("ACCOUNTANT")
		self.assertTrue(user.has_permission("review_expenses"))
		self.assertTrue(user.has_permission("export_reports"))
		self.assertFalse(user.has_permission("record_sales"))
		self.assertFalse(user.has_permission("manage_inventory"))

	def test_manager_can_run_operations_but_not_manage_roles(self):
		user = self.make_user("MANAGER")
		self.assertTrue(user.has_permission("manage_products"))
		self.assertTrue(user.has_permission("approve_expenses"))
		self.assertFalse(user.has_permission("manage_roles"))
		self.assertFalse(user.has_permission("export_reports"))
