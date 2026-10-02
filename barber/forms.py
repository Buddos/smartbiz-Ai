from django import forms
from django.db.models import Q

from .models import BarberGoal, BarberShift, Chair
from accounts.models import User


class BarberGoalForm(forms.ModelForm):
    class Meta:
        model = BarberGoal
        fields = ["metric", "target"]
        widgets = {
            "metric": forms.Select(attrs={"class": "input-field"}),
            "target": forms.NumberInput(attrs={"class": "input-field", "min": 1, "step": "1"}),
        }


class BarberShiftForm(forms.ModelForm):
    class Meta:
        model = BarberShift
        fields = ["barber", "chair", "shift_date", "start_time", "end_time", "is_day_off"]
        widgets = {
            "barber": forms.Select(attrs={"class": "input-field"}),
            "chair": forms.Select(attrs={"class": "input-field"}),
            "shift_date": forms.DateInput(attrs={"class": "input-field", "type": "date"}),
            "start_time": forms.TimeInput(attrs={"class": "input-field", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "input-field", "type": "time"}),
            "is_day_off": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business")
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["barber"].queryset = User.objects.filter(
            business=business, role="BARBER", is_active=True
        ).order_by("first_name", "last_name")
        self.fields["chair"].queryset = Chair.objects.filter(business=business, is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_time")
        end = cleaned_data.get("end_time")
        if start and end and start >= end:
            self.add_error("end_time", "Shift end must be later than its start.")
        barber = cleaned_data.get("barber")
        chair = cleaned_data.get("chair")
        shift_date = cleaned_data.get("shift_date")
        if start and end and start < end and barber and chair and shift_date:
            conflicts = BarberShift.objects.filter(
                business=self.business,
                shift_date=shift_date,
                start_time__lt=end,
                end_time__gt=start,
            ).filter(Q(barber=barber) | Q(chair=chair))
            if self.instance.pk:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            if conflicts.exists():
                self.add_error(None, "This barber or chair already has an overlapping shift.")
        return cleaned_data
