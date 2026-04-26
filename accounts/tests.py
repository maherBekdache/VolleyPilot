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

    def test_login_page_authenticates_registered_user(self):
        user = User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='demo12345',
            role='manager',
        )
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'Sign In')
        response = self.client.post(reverse('login'), {
            'username': user.email,
            'password': 'demo12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('dashboard')))
        follow_response = self.client.get(reverse('profile'))
        self.assertEqual(follow_response.status_code, 200)

    def test_profile_page_updates_information_and_password(self):
        user = User.objects.create_user(
            username='assistant@example.com',
            email='assistant@example.com',
            password='demo12345',
            role='assistant',
        )
        self.client.login(username='assistant@example.com', password='demo12345')

        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Account Settings')
        self.assertContains(response, 'assistant@example.com')

        response = self.client.post(reverse('profile'), {
            'form_type': 'profile',
            'first_name': 'Lina',
            'last_name': 'Haddad',
            'email': 'lina@example.com',
        })
        self.assertRedirects(response, reverse('profile'))
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Lina')
        self.assertEqual(user.last_name, 'Haddad')
        self.assertEqual(user.email, 'lina@example.com')
        self.assertEqual(user.username, 'lina@example.com')

        response = self.client.post(reverse('profile'), {
            'form_type': 'password',
            'old_password': 'demo12345',
            'new_password1': 'strong-pass-456',
            'new_password2': 'strong-pass-456',
        })
        self.assertRedirects(response, reverse('profile'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('strong-pass-456'))
        profile_response = self.client.get(reverse('profile'))
        self.assertEqual(profile_response.status_code, 200)

    def test_role_properties_cover_supported_personas(self):
        coach = User.objects.create_user(username='coach2@example.com', email='coach2@example.com', password='demo12345', role='coach')
        assistant = User.objects.create_user(username='assistant2@example.com', email='assistant2@example.com', password='demo12345', role='assistant')
        parent = User.objects.create_user(username='parent@example.com', email='parent@example.com', password='demo12345', role='parent')
        player = User.objects.create_user(username='player2@example.com', email='player2@example.com', password='demo12345', role='player')

        self.assertTrue(coach.is_coach)
        self.assertTrue(coach.is_staff_role)
        self.assertTrue(assistant.is_staff_role)
        self.assertTrue(parent.is_parent_role)
        self.assertTrue(player.is_player_role)


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
