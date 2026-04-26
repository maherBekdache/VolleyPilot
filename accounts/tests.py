from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.core import mail

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


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='noreply@volleypilot.test',
)
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='demo12345',
            role='manager',
        )

    def test_password_reset_sends_email(self):
        response = self.client.post(reverse('password_reset'), {'email': 'manager@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].body.lower())
        self.assertIn('manager@example.com', mail.outbox[0].to)
