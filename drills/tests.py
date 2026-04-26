from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from accounts.models import Club, User
from drills.models import Drill, DrillObservation, PracticeDrill
from schedule.models import Practice
from teams.models import Team, TeamMembership


class DrillWorkflowTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name='AUB Volleyball Club')
        self.coach = User.objects.create_user(
            username='coach@example.com',
            email='coach@example.com',
            password='demo12345',
            role='coach',
            club=self.club,
        )
        self.team = Team.objects.create(
            name='AUB Eagles',
            age_group='U18',
            club_affiliation='AUB Volleyball Club',
            created_by=self.coach,
        )
        TeamMembership.objects.create(team=self.team, user=self.coach, role='coach')
        self.practice = Practice.objects.create(
            team=self.team,
            date=date.today(),
            time=time(16, 0),
            location='AUB Gym',
            focus='Serve Receive',
            created_by=self.coach,
        )

    def test_create_assign_and_record_drill_observations(self):
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.post(reverse('drill_create'), {
            'name': 'Target Serving',
            'category': 'Serving',
            'duration': '20',
            'players_needed': '6',
            'difficulty': 'intermediate',
            'description': 'Serve to specific zones.',
        })
        self.assertRedirects(response, reverse('drill_list'))
        drill = Drill.objects.get(name='Target Serving')

        response = self.client.post(reverse('assign_drill', args=[self.practice.pk]), {'drill_id': drill.pk})
        self.assertRedirects(response, reverse('practice_detail', args=[self.practice.pk]))
        practice_drill = PracticeDrill.objects.get(practice=self.practice, drill=drill)

        response = self.client.post(reverse('drill_observations', args=[self.practice.pk]), {
            f'performed_{practice_drill.pk}': 'on',
            f'duration_{practice_drill.pk}': '18',
            f'rating_{practice_drill.pk}': '4',
            f'notes_{practice_drill.pk}': 'Good serving rhythm',
        })
        self.assertRedirects(response, reverse('practice_detail', args=[self.practice.pk]))
        observation = DrillObservation.objects.get(practice_drill=practice_drill)
        self.assertTrue(observation.was_performed)
        self.assertEqual(observation.actual_duration, '18')
        self.assertEqual(observation.rating, 4)
