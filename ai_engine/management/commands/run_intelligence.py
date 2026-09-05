from django.core.management.base import BaseCommand, CommandError

from businesses.models import Business
from ai_engine.services import run_intelligence_pipeline, run_sales_forecast


class Command(BaseCommand):
    help = "Run SmartBiz AI feature engineering, insight scoring, recommendations, and optional forecasts."

    def add_arguments(self, parser):
        parser.add_argument("--business", type=str, help="Business UUID. Defaults to every active business.")
        parser.add_argument("--forecast", action="store_true", help="Also generate the daily sales forecast.")
        parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon in days.")

    def handle(self, *args, **options):
        businesses = Business.objects.filter(is_active=True)
        if options["business"]:
            businesses = businesses.filter(id=options["business"])
            if not businesses.exists():
                raise CommandError("No active business matches the supplied UUID.")

        total_insights = 0
        total_forecasts = 0
        for business in businesses.iterator():
            created = run_intelligence_pipeline(business)
            total_insights += len(created)
            if options["forecast"]:
                run_sales_forecast(business, horizon_days=options["horizon"])
                total_forecasts += 1
            self.stdout.write(self.style.SUCCESS(
                f"{business.name}: {len(created)} ranked insights generated"
                + (" and forecast updated" if options["forecast"] else "")
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Completed AI engine run: {total_insights} insights, {total_forecasts} forecasts."
        ))
