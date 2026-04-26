import json
from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from accounts.models import Club, User
from matches.models import Action, ActionTag, LiveMatch, PlayerParticipation
from schedule.models import Match
from teams.models import Player, Team, TeamMembership


class LiveMatchFlowTests(TestCase):
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
        self.players = [
            Player.objects.create(team=self.team, name=f'Player {idx}', jersey_number=idx, position='Setter' if idx == 1 else 'Outside Hitter')
            for idx in range(1, 9)
        ]
        self.match = Match.objects.create(
            team=self.team,
            title='League Match',
            date=date.today(),
            time=time(18, 0),
            location='AUB Gym',
            opponent='LAU Wolves',
            is_home=True,
            created_by=self.coach,
        )

    def _start_match(self):
        self.client.login(username='coach@example.com', password='demo12345')
        payload = {
            'first_server': '1',
            'libero_player': str(self.players[6].pk),
        }
        for index, player in enumerate(self.players[:6], start=1):
            payload[f'position_{index}'] = str(player.pk)
        payload['bench'] = [str(self.players[6].pk), str(self.players[7].pk)]
        response = self.client.post(reverse('start_match', args=[self.match.pk]), payload)
        self.assertRedirects(response, reverse('live_match', args=[self.match.pk]))
        return LiveMatch.objects.get(match=self.match)

    def test_live_match_supports_libero_sideout_tagging_and_participation(self):
        live = self._start_match()
        self.assertEqual(live.libero_player, self.players[6])
        self.assertTrue(PlayerParticipation.objects.filter(live_match=live, player=self.players[0], currently_on_court=True).exists())

        # Lose serve first, then win it back with a sideout.
        response = self.client.post(
            reverse('record_point', args=[self.match.pk]),
            data=json.dumps({'us': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('record_point', args=[self.match.pk]),
            data=json.dumps({'us': True, 'mode': 'sideout'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        latest_action = Action.objects.filter(live_match=live).order_by('-timestamp').first()
        self.assertEqual(latest_action.action_type, 'sideout')

        # Tag the most recent rally.
        response = self.client.post(
            reverse('tag_last_point', args=[self.match.pk]),
            data=json.dumps({'player_id': self.players[0].pk, 'tag_type': 'kill'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ActionTag.objects.filter(action=latest_action, player=self.players[0], tag_type='kill').exists())

        # Record a libero swap.
        response = self.client.post(
            reverse('make_substitution', args=[self.match.pk]),
            data=json.dumps({
                'player_in': self.players[6].pk,
                'player_out': self.players[4].pk,
                'is_libero_swap': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        live.refresh_from_db()
        self.assertEqual(int(live.lineup['5']), self.players[6].pk)

        # Undo the libero swap.
        response = self.client.post(reverse('undo_last_action', args=[self.match.pk]), data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        live.refresh_from_db()
        self.assertEqual(int(live.lineup['5']), self.players[4].pk)

        state = self.client.get(reverse('match_state', args=[self.match.pk])).json()
        self.assertIn('rotation_metrics', state)
        self.assertIn('run_stats', state)
        self.assertIn('participation_totals', state)

    def test_regular_substitutions_respect_match_limit(self):
        self.match.substitution_limit = 1
        self.match.save(update_fields=['substitution_limit'])
        live = self._start_match()
        response = self.client.post(
            reverse('make_substitution', args=[self.match.pk]),
            data=json.dumps({
                'player_in': self.players[6].pk,
                'player_out': self.players[4].pk,
                'is_libero_swap': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('make_substitution', args=[self.match.pk]),
            data=json.dumps({
                'player_in': self.players[7].pk,
                'player_out': self.players[3].pk,
                'is_libero_swap': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('limit', response.json()['error'].lower())
        live.refresh_from_db()
        self.assertEqual(live.match.substitution_limit, 1)
