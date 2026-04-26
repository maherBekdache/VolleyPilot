from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Club, User
from teams.models import Team, TeamInvitation, TeamMembership


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class InvitationFlowTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name='AUB Volleyball Club')
        self.coach = User.objects.create_user(
            username='coach@example.com',
            email='coach@example.com',
            password='demo12345',
            role='coach',
            club=self.club,
            first_name='Sarah',
            last_name='Coach',
        )
        self.team = Team.objects.create(
            name='AUB Eagles',
            age_group='U18',
            club_affiliation='AUB Volleyball Club',
            created_by=self.coach,
        )
        TeamMembership.objects.create(team=self.team, user=self.coach, role='coach')

    def test_invite_creation_sends_email(self):
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.post(reverse('invite'), {
            'email': 'manager@example.com',
            'role': 'manager',
        })

        self.assertRedirects(response, reverse('roster'))
        invite = TeamInvitation.objects.get(email='manager@example.com')
        self.assertEqual(invite.role, 'manager')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(invite.token), mail.outbox[0].body)

    def test_accept_invite_requires_matching_email(self):
        invite = TeamInvitation.objects.create(team=self.team, email='manager@example.com', role='manager')
        wrong_user = User.objects.create_user(
            username='wrong@example.com',
            email='wrong@example.com',
            password='demo12345',
            role='fan',
        )
        matching_user = User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='demo12345',
            role='fan',
        )

        self.client.login(username='wrong@example.com', password='demo12345')
        response = self.client.post(reverse('accept_invite', args=[invite.token]), {'action': 'accept'})
        self.assertRedirects(response, reverse('dashboard'))
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'pending')

        self.client.logout()
        self.client.login(username='manager@example.com', password='demo12345')
        response = self.client.post(reverse('accept_invite', args=[invite.token]), {'action': 'accept'})
        self.assertRedirects(response, reverse('dashboard'))
        invite.refresh_from_db()
        matching_user.refresh_from_db()
        self.assertEqual(invite.status, 'accepted')
        self.assertEqual(matching_user.role, 'manager')
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=matching_user, role='manager').exists())
