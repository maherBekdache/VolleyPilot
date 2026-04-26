from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from accounts.models import Club, User
from schedule.models import AvailabilityRequest, AvailabilityResponse, Match, Practice
from teams.models import Player, Team, TeamMembership


class ScheduleAndAvailabilityTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name='AUB Volleyball Club')
        self.coach = User.objects.create_user(
            username='coach@example.com',
            email='coach@example.com',
            password='demo12345',
            role='coach',
            club=self.club,
        )
        self.player_user = User.objects.create_user(
            username='player@example.com',
            email='player@example.com',
            password='demo12345',
            role='player',
            club=self.club,
        )
        self.other_user = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='demo12345',
            role='player',
            club=self.club,
        )
        self.team = Team.objects.create(
            name='AUB Eagles',
            age_group='U18',
            club_affiliation='AUB Volleyball Club',
            created_by=self.coach,
        )
        TeamMembership.objects.create(team=self.team, user=self.coach, role='coach')
        TeamMembership.objects.create(team=self.team, user=self.player_user, role='player')
        self.player = Player.objects.create(
            team=self.team,
            user=self.player_user,
            email='player@example.com',
            name='Emma Davis',
            jersey_number=1,
            position='Setter',
        )

    def test_practice_creation_and_availability_flow(self):
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.post(reverse('practice_create'), {
            'date': date.today().isoformat(),
            'time': time(16, 0).strftime('%H:%M'),
            'location': 'AUB Gym',
            'focus': 'Serve Receive',
        })
        self.assertRedirects(response, reverse('schedule'))
        practice = Practice.objects.get(team=self.team, focus='Serve Receive')

        response = self.client.get(reverse('request_availability', args=['practice', practice.pk]))
        self.assertRedirects(response, reverse('schedule'))
        request_obj = AvailabilityRequest.objects.get(practice=practice)
        response_obj = AvailabilityResponse.objects.get(request=request_obj, player=self.player)
        self.assertEqual(response_obj.status, 'pending')

        self.client.logout()
        self.client.login(username='player@example.com', password='demo12345')
        response = self.client.post(reverse('availability_respond', args=[response_obj.pk]), {'status': 'available'})
        self.assertRedirects(response, reverse('schedule'))
        response_obj.refresh_from_db()
        self.assertEqual(response_obj.status, 'available')

        self.client.logout()
        self.client.login(username='other@example.com', password='demo12345')
        response = self.client.post(reverse('availability_respond', args=[response_obj.pk]), {'status': 'maybe'})
        self.assertEqual(response.status_code, 302)
        response_obj.refresh_from_db()
        self.assertEqual(response_obj.status, 'available')

        self.client.logout()
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.get(reverse('availability_summary', args=['practice', practice.pk]))
        self.assertEqual(response.status_code, 200)

    def test_match_creation_uses_team_defaults(self):
        self.team.default_ruleset = 'best_of_3'
        self.team.default_substitution_limit = 9
        self.team.save(update_fields=['default_ruleset', 'default_substitution_limit'])
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.get(reverse('match_create'))
        self.assertContains(response, 'value="9"')
        self.assertContains(response, 'best_of_3')

        response = self.client.post(reverse('match_create'), {
            'title': 'Cup Match',
            'date': date.today().isoformat(),
            'time': time(18, 30).strftime('%H:%M'),
            'location': 'AUB Gym',
            'opponent': 'LAU Wolves',
            'is_home': 'on',
            'ruleset': 'best_of_3',
            'substitution_limit': 9,
        })
        self.assertRedirects(response, reverse('schedule'))
        match = Match.objects.get(team=self.team, title='Cup Match')
        self.assertEqual(match.ruleset, 'best_of_3')
        self.assertEqual(match.substitution_limit, 9)

    def test_schedule_page_includes_calendar_view(self):
        Match.objects.create(
            team=self.team,
            title='Calendar Match',
            date=date.today(),
            time=time(19, 0),
            location='AUB Gym',
            opponent='LAU Wolves',
            created_by=self.coach,
        )
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.get(reverse('schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monthly Calendar')
        self.assertContains(response, 'Calendar Match')
