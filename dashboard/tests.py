from django.test import TestCase
from django.urls import reverse

from accounts.models import Club, User
from matches.models import Action, LiveMatch, SetScore
from schedule.models import Match
from teams.models import Player, Team, TeamMembership


class DashboardExportTests(TestCase):
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
        self.player = Player.objects.create(team=self.team, name='Emma Davis', jersey_number=1, position='Setter')
        match = Match.objects.create(
            team=self.team,
            title='Conference Match',
            date='2026-04-01',
            time='18:00',
            location='AUB Gym',
            opponent='LAU Wolves',
            is_home=True,
            created_by=self.coach,
            status='completed',
        )
        live = LiveMatch.objects.create(match=match, is_active=False)
        SetScore.objects.create(live_match=live, set_number=1, our_score=25, opponent_score=18, is_complete=True)
        Action.objects.create(live_match=live, action_type='point_won', set_number=1, rotation=1, data={'our_score': 1, 'opponent_score': 0})

    def test_csv_and_pdf_exports(self):
        self.client.login(username='coach@example.com', password='demo12345')
        csv_response = self.client.get(reverse('export_stats_csv'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response['Content-Type'], 'text/csv')

        pdf_response = self.client.get(reverse('export_stats_pdf'))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
