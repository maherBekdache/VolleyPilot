from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Drill, PracticeDrill, DrillObservation
from .forms import DrillForm, DrillObservationForm
from schedule.models import Practice
from teams.views import get_user_team


@login_required
def drill_list_view(request):
    drills = Drill.objects.all()
    search = request.GET.get('search', '')
    category = request.GET.get('category', 'all')
    difficulty = request.GET.get('difficulty', 'all')
    if search:
        drills = drills.filter(name__icontains=search)
    if category != 'all':
        drills = drills.filter(category=category)
    if difficulty != 'all':
        drills = drills.filter(difficulty=difficulty)
    return render(request, 'drills/drill_list.html', {
        'drills': drills, 'search': search,
        'category': category, 'difficulty': difficulty,
    })


@login_required
def drill_create_view(request):
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('drill_list')
    if request.method == 'POST':
        form = DrillForm(request.POST)
        if form.is_valid():
            drill = form.save(commit=False)
            drill.created_by = request.user
            drill.save()
            messages.success(request, f'Drill "{drill.name}" created.')
            return redirect('drill_list')
    else:
        form = DrillForm()
    return render(request, 'drills/drill_form.html', {'form': form, 'action': 'Create'})


@login_required
def drill_edit_view(request, pk):
    drill = get_object_or_404(Drill, pk=pk)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('drill_list')
    if request.method == 'POST':
        form = DrillForm(request.POST, instance=drill)
        if form.is_valid():
            form.save()
            messages.success(request, 'Drill updated.')
            return redirect('drill_list')
    else:
        form = DrillForm(instance=drill)
    return render(request, 'drills/drill_form.html', {'form': form, 'action': 'Edit'})


@login_required
def assign_drill_view(request, practice_id):
    team = get_user_team(request.user)
    practice = get_object_or_404(Practice, pk=practice_id, team=team)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('practice_detail', pk=practice_id)
    if request.method == 'POST':
        drill_id = request.POST.get('drill_id')
        drill = get_object_or_404(Drill, pk=drill_id)
        order = practice.practice_drills.count() + 1
        PracticeDrill.objects.create(
            practice=practice, drill=drill, order=order,
            planned_duration=drill.duration
        )
        messages.success(request, f'"{drill.name}" added to practice.')
        return redirect('practice_detail', pk=practice_id)
    drills = Drill.objects.all()
    return render(request, 'drills/assign_drill.html', {
        'practice': practice, 'drills': drills,
    })


@login_required
def remove_drill_from_practice_view(request, pk):
    pd = get_object_or_404(PracticeDrill, pk=pk)
    practice_id = pd.practice.pk
    if request.method == 'POST' and request.user.is_staff_role:
        pd.delete()
        messages.success(request, 'Drill removed from practice.')
    return redirect('practice_detail', pk=practice_id)


@login_required
def drill_observation_view(request, practice_id):
    team = get_user_team(request.user)
    practice = get_object_or_404(Practice, pk=practice_id, team=team)
    practice_drills = practice.practice_drills.select_related('drill')
    if request.method == 'POST' and request.user.is_staff_role:
        for pd in practice_drills:
            obs, _ = DrillObservation.objects.get_or_create(practice_drill=pd)
            obs.was_performed = request.POST.get(f'performed_{pd.id}') == 'on'
            obs.actual_duration = request.POST.get(f'duration_{pd.id}', '')
            obs.notes = request.POST.get(f'notes_{pd.id}', '')
            rating = request.POST.get(f'rating_{pd.id}')
            obs.rating = int(rating) if rating else None
            obs.save()
        messages.success(request, 'Observations saved.')
        return redirect('practice_detail', pk=practice_id)
    return render(request, 'drills/observations.html', {
        'practice': practice, 'practice_drills': practice_drills,
    })

