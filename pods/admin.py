from django.contrib import admin
from .models import Pod, PodMember, ApprenticeOversight
# Register your models here.

class podMemberInline(admin.TabularInline):
    model = PodMember
    extra = 1

@admin.register(Pod)
class PodAdmin(admin.ModelAdmin):
    list_display = ('name', 'leader', 'created_at')
    search_fields = ('name', 'leader__username')
    inlines = [podMemberInline]

@admin.register(PodMember)
class PodmemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'pod', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'Pod__name')

@admin.register(ApprenticeOversight)
class ApprenticeOversightAdmin(admin.ModelAdmin):
    list_display = ('mentor', 'apprentice_pod', 'created_at')
    