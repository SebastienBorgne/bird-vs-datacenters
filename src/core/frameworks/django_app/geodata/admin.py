from django.contrib import admin

from .models import BirdObservationModel, DatacenterModel


@admin.register(BirdObservationModel)
class BirdObservationAdmin(admin.ModelAdmin):
    list_display = ("observation_id", "common_name", "scientific_name", "observed_on")
    list_filter = ("observed_on",)
    search_fields = ("common_name", "scientific_name")


@admin.register(DatacenterModel)
class DatacenterAdmin(admin.ModelAdmin):
    list_display = ("name", "operator", "opened_on", "latitude", "longitude")
    list_filter = ("opened_on",)
    search_fields = ("name", "operator", "external_id")
