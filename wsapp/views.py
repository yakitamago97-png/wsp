from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Condition, Feeling, PhysicalCondition, Task, WorkRecord


# ---------------------------------------------------------------
# 認証（ログイン・ログアウト）
# ---------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect('wsapp:03-top')

    if request.method == 'POST':
        employee_id = request.POST.get('emp_id', '').strip()
        password = request.POST.get('password', '')

        # USERNAME_FIELD = 'id' なので username に従業員IDを渡す
        user = authenticate(request, username=employee_id, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'{user.full_name} さん、ログインしました。')
            return redirect('wsapp:03-top')
        messages.error(request, '従業員IDまたはパスワードが正しくありません。')

    return render(request, '01-login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'ログアウトしました。')
    return redirect('wsapp:01-login')


# ---------------------------------------------------------------
# ダッシュボード / トップ（本日の勤怠・コンディション・タスク一覧）
# ---------------------------------------------------------------
@login_required
def dashboard(request):
    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()

    recent_conditions = (
        Condition.objects.filter(employee=request.user)
        .select_related('physical_condition', 'feeling')
        .order_by('-date')[:5]
    )

    my_tasks = Task.objects.filter(employee=request.user).order_by('deadline', 'id')

    context = {
        'today': today,
        'today_record': today_record,
        'recent_conditions': recent_conditions,
        'my_tasks': my_tasks,
    }
    return render(request, '03-top.html', context)


# ---------------------------------------------------------------
# 勤怠打刻（出勤・退勤）・修正
# ---------------------------------------------------------------
@login_required
def clock_in(request):
    if request.method != 'POST':
        return redirect('wsapp:03-top')

    today = timezone.localdate()
    now = timezone.now()

    latest_condition = (
        Condition.objects.filter(employee=request.user, date__date=today)
        .order_by('-date')
        .first()
    )

    try:
        WorkRecord.objects.create(
            employee=request.user,
            working_date=today,
            clock_in=now,
            condition=latest_condition,
        )
        messages.success(
            request,
            f'出勤打刻が完了しました（{timezone.localtime(now):%H:%M}）。',
        )
    except IntegrityError:
        messages.warning(request, '本日の出勤記録はすでに登録されています。')

    return redirect('wsapp:03-top')


@login_required
def clock_out(request):
    if request.method != 'POST':
        return redirect('wsapp:03-top')

    today = timezone.localdate()
    record = get_object_or_404(WorkRecord, employee=request.user, working_date=today)

    if record.clock_out is not None:
        messages.warning(request, '本日の退勤打刻はすでに完了しています。')
    else:
        now = timezone.now()
        record.clock_out = now
        record.save(update_fields=['clock_out'])
        messages.success(
            request,
            f'退勤打刻が完了しました（{timezone.localtime(now):%H:%M}）。',
        )

    return redirect('wsapp:03-top')


@login_required
def attendance_view(request):
    if request.method == 'POST':
        return clock_in(request)

    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()
    return render(request, '04-attendance.html', {'today_record': today_record})


@login_required
def leaving_work_view(request):
    if request.method == 'POST':
        return clock_out(request)

    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()
    return render(request, '05-leaving-work.html', {'today_record': today_record})


@login_required
def edit_work_record(request, record_id):
    record = get_object_or_404(WorkRecord, pk=record_id, employee=request.user)

    if request.method == 'POST':
        clock_in_str = request.POST.get('clock_in', '').strip()
        clock_out_str = request.POST.get('clock_out', '').strip()
        change_reason = request.POST.get('change_reason', '').strip()

        if not change_reason:
            messages.error(request, '出退勤を修正する場合は変更理由を入力してください。')
            return render(request, '18-clock-in-update.html', {'record': record})

        if clock_in_str:
            parsed_in = timezone.datetime.fromisoformat(clock_in_str)
            if timezone.is_naive(parsed_in):
                parsed_in = timezone.make_aware(parsed_in)
            record.clock_in = parsed_in

        if clock_out_str:
            parsed_out = timezone.datetime.fromisoformat(clock_out_str)
            if timezone.is_naive(parsed_out):
                parsed_out = timezone.make_aware(parsed_out)
            record.clock_out = parsed_out
        else:
            record.clock_out = None

        record.change_reason = change_reason
        record.save()
        messages.success(request, '勤務記録を更新しました。')
        return redirect('wsapp:03-top')

    return render(request, '18-clock-in-update.html', {'record': record})


# ---------------------------------------------------------------
# コンディション登録・履歴
# ---------------------------------------------------------------
@login_required
def condition_create(request):
    physical_conditions = PhysicalCondition.objects.order_by('id')
    feelings = Feeling.objects.order_by('id')

    if request.method == 'POST':
        sleep_raw = request.POST.get('sleep_time', '').strip()
        physical_id = request.POST.get('physical_condition', '').strip()
        feeling_id = request.POST.get('feeling', '').strip()

        physical = get_object_or_404(PhysicalCondition, pk=physical_id)
        feeling = get_object_or_404(Feeling, pk=feeling_id)

        sleep_time = None
        if sleep_raw:
            try:
                sleep_time = float(sleep_raw)
            except ValueError:
                messages.error(request, '睡眠時間は数値で入力してください。')
                return render(
                    request,
                    '06-condition-create.html',
                    {
                        'physical_conditions': physical_conditions,
                        'feelings': feelings,
                    },
                )

        condition = Condition.objects.create(
            employee=request.user,
            sleep_time=sleep_time,
            physical_condition=physical,
            feeling=feeling,
        )

        # 本日の勤務記録があれば最新のコンディションを紐付け
        today_record = WorkRecord.objects.filter(
            employee=request.user,
            working_date=timezone.localdate(),
        ).first()
        if today_record is not None:
            today_record.condition = condition
            today_record.save(update_fields=['condition'])

        messages.success(request, 'コンディションを登録しました。')
        return redirect('wsapp:03-top')

    context = {
        'physical_conditions': physical_conditions,
        'feelings': feelings,
    }
    return render(request, '06-condition-create.html', context)


# ---------------------------------------------------------------
# タスク一覧・ステータス更新・管理者確認
# ---------------------------------------------------------------
@login_required
def task_list(request):
    if request.user.authority:
        tasks = Task.objects.select_related('employee').order_by('is_completed', 'deadline', 'id')
    else:
        tasks = Task.objects.filter(employee=request.user).order_by('is_completed', 'deadline', 'id')

    return render(
        request,
        '16-task-list.html',
        {
            'tasks': tasks,
            'status_choices': Task.Status.choices,
        },
    )


@login_required
def task_update_status(request, task_id):
    if request.method != 'POST':
        return redirect('wsapp:16-task-list')

    task = get_object_or_404(Task, pk=task_id)
    if task.employee != request.user and not request.user.authority:
        raise PermissionDenied('このタスクを更新する権限がありません。')

    new_status = request.POST.get('status', '')
    valid_statuses = {choice[0] for choice in Task.Status.choices}
    if new_status not in valid_statuses:
        messages.error(request, '不正なステータスが選択されました。')
        return redirect('wsapp:16-task-list')

    task.status = new_status
    task.save(update_fields=['status'])
    messages.success(request, f'「{task.task_name}」のステータスを {new_status} に更新しました。')
    return redirect('wsapp:16-task-list')


@login_required
def task_toggle_complete(request, task_id):
    if request.method != 'POST':
        return redirect('wsapp:16-task-list')

    if not request.user.authority:
        raise PermissionDenied('完了フラグを変更できるのは管理者のみです。')

    task = get_object_or_404(Task, pk=task_id)
    task.is_completed = not task.is_completed
    task.save(update_fields=['is_completed'])
    state_label = '完了確認済み' if task.is_completed else '未完了確認'
    messages.success(request, f'「{task.task_name}」を {state_label} にしました。')
    return redirect('wsapp:16-task-list')







# ---------------------------------------------------------------
# urls.py 対応用ビュー(仮)
# ---------------------------------------------------------------
def error_view(request):
    return render(request, '00-error.html')


def index_view(request):
    return dashboard(request)


@login_required
def condition_judgement_view(request, pk):
    condition = get_object_or_404(Condition, pk=pk, employee=request.user)
    return render(request, '07-condition-judgement.html', {'condition': condition})


@login_required
def condition_update_view(request, pk):
    condition = get_object_or_404(Condition, pk=pk, employee=request.user)
    return render(request, '08-condition-update.html', {'condition': condition})


@login_required
def condition_list_view(request):
    conditions = (
        Condition.objects.filter(employee=request.user)
        .select_related('physical_condition', 'feeling')
        .order_by('-date')
    )
    return render(request, '13-condition-list.html', {'conditions': conditions})


@login_required
def working_history_view(request):
    records = WorkRecord.objects.filter(employee=request.user).order_by('-working_date')
    return render(request, '09-working-history.html', {'records': records})


@login_required
def employee_create_view(request):
    return render(request, '10-employee-create.html')


@login_required
def employee_update_view(request, pk):
    return render(request, '11-employee-update.html', {'pk': pk})


@login_required
def employee_list_view(request):
    return render(request, '12-employee-list.html')


@login_required
def task_create_view(request):
    return render(request, '14-task-create.html')


@login_required
def task_update_view(request, pk):
    task = get_object_or_404(Task, pk=pk)
    return render(request, '15-task-update.html', {'task': task})


def task_list_view(request):
    return task_list(request)


def task_check_view(request, pk):
    return task_toggle_complete(request, pk)


@login_required
def clock_in_list_view(request):
    records = WorkRecord.objects.select_related('employee').order_by('-working_date', '-id')
    return render(request, '17-clock-in-list.html', {'records': records})


def clock_in_update_view(request, pk):
    return edit_work_record(request, pk)


@login_required
def password_update_view(request):
    return render(request, '20-password-update.html')