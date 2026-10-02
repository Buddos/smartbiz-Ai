from django.test import TestCase
from django.urls import reverse

from accounts.models import User, UserActivity
from businesses.models import Business

from .models import Appointment, BarberService, Chair


class LiveChairBoardTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Live Board Barbershop",
            business_type="BARBER",
            email="board@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.barber = User.objects.create_user(
            email="barber@example.com",
            password="test-password",
            first_name="Marcus",
            last_name="Barber",
            role="BARBER",
            business=self.business,
        )
        self.chair = Chair.objects.create(
            business=self.business,
            label="Chair 1",
            barber=self.barber,
        )
        self.service = BarberService.objects.create(
            business=self.business,
            name="Haircut",
            price=350,
        )
        self.client.force_login(self.owner)

    def test_board_page_and_live_endpoint_show_persisted_chairs_and_appointments(self):
        appointment = Appointment.objects.create(
            business=self.business,
            client_name="Brian",
            service=self.service,
            barber=self.barber,
            chair=self.chair,
            status="IN_CHAIR",
        )

        response = self.client.get(reverse("barber:board"))
        live_response = self.client.get(reverse("barber:live_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chair view")
        self.assertContains(response, "Walk-in")
        self.assertEqual(live_response.status_code, 200)
        self.assertEqual(live_response.json()["appointments"][0]["id"], str(appointment.id))
        self.assertEqual(live_response.json()["metrics"]["occupied"], 1)

    def test_board_can_add_walk_in_and_reflect_it_in_live_queue(self):
        response = self.client.post(reverse("barber:create_appointment"), {
            "appointment_type": "walk_in",
            "client_name": "Alex",
            "client_phone": "0712345678",
            "service_id": str(self.service.id),
            "barber_id": str(self.barber.id),
            "chair_id": "",
        })

        self.assertEqual(response.status_code, 200)
        appointment = Appointment.objects.get(id=response.json()["appointment_id"])
        self.assertEqual(appointment.status, "WAITING")
        self.assertEqual(appointment.source, "WALK_IN")
        self.assertIsNotNone(appointment.checked_in_at)
        live_response = self.client.get(reverse("barber:live_board"))
        self.assertEqual(live_response.json()["metrics"]["waiting"], 1)
        self.assertEqual(live_response.json()["queue"][0]["name"], "Alex")

    def test_business_admin_is_the_team_creation_entry_point_for_barbershops(self):
        admin_page = self.client.get(reverse("business_admin"))
        barber_page = self.client.get(reverse("barber:barbers"))
        team_page = self.client.get(reverse("accounts:users_list"))
        self.assertContains(admin_page, "Manage team")
        self.assertNotContains(admin_page, "Add team member")
        self.assertContains(barber_page, "Live daily appointment and sale totals.")
        self.assertNotContains(barber_page, "Add a barber")
        self.assertNotContains(barber_page, "Add barber")
        self.assertContains(team_page, "Create team member")
        self.assertContains(team_page, reverse("accounts:user_create"))

        response = self.client.post(reverse("accounts:user_create"), {
            "first_name": "Maya",
            "last_name": "North",
            "email": "maya.north@example.com",
            "phone_number": "0712345678",
            "role": "BARBER",
            "password1": "M0untain!River-82",
            "password2": "M0untain!River-82",
        })

        self.assertRedirects(response, reverse("accounts:users_list"))
        barber = User.objects.get(email="maya.north@example.com")
        self.assertEqual(barber.business, self.business)
        self.assertEqual(barber.role, "BARBER")
        self.assertTrue(barber.is_active)
        self.assertTrue(barber.check_password("M0untain!River-82"))
        self.assertTrue(UserActivity.objects.filter(
            user=self.owner, object_id=str(barber.id), action="CREATE"
        ).exists())

        board = self.client.get(reverse("barber:board"))
        self.assertIn(barber, board.context["barbers"])
        sales = self.client.get(reverse("sales:create"))
        self.assertContains(sales, "Maya North")
        admin_dashboard = self.client.get(reverse("business_admin"))
        self.assertEqual(admin_dashboard.context["team_count"], 3)

    def test_barbershop_team_creation_form_offers_barber_role(self):
        response = self.client.get(reverse("accounts:user_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="BARBER">Barber</option>', html=True)
