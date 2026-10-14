from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from businesses.models import Business
from reports.models import Report


class ReportPeriodTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Report Test Shop",
            business_type="RETAIL",
            email="reports@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="reports-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.owner)

    def test_generate_accepts_legacy_localized_date_parameters(self):
        response = self.client.get(
            reverse("reports:generate"),
            {
                "start": "Sept. 9, 2026",
                "end": "Oct. 9, 2026",
                "type": "PERFORMANCE",
            },
        )

        report = Report.objects.get(business=self.business)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(report.period_start.isoformat(), "2026-09-09")
        self.assertEqual(report.period_end.isoformat(), "2026-10-09")

    def test_report_list_shows_required_calendar_inputs_with_iso_dates(self):
        response = self.client.get(
            reverse("reports:list"),
            {"start": "Sept. 9, 2026", "end": "Oct. 9, 2026"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="date" name="start" value="2026-09-09" required')
        self.assertContains(response, 'type="date" name="end" value="2026-10-09" required')
        self.assertContains(response, "Generate performance report")
        self.assertNotContains(response, "Sept. 9, 2026")

    def test_generate_rejects_invalid_period_date(self):
        response = self.client.get(
            reverse("reports:generate"),
            {"start": "not-a-date"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Select both a start date and an end date.", status_code=400)
        self.assertFalse(Report.objects.filter(business=self.business).exists())

    def test_generate_requires_both_dates(self):
        response = self.client.get(
            reverse("reports:generate"),
            {"start": "2026-09-09"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Report.objects.filter(business=self.business).exists())

    def test_generate_rejects_start_date_after_end_date(self):
        response = self.client.get(
            reverse("reports:generate"),
            {"start": "2026-10-10", "end": "2026-10-09"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Report.objects.filter(business=self.business).exists())
