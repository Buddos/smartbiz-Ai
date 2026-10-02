from datetime import datetime, time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from expenses.models import Expense
from products.models import Product
from sales.models import Sale, SaleItem

from .models import Appointment, BarberGoal, BarberService, BarberShift, Chair


class BarberPagesTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Page Tests Shop",
            business_type="BARBER",
            email="pages@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="pages-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.barber = User.objects.create_user(
            email="pages-barber@example.com",
            password="test-password",
            first_name="Sam",
            role="BARBER",
            business=self.business,
        )
        self.customer = Customer.objects.create(
            business=self.business,
            name="Sam Client",
            phone="0712345678",
        )
        self.service = BarberService.objects.create(
            business=self.business,
            name="Haircut",
            price=500,
        )
        self.chair = Chair.objects.create(
            business=self.business,
            label="Chair 1",
            barber=self.barber,
        )
        self.client.force_login(self.owner)

    def add_sale(self, **overrides):
        values = {
            "business": self.business,
            "created_by": self.owner,
            "customer": self.customer,
            "customer_name": self.customer.name,
            "barber": self.barber,
            "subtotal": 500,
            "amount_paid": 500,
            "payment_method": "CASH",
        }
        values.update(overrides)
        return Sale.objects.create(**values)

    def test_clients_page_uses_saved_customer_and_refreshes_live_data(self):
        page = self.client.get(reverse("barber:clients"))
        live = self.client.get(reverse("barber:live_clients"))

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sam Client")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["summary"]["total"], 1)
        self.assertEqual(live.json()["clients"][0]["phone"], self.customer.phone)
        self.assertEqual(live.json()["clients"][0]["status"], "new")

    def test_money_page_calculates_revenue_expenses_and_cash_from_records(self):
        sale = self.add_sale()
        product = Product.objects.create(
            business=self.business,
            name="Beard Oil",
            purchase_price=120,
            selling_price=500,
            created_by=self.owner,
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_name=product.name,
            unit_price=500,
            cost_price=120,
            quantity=1,
        )
        Expense.objects.create(
            business=self.business,
            title="Shop supplies",
            amount=100,
            expense_date=timezone.localdate(),
            created_by=self.owner,
        )

        page = self.client.get(reverse("barber:money"), {"period": "today"})
        live = self.client.get(reverse("barber:live_money"), {"period": "today"})

        self.assertEqual(page.status_code, 200)
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["revenue"], 500)
        self.assertEqual(live.json()["expenses"], 100)
        self.assertEqual(live.json()["profit"], 280)
        self.assertEqual(live.json()["cash_in"], 500)

    def test_goals_save_and_show_progress_from_actual_sales(self):
        self.add_sale()
        response = self.client.post(reverse("barber:goals"), {
            "metric": "DAILY_REVENUE",
            "target": "1000",
        })

        self.assertEqual(response.status_code, 302)
        goal = BarberGoal.objects.get(business=self.business)
        live = self.client.get(reverse("barber:live_goals"))

        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["goals"][0]["id"], str(goal.id))
        self.assertEqual(live.json()["goals"][0]["current"], 500)
        self.assertEqual(live.json()["goals"][0]["percent"], 50)
        page = self.client.get(reverse("barber:goals"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "SmartBiz Coach")

    def test_client_and_product_rate_goals_use_completed_visits(self):
        sale = self.add_sale()
        product = Product.objects.create(
            business=self.business,
            name="Beard Oil",
            purchase_price=120,
            selling_price=500,
            created_by=self.owner,
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_name="Beard Oil",
            unit_price=500,
            cost_price=120,
            quantity=1,
        )
        Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            barber=self.barber,
            sale=sale,
            completed_at=timezone.now(),
            status="DONE",
        )
        Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            barber=self.barber,
            completed_at=timezone.now(),
            status="DONE",
        )
        BarberGoal.objects.create(
            business=self.business,
            metric="MONTHLY_ATTACH_RATE",
            target=100,
        )
        BarberGoal.objects.create(
            business=self.business,
            metric="MONTHLY_REPEAT_RATE",
            target=100,
        )

        live = self.client.get(reverse("barber:live_goals"))
        goals = {goal["metric"]: goal["current"] for goal in live.json()["goals"]}

        self.assertEqual(goals["Monthly product attach rate"], 50)
        self.assertEqual(goals["Monthly repeat client rate"], 100)

    def test_schedule_page_reads_saved_shifts_and_real_appointment_overlap(self):
        today = timezone.localdate()
        BarberShift.objects.create(
            business=self.business,
            barber=self.barber,
            chair=self.chair,
            shift_date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        Appointment.objects.create(
            business=self.business,
            client_name="Booked client",
            service=self.service,
            barber=self.barber,
            chair=self.chair,
            start_time=timezone.make_aware(datetime.combine(today, time(9, 15))),
            duration_min=30,
            status="CONFIRMED",
        )

        page = self.client.get(reverse("barber:schedule"), {"week": today.isoformat()})
        live = self.client.get(reverse("barber:live_schedule"), {"week": today.isoformat()})

        self.assertEqual(page.status_code, 200)
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["snapshot"]["staffed_chairs"], 1)
        self.assertEqual(live.json()["utilization"][0]["percent"], 50)
        self.assertEqual(live.json()["shifts"][0]["barber"], self.barber.get_full_name())

    def test_schedule_form_saves_a_business_scoped_shift(self):
        today = timezone.localdate()
        response = self.client.post(reverse("barber:schedule"), {
            "barber": str(self.barber.id),
            "chair": str(self.chair.id),
            "shift_date": today.isoformat(),
            "start_time": "09:00",
            "end_time": "18:00",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BarberShift.objects.filter(business=self.business).count(), 1)

    def test_barber_sees_a_chair_assigned_to_them_by_shift(self):
        unassigned_chair = Chair.objects.create(
            business=self.business,
            label="Chair 2",
        )
        BarberShift.objects.create(
            business=self.business,
            barber=self.barber,
            chair=unassigned_chair,
            shift_date=timezone.localdate(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        self.client.force_login(self.barber)

        live = self.client.get(reverse("barber:live_schedule"), {
            "week": timezone.localdate().isoformat(),
        })

        self.assertEqual(live.status_code, 200)
        self.assertIn("Chair 2", [chair["label"] for chair in live.json()["chairs"]])

    def test_client_detail_shows_saved_customer_notes_and_visit(self):
        sale = self.add_sale()
        self.customer.notes = "Prefers a short fade."
        self.customer.save(update_fields=["notes"])
        Appointment.objects.create(
            business=self.business,
            customer=self.customer,
            service=self.service,
            barber=self.barber,
            sale=sale,
            start_time=timezone.now(),
            completed_at=timezone.now(),
            status="DONE",
        )

        response = self.client.get(reverse("barber:client_detail", kwargs={"customer_id": self.customer.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prefers a short fade.")
        self.assertContains(response, "Haircut")

    def test_barber_role_cannot_view_business_money_page(self):
        self.client.force_login(self.barber)

        response = self.client.get(reverse("barber:money"))

        self.assertEqual(response.status_code, 302)

    def test_barber_client_list_only_shows_clients_they_served(self):
        other_barber = User.objects.create_user(
            email="another-pages-barber@example.com",
            password="test-password",
            first_name="Taylor",
            role="BARBER",
            business=self.business,
        )
        other_customer = Customer.objects.create(
            business=self.business,
            name="Other Barber Client",
        )
        Sale.objects.create(
            business=self.business,
            created_by=self.owner,
            customer=other_customer,
            customer_name=other_customer.name,
            barber=other_barber,
            subtotal=400,
            amount_paid=400,
            payment_method="CASH",
        )
        self.add_sale()
        self.client.force_login(self.barber)

        live = self.client.get(reverse("barber:live_clients"))

        self.assertEqual([row["name"] for row in live.json()["clients"]], ["Sam Client"])
