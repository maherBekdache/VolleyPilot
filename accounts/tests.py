from django.test import TestCase
from django.urls import reverse

from accounts.models import Club, User
from teams.models import Player, Team, TeamMembership


class RegistrationFlowTests(TestCase):
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
        self.player = Player.objects.create(
            team=self.team,
            email='player@example.com',
            name='Emma Davis',
            jersey_number=1,
            position='Setter',
        )

    def test_registration_links_existing_player_profile(self):
        response = self.client.post(reverse('register'), {
            'first_name': 'Emma',
            'last_name': 'Davis',
            'email': 'player@example.com',
            'password1': 'strong-pass-123',
            'password2': 'strong-pass-123',
        })

        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(email='player@example.com')
        self.player.refresh_from_db()
        self.assertEqual(user.role, 'player')
        self.assertEqual(self.player.user, user)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=user, role='player').exists())
