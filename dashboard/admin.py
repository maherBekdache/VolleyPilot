from django.contrib import admin

from .models import MLTrainingSample


@admin.register(MLTrainingSample)
class MLTrainingSampleAdmin(admin.ModelAdmin):
    list_display = ('sample_id', 'team_hash', 'opponent_hash', 'is_encrypted', 'updated_at')
    list_filter = ('is_encrypted', 'updated_at')
    search_fields = ('sample_id', 'team_hash', 'opponent_hash')
    readonly_fields = ('created_at', 'updated_at')
