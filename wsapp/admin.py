from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Company,
    Condition,
    Feeling,
    PhysicalCondition,
    Task,
    User,
    WorkRecord,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('id', 'company_name', 'tel', 'email', 'prefecture', 'city')
    search_fields = ('company_name', 'email', 'tel', 'city', 'address_line1')
    list_filter = ('prefecture',)
    ordering = ('id',)


@admin.register(PhysicalCondition)
class PhysicalConditionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(Feeling)
class FeelingAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'id',
        'full_name',
        'last_name',
        'given_name',
        'email',
        'company',
        'authority',
        'is_active',
        'is_superuser',
    )
    list_filter = ('authority', 'is_active', 'is_superuser', 'company')
    search_fields = ('id', 'last_name', 'given_name', 'email')
    ordering = ('id',)
    readonly_fields = ('id', 'last_login')

    fieldsets = (
        ('従業員情報', {'fields': ('id', 'last_name', 'given_name', 'email', 'company')}),
        ('パスワード', {'fields': ('password',)}),
        (
            '権限・ステータス',
            {
                'fields': (
                    'authority',
                    'is_active',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                )
            },
        ),
        ('ログイン履歴', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'last_name',
                    'given_name',
                    'email',
                    'company',
                    'authority',
                    'is_active',
                    'password1',
                    'password2',
                ),
            },
        ),
    )


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'employee',
        'date',
        'sleep_time',
        'physical_condition',
        'feeling',
        'ai_judgement',
    )
    list_filter = ('physical_condition', 'feeling', 'ai_judgement', 'date')
    search_fields = ('employee__last_name', 'employee__given_name', 'employee__id', 'ai_judgement')
    raw_id_fields = ('employee',)
    date_hierarchy = 'date'
    ordering = ('-date', '-id')


@admin.register(WorkRecord)
class WorkRecordAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'employee',
        'working_date',
        'clock_in',
        'clock_out',
        'condition',
        'change_reason',
    )
    list_filter = ('working_date', 'employee__company')
    search_fields = (
        'employee__last_name',
        'employee__given_name',
        'employee__id',
        'change_reason',
    )
    raw_id_fields = ('employee', 'condition')
    date_hierarchy = 'working_date'
    ordering = ('-working_date', '-id')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'task_name',
        'employee',
        'status',
        'deadline',
        'is_completed',
    )
    list_filter = ('status', 'is_completed', 'deadline', 'employee__company')
    search_fields = ('task_name', 'detail', 'employee__last_name', 'employee__given_name')
    raw_id_fields = ('employee',)
    list_editable = ('status', 'is_completed')
    ordering = ('is_completed', 'deadline', 'id')