from django.urls import path
from . import views

app_name = 'wsapp'

urlpatterns = [
    # 00: エラー
    path('error/', views.error_view, name='00-error'),

    # 01 / 02: ログイン・ログアウト
    path('login/', views.login_view, name='01-login'),
    path('logout/', views.logout_view, name='02-logout'),

    # 03: トップ
    path('', views.index_view, name='03-top'),

    # 04 / 05: 出勤・退勤打刻
    path('attendance/', views.attendance_view, name='04-attendance'),
    path('leaving-work/', views.leaving_work_view, name='05-leaving-work'),

    # 06 / 07 / 08: コンディション登録・AI判定・編集
    path('condition/create/', views.condition_create, name='06-condition-create'),
    path('condition/<int:pk>/judgement/', views.condition_judgement_view, name='07-condition-judgement'),
    path('condition/<int:pk>/update/', views.condition_update_view, name='08-condition-update'),

    # 09: 勤務履歴
    path('working-history/', views.working_history_view, name='09-working-history'),
    path('working-history/api/', views.working_history_api, name='09-working-history-api'),

    # 10 / 11 / 12: 従業員登録・編集・一覧
    path('employee/create/', views.employee_create_view, name='10-employee-create'),
    path('employee/<int:pk>/update/', views.employee_update_view, name='11-employee-update'),
    path('employee/list/', views.employee_list_view, name='12-employee-list'),

    # 13: コンディション一覧
    path('condition/list/', views.condition_list_view, name='13-condition-list'),

    # 14 / 15 / 16: タスク作成・更新・一覧
    path('task/create/', views.task_create_view, name='14-task-create'),
    path('task/<int:pk>/update/', views.task_update_view, name='15-task-update'),
    path('task/list/', views.task_list_view, name='16-task-list'),
    path('task/<int:pk>/complete/', views.task_complete_view, name='task-complete'),

    # 17 / 18: 打刻一覧・打刻修正
    path('clock-in/list/', views.clock_in_list_view, name='17-clock-in-list'),
    path('clock-in/<int:pk>/update/', views.clock_in_update_view, name='18-clock-in-update'),

    # 19: タスク完了確認
    path('task/<int:pk>/check/', views.task_check_view, name='19-task-check'),

    # 20: パスワード変更
    path('password/update/', views.password_update_view, name='20-password-update'),
]