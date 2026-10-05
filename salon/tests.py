from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from products.models import Product
from sales.models import Sale

from .models import SalonAppointment, SalonClientPackage, SalonPackageRedemption


class SalonWorkspaceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Rose Salon",
            business_type="SALON",
            email="salon@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
            first_name="Salon",
            last_name="Owner",
            role="OWNER",
            business=self.business,
        )
        self.stylist = User.objects.create_user(
            email="stylist@example.com",
            password="test-password",
            first_name="Maya",
            last_name="Stylist",
            role="STAFF",
            business=self.business,
        )
        self.customer = Customer.objects.create(
            business=self.business,
            name="Amina Client",
            phone="0712345678",
        )
        self.service = Product.objects.create(
            business=self.business,
            name="Wash and style",
            sku="SALON-SVC-001",
            selling_price=1200,
            created_by=self.owner,
            metadata={"salon_service": True, "duration_min": 45},
        )
        self.client.force_login(self.owner)

    def test_shared_customer_and_expense_pages_use_the_dashboard_sidebar(self):
        for route_name in ("customers:list", "expenses:list"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content.count(b'id="salonSidebar"'), 1)
                self.assertContains(response, "dashboard-readable.css")
                self.assertContains(response, 'aria-current="page"')

    def test_appointment_booking_saves_selected_business_records(self):
        starts_at = timezone.localtime() + timedelta(days=1)
        response = self.client.post(reverse("salon:appointments"), {
            "customer": str(self.customer.id),
            "client_name": "",
            "client_phone": "",
            "services": [str(self.service.id)],
            "stylist": str(self.stylist.id),
            "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
            "source": "WEBSITE",
            "notes": "Prefers a quiet appointment",
        })

        appointment = SalonAppointment.objects.get(business=self.business)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.customer, self.customer)
        self.assertEqual(appointment.stylist, self.stylist)
        self.assertEqual(list(appointment.services.all()), [self.service])
        self.assertEqual(appointment.duration_min, 45)
        self.assertEqual(appointment.source, "WEBSITE")

    def test_appointment_page_and_status_updates_are_business_scoped(self):
        appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            stylist=self.stylist,
            starts_at=timezone.now() + timedelta(hours=2),
            duration_min=45,
        )
        appointment.services.add(self.service)
        other_business = Business.objects.create(
            name="Other Salon",
            business_type="SALON",
            email="other@example.com",
            phone_number="0700000001",
        )
        other_appointment = SalonAppointment.objects.create(
            business=other_business,
            client_name="Private Client",
            starts_at=timezone.now() + timedelta(hours=2),
            duration_min=30,
        )

        page = self.client.get(
            reverse("salon:appointments"),
            {"date": appointment.starts_at.date().isoformat()},
        )
        update = self.client.post(reverse("salon:appointments"), {
            "action": "status",
            "appointment_id": str(appointment.id),
            "status": "CONFIRMED",
        })
        foreign_update = self.client.post(reverse("salon:appointments"), {
            "action": "status",
            "appointment_id": str(other_appointment.id),
            "status": "CANCELLED",
        })
        manual_completion = self.client.post(reverse("salon:appointments"), {
            "action": "status",
            "appointment_id": str(appointment.id),
            "status": "COMPLETED",
        })

        appointment.refresh_from_db()
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Amina Client")
        self.assertNotContains(page, "Private Client")
        self.assertEqual(update.status_code, 302)
        self.assertEqual(appointment.status, "CONFIRMED")
        self.assertEqual(foreign_update.status_code, 404)
        self.assertEqual(manual_completion.status_code, 302)
        self.assertEqual(appointment.status, "CONFIRMED")

    def test_dashboard_and_stylist_metrics_use_saved_appointments(self):
        appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            stylist=self.stylist,
            starts_at=timezone.now() + timedelta(hours=2),
            duration_min=45,
        )
        appointment.services.add(self.service)
        Sale.objects.create(
            business=self.business,
            sale_number="SALON-TEST-0001",
            customer=self.customer,
            customer_name=self.customer.name,
            subtotal=1200,
            total=1200,
            amount_paid=1200,
            payment_status="PAID",
            created_by=self.owner,
            metadata={"served_by": {"id": str(self.stylist.id)}},
        )

        dashboard = self.client.get(reverse("dashboard"))
        stylists = self.client.get(reverse("salon:stylists"))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "dashboard-readable")
        self.assertEqual(dashboard.context["appointments_today"], 1)
        self.assertContains(dashboard, "Amina Client")
        self.assertEqual(stylists.status_code, 200)
        self.assertEqual(stylists.context["appointments_today"], 1)
        self.assertEqual(stylists.context["stylists"][0].appointments_today, 1)
        self.assertEqual(stylists.context["sales_today"], 1)
        self.assertEqual(stylists.context["stylists"][0].revenue_today, 1200)
        self.assertNotContains(stylists, "Team access")
        self.assertNotContains(stylists, "Open team access")
        self.client.force_login(self.stylist)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_booking_pipeline_updates_real_stages_and_is_business_scoped(self):
        starts_at = timezone.now() + timedelta(hours=1)
        appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            stylist=self.stylist,
            starts_at=starts_at,
            duration_min=45,
        )
        appointment.services.add(self.service)
        other_business = Business.objects.create(
            name="Other Salon",
            business_type="SALON",
            email="other-pipeline@example.com",
            phone_number="0700000002",
        )
        foreign_appointment = SalonAppointment.objects.create(
            business=other_business,
            client_name="Hidden Pipeline Client",
            starts_at=starts_at,
            duration_min=30,
        )

        board = self.client.get(reverse("salon:bookings_pipeline"), {
            "date": starts_at.date().isoformat(),
        })
        update = self.client.post(reverse("salon:bookings_pipeline"), {
            "appointment_id": str(appointment.id),
            "status": "IN_SERVICE",
        })
        foreign_update = self.client.post(reverse("salon:bookings_pipeline"), {
            "appointment_id": str(foreign_appointment.id),
            "status": "IN_SERVICE",
        })
        completed_update = self.client.post(reverse("salon:bookings_pipeline"), {
            "appointment_id": str(appointment.id),
            "status": "COMPLETED",
        })

        appointment.refresh_from_db()
        self.assertEqual(board.status_code, 200)
        self.assertContains(board, "Bookings pipeline")
        self.assertContains(board, self.customer.name)
        self.assertNotContains(board, "Hidden Pipeline Client")
        self.assertEqual(board.context["open_count"], 1)
        self.assertEqual(update.status_code, 302)
        self.assertEqual(appointment.status, "IN_SERVICE")
        self.assertEqual(foreign_update.status_code, 404)
        self.assertEqual(completed_update.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "IN_SERVICE")

    def test_client_package_creation_and_redemption_track_session_history(self):
        purchase = Sale.objects.create(
            business=self.business,
            sale_number="PACKAGE-SALE-001",
            customer=self.customer,
            customer_name=self.customer.name,
            subtotal=3000,
            total=3000,
            amount_paid=3000,
            created_by=self.owner,
        )
        create_response = self.client.post(reverse("salon:client_packages"), {
            "action": "create",
            "customer": str(self.customer.id),
            "name": "Wash bundle",
            "services": [str(self.service.id)],
            "sessions_total": "3",
            "purchased_at": timezone.localdate().isoformat(),
            "expires_at": (timezone.localdate() + timedelta(days=60)).isoformat(),
            "purchase_sale": str(purchase.id),
            "notes": "Three visits",
        })
        package = SalonClientPackage.objects.get(business=self.business)
        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(package.customer, self.customer)
        self.assertEqual(package.purchase_sale, purchase)
        self.assertEqual(list(package.services.all()), [self.service])
        self.assertEqual(package.sessions_remaining, 3)

        appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            stylist=self.stylist,
            starts_at=timezone.now(),
            duration_min=45,
            status="IN_SERVICE",
        )
        appointment.services.add(self.service)
        redeem_response = self.client.post(reverse("salon:client_packages"), {
            "action": "redeem",
            "client_package": str(package.id),
            "service": str(self.service.id),
            "appointment": str(appointment.id),
            "notes": "Visit one",
        })
        duplicate_response = self.client.post(reverse("salon:client_packages"), {
            "action": "redeem",
            "client_package": str(package.id),
            "service": str(self.service.id),
            "appointment": str(appointment.id),
            "notes": "Duplicate visit",
        })
        package.refresh_from_db()
        redemption = SalonPackageRedemption.objects.get(client_package=package)
        page = self.client.get(reverse("salon:client_packages"))

        self.assertEqual(redeem_response.status_code, 302)
        self.assertEqual(package.sessions_redeemed, 1)
        self.assertEqual(package.sessions_remaining, 2)
        self.assertEqual(redemption.appointment, appointment)
        self.assertEqual(redemption.service, self.service)
        self.assertEqual(redemption.redeemed_by, self.owner)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(package.redemptions.count(), 1)
        self.assertContains(page, "Wash bundle")
        self.assertContains(page, "Recent redemptions")
        self.assertEqual(page.context["usable_count"], 1)

    def test_client_package_forms_reject_foreign_sale_and_expired_redemption(self):
        package = SalonClientPackage.objects.create(
            business=self.business,
            customer=self.customer,
            name="Expired bundle",
            sessions_total=2,
            purchased_at=timezone.localdate() - timedelta(days=50),
            expires_at=timezone.localdate() - timedelta(days=1),
            created_by=self.owner,
        )
        package.services.add(self.service)
        foreign_business = Business.objects.create(
            name="Other Package Salon",
            business_type="SALON",
            email="other-package@example.com",
            phone_number="0700000003",
        )
        foreign_sale = Sale.objects.create(
            business=foreign_business,
            sale_number="FOREIGN-PACKAGE-SALE",
            customer_name="Someone Else",
            subtotal=100,
            total=100,
        )

        invalid_sale_response = self.client.post(reverse("salon:client_packages"), {
            "action": "create",
            "customer": str(self.customer.id),
            "name": "Invalid purchase linkage",
            "services": [str(self.service.id)],
            "sessions_total": "2",
            "purchased_at": timezone.localdate().isoformat(),
            "expires_at": "",
            "purchase_sale": str(foreign_sale.id),
            "notes": "",
        })
        expired_redemption_response = self.client.post(reverse("salon:client_packages"), {
            "action": "redeem",
            "client_package": str(package.id),
            "service": str(self.service.id),
            "appointment": "",
            "notes": "",
        })

        package.refresh_from_db()
        self.assertEqual(invalid_sale_response.status_code, 200)
        self.assertEqual(expired_redemption_response.status_code, 200)
        self.assertEqual(SalonClientPackage.objects.filter(business=self.business).count(), 1)
        self.assertEqual(package.sessions_redeemed, 0)
        self.assertFalse(package.redemptions.exists())

    def test_service_and_client_forms_create_business_scoped_records(self):
        service_response = self.client.post(reverse("salon:services"), {
            "name": "Colour consultation",
            "price": "500",
            "duration_min": "30",
            "description": "Initial consultation",
        })
        client_response = self.client.post(reverse("salon:clients"), {
            "name": "New Client",
            "phone": "0700000002",
            "email": "newclient@example.com",
            "address": "",
            "notes": "",
            "is_active": "on",
        })
        services_page = self.client.get(reverse("salon:services"))
        clients_page = self.client.get(reverse("salon:clients"))

        self.assertEqual(service_response.status_code, 302)
        self.assertTrue(Product.objects.filter(
            business=self.business,
            name="Colour consultation",
            metadata__salon_service=True,
            metadata__duration_min=30,
        ).exists())
        self.assertEqual(client_response.status_code, 302)
        self.assertTrue(Customer.objects.filter(
            business=self.business,
            name="New Client",
            is_active=True,
        ).exists())
        self.assertContains(services_page, "Colour consultation")
        self.assertContains(clients_page, "New Client")

    def test_appointment_checkout_prefills_and_completes_sale(self):
        appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            stylist=self.stylist,
            starts_at=timezone.now(),
            duration_min=45,
            status="CHECKED_IN",
        )
        appointment.services.add(self.service)
        self.service.current_stock = 5
        self.service.save(update_fields=["current_stock"])
        retail_product = Product.objects.create(
            business=self.business,
            name="Conditioner",
            sku="SALON-RETAIL-001",
            selling_price=300,
            current_stock=8,
            created_by=self.owner,
        )

        checkout_page = self.client.get(
            reverse("sales:create"),
            {"appointment": str(appointment.id)},
        )
        self.assertEqual(checkout_page.status_code, 200)
        self.assertContains(checkout_page, str(appointment.id))
        self.assertContains(checkout_page, "Amina Client")
        self.assertEqual(checkout_page.context["form"].initial["customer"], self.customer.id)
        self.assertEqual(checkout_page.context["form"].initial["served_by"], self.stylist.id)
        self.assertContains(
            checkout_page,
            f'data-name="Amina Client" data-phone="0712345678" data-email="" selected',
        )
        self.assertEqual(checkout_page.context["formset"].forms[0].initial["product"], self.service.name)
        self.assertEqual(checkout_page.context["formset"].initial_form_count(), 0)
        self.assertEqual(
            checkout_page.context["formset"].forms[0].initial["unit_price"],
            self.service.selling_price,
        )

        response = self.client.post(reverse("sales:create"), {
            "appointment_id": str(appointment.id),
            "customer": str(self.customer.id),
            "customer_name": self.customer.name,
            "customer_phone": self.customer.phone,
            "customer_email": "",
            "payment_method": "CASH",
            "discount": "0",
            "transaction_code": "",
            "served_by": str(self.stylist.id),
            "notes": "",
            "delivery_address": "",
            "delivery_date": "",
            "sale_items-TOTAL_FORMS": "2",
            "sale_items-INITIAL_FORMS": "0",
            "sale_items-MIN_NUM_FORMS": "1",
            "sale_items-MAX_NUM_FORMS": "1000",
            "sale_items-0-product": self.service.name,
            "sale_items-0-quantity": "1",
            "sale_items-0-unit_price": "1200",
            "sale_items-1-product": retail_product.name,
            "sale_items-1-quantity": "1",
            "sale_items-1-unit_price": "300",
        })

        self.assertEqual(response.status_code, 302, response.context)
        sale = Sale.objects.get(business=self.business)
        appointment.refresh_from_db()
        self.service.refresh_from_db()
        retail_product.refresh_from_db()
        self.assertRedirects(response, reverse("sales:detail", kwargs={"sale_id": sale.id}))
        self.assertEqual(appointment.status, "COMPLETED")
        self.assertEqual(appointment.sale, sale)
        self.assertEqual(sale.customer, self.customer)
        self.assertEqual(sale.metadata["served_by"]["id"], str(self.stylist.id))
        self.assertEqual(sale.sale_items.count(), 2)
        self.assertEqual(self.service.current_stock, 5)
        self.assertEqual(retail_product.current_stock, 7)

    def test_salon_checkout_rejects_foreign_and_not_ready_appointments(self):
        foreign_business = Business.objects.create(
            name="Other Salon",
            business_type="SALON",
            email="other-salon@example.com",
            phone_number="0700000001",
        )
        foreign_appointment = SalonAppointment.objects.create(
            business=foreign_business,
            client_name="Private Client",
            starts_at=timezone.now(),
            duration_min=30,
            status="CHECKED_IN",
        )
        booked_appointment = SalonAppointment.objects.create(
            business=self.business,
            customer=self.customer,
            starts_at=timezone.now(),
            duration_min=45,
            status="BOOKED",
        )

        foreign_response = self.client.get(
            reverse("sales:create"),
            {"appointment": str(foreign_appointment.id)},
        )
        not_ready_response = self.client.get(
            reverse("sales:create"),
            {"appointment": str(booked_appointment.id)},
        )
        foreign_post = self.client.post(reverse("sales:create"), {
            "appointment_id": str(foreign_appointment.id),
            "customer": "",
            "customer_name": "",
            "customer_phone": "",
            "customer_email": "",
            "payment_method": "CASH",
            "discount": "0",
            "transaction_code": "",
            "served_by": "",
            "notes": "",
            "delivery_address": "",
            "delivery_date": "",
            "sale_items-TOTAL_FORMS": "1",
            "sale_items-INITIAL_FORMS": "0",
            "sale_items-MIN_NUM_FORMS": "1",
            "sale_items-MAX_NUM_FORMS": "1000",
            "sale_items-0-product": self.service.name,
            "sale_items-0-quantity": "1",
            "sale_items-0-unit_price": "1200",
        })

        self.assertEqual(foreign_response.status_code, 404)
        self.assertEqual(not_ready_response.status_code, 404)
        self.assertEqual(foreign_post.status_code, 200)
        self.assertNotContains(foreign_post, "Private Client")
        self.assertFalse(Sale.objects.filter(business=self.business).exists())
        foreign_appointment.refresh_from_db()
        self.assertEqual(foreign_appointment.status, "CHECKED_IN")
        self.assertIsNone(foreign_appointment.sale)
