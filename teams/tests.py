from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Club, User
from teams.models import Player, Team, TeamInvitation, TeamMembership


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

    def test_team_settings_update_persists_defaults(self):
        self.client.login(username='coach@example.com', password='demo12345')
        response = self.client.post(reverse('team_settings'), {
            'name': self.team.name,
            'age_group': self.team.age_group,
            'club_affiliation': self.team.club_affiliation,
            'default_ruleset': 'best_of_3',
            'default_substitution_limit': 9,
            'preferred_first_server': 4,
        })
        self.assertRedirects(response, reverse('team_settings'))
        self.team.refresh_from_db()
        self.assertEqual(self.team.default_ruleset, 'best_of_3')
        self.assertEqual(self.team.default_substitution_limit, 9)
        self.assertEqual(self.team.preferred_first_server, 4)


class TeamAndRosterFlowTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name='AUB Volleyball Club')
        self.coach = User.objects.create_user(
            username='coach-roster@example.com',
            email='coach-roster@example.com',
            password='demo12345',
            role='coach',
            club=self.club,
        )
        self.player_user = User.objects.create_user(
            username='player-roster@example.com',
            email='player-roster@example.com',
            password='demo12345',
            role='player',
            club=self.club,
        )

    def test_team_creation_and_roster_management_flow(self):
        self.client.login(username='coach-roster@example.com', password='demo12345')
        response = self.client.post(reverse('team_create'), {
            'name': 'AUB Falcons',
            'age_group': 'U16',
            'club_affiliation': 'AUB Volleyball Club',
            'default_ruleset': 'fivb_best_of_5',
            'default_substitution_limit': 6,
            'preferred_first_server': 2,
        })
        self.assertRedirects(response, reverse('roster'))
        team = Team.objects.get(name='AUB Falcons')
        self.assertEqual(team.age_group, 'U16')
        self.assertEqual(team.club_affiliation, 'AUB Volleyball Club')

        response = self.client.post(reverse('player_add'), {
            'name': 'Maya Saab',
            'email': 'maya@example.com',
            'jersey_number': 8,
            'position': 'Libero',
            'height': '165',
            'year': '2008',
            'notes': 'Strong passer',
        })
        self.assertRedirects(response, reverse('roster'))
        player = Player.objects.get(team=team, jersey_number=8)
        self.assertEqual(player.name, 'Maya Saab')

        response = self.client.get(reverse('roster'))
        self.assertContains(response, 'Team Roster')
        self.assertContains(response, 'Maya Saab')

        response = self.client.post(reverse('player_edit', args=[player.pk]), {
            'name': 'Maya Saad',
            'email': 'maya@example.com',
            'jersey_number': 8,
            'position': 'Libero',
            'height': '166',
            'year': '2008',
            'notes': 'Updated notes',
        })
        self.assertRedirects(response, reverse('player_profile', args=[player.pk]))
        player.refresh_from_db()
        self.assertEqual(player.name, 'Maya Saad')
        self.assertEqual(player.height, '166')

    def test_role_based_access_blocks_player_from_staff_pages(self):
        team = Team.objects.create(
            name='AUB Eagles',
            age_group='U18',
            club_affiliation='AUB Volleyball Club',
            created_by=self.coach,
        )
        TeamMembership.objects.create(team=team, user=self.coach, role='coach')
        TeamMembership.objects.create(team=team, user=self.player_user, role='player')
        self.client.login(username='player-roster@example.com', password='demo12345')

        roster_response = self.client.get(reverse('roster'))
        self.assertEqual(roster_response.status_code, 200)
        invite_response = self.client.get(reverse('invite'))
        self.assertEqual(invite_response.status_code, 302)
        add_response = self.client.post(reverse('player_add'), {
            'name': 'Blocked Player',
            'email': 'blocked@example.com',
            'jersey_number': 10,
            'position': 'Setter',
        })
        self.assertEqual(add_response.status_code, 302)
        self.assertFalse(Player.objects.filter(team=team, jersey_number=10).exists())
