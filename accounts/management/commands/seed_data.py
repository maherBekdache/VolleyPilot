import random
from datetime import date, time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Club, User
from teams.models import Team, Player
from schedule.models import Match, Practice
from drills.models import Drill, PracticeDrill
from matches.models import LiveMatch, SetScore, Action, ActionTag


class Command(BaseCommand):
    help = 'Seeds the database with realistic demo data for Sprint 1.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')

        # ── Club & Coach ──
        club, _ = Club.objects.get_or_create(name='AUB Volleyball Club')
        coach, created = User.objects.get_or_create(
            email='coach@volleypilot.com',
            defaults={
                'username': 'coach',
                'first_name': 'Sarah',
                'last_name': 'Mitchell',
                'role': 'coach',
                'club': club,
            }
        )
        if created:
            coach.set_password('demo1234')
            coach.save()
            self.stdout.write(self.style.SUCCESS('  Created coach account (coach@volleypilot.com / demo1234)'))

        assistant, created = User.objects.get_or_create(
            email='assistant@volleypilot.com',
            defaults={
                'username': 'assistant',
                'first_name': 'Mike',
                'last_name': 'Torres',
                'role': 'assistant',
                'club': club,
            }
        )
        if created:
            assistant.set_password('demo1234')
            assistant.save()

        # Player user account (for availability demo)
        player_user, created = User.objects.get_or_create(
            email='player@volleypilot.com',
            defaults={
                'username': 'player',
                'first_name': 'Emma',
                'last_name': 'Davis',
                'role': 'player',
                'club': club,
            }
        )
        if created:
            player_user.set_password('demo1234')
            player_user.save()
            self.stdout.write(self.style.SUCCESS('  Created player account (player@volleypilot.com / demo1234)'))

        # ── Team ──
        team, _ = Team.objects.get_or_create(
            name='AUB Eagles',
            defaults={
                'age_group': 'U18',
                'club_affiliation': 'AUB Volleyball Club',
                'created_by': coach,
            }
        )

        # ── Team Memberships ──
        from teams.models import TeamMembership
        TeamMembership.objects.get_or_create(team=team, user=coach, defaults={'role': 'coach'})
        TeamMembership.objects.get_or_create(team=team, user=assistant, defaults={'role': 'assistant'})

        # ── Players (12) ──
        players_data = [
            ('Emma Davis', 1, 'Setter', "5'8\"", 'Junior'),
            ('Olivia Chen', 7, 'Outside Hitter', "5'11\"", 'Senior'),
            ('Sophia Martinez', 12, 'Outside Hitter', "5'10\"", 'Junior'),
            ('Ava Johnson', 4, 'Middle Blocker', "6'1\"", 'Senior'),
            ('Isabella Brown', 15, 'Middle Blocker', "6'0\"", 'Sophomore'),
            ('Mia Wilson', 9, 'Opposite', "5'11\"", 'Junior'),
            ('Charlotte Lee', 3, 'Libero', "5'6\"", 'Senior'),
            ('Amelia Taylor', 11, 'Defensive Specialist', "5'7\"", 'Junior'),
            ('Harper Anderson', 8, 'Outside Hitter', "5'10\"", 'Sophomore'),
            ('Evelyn Thomas', 6, 'Setter', "5'9\"", 'Freshman'),
            ('Luna Garcia', 14, 'Middle Blocker', "6'0\"", 'Sophomore'),
            ('Aria Robinson', 2, 'Defensive Specialist', "5'6\"", 'Freshman'),
        ]
        player_objs = []
        for name, num, pos, height, year in players_data:
            p, _ = Player.objects.get_or_create(
                team=team, jersey_number=num,
                defaults={
                    'name': name, 'position': pos,
                    'height': height, 'year': year,
                    'user': player_user if name == 'Emma Davis' else None,
                }
            )
            player_objs.append(p)
        self.stdout.write(self.style.SUCCESS(f'  {len(player_objs)} players ensured'))

        # ── Drills (12) ──
        drills_data = [
            ('Pepper Passing', 'Passing', '15', '2', 'beginner', 'Partners pass, set, and hit to each other continuously.'),
            ('Target Serving', 'Serving', '20', '6', 'intermediate', 'Serve to specific zones marked on the opposite court.'),
            ('Hitting Lines', 'Hitting', '20', '8', 'intermediate', 'Players rotate through hitting lines with setter feeding.'),
            ('Block & Recover', 'Blocking', '15', '6', 'advanced', 'Block at the net then immediately transition to defense.'),
            ('Dig & Set', 'Defense', '15', '4', 'beginner', 'Coach tosses balls for players to dig and set to target.'),
            ('Setting Footwork', 'Setting', '10', '2', 'beginner', 'Focus on proper footwork patterns for setting.'),
            ('Wash Drill', 'Game-like', '25', '12', 'advanced', 'Rally-score game where teams must win consecutive rallies.'),
            ('Serve Receive Patterns', 'Passing', '20', '6', 'intermediate', 'Practice different serve receive formations.'),
            ('Quick Attack Timing', 'Hitting', '15', '4', 'advanced', 'Middle hitters work on timing with setter for quick sets.'),
            ('Defensive Shuffle', 'Defense', '10', '6', 'beginner', 'Lateral movement drills for defensive positioning.'),
            ('Jump Serve Progression', 'Serving', '20', '4', 'advanced', 'Step-by-step approach to learning the jump serve.'),
            ('6 vs 6 Controlled', 'Game-like', '30', '12', 'intermediate', 'Full scrimmage with coach-imposed constraints.'),
        ]
        drill_objs = []
        for name, cat, dur, players_needed, diff, desc in drills_data:
            d, _ = Drill.objects.get_or_create(
                name=name,
                defaults={
                    'category': cat, 'duration': dur,
                    'players_needed': players_needed, 'difficulty': diff,
                    'description': desc, 'created_by': coach,
                }
            )
            drill_objs.append(d)
        self.stdout.write(self.style.SUCCESS(f'  {len(drill_objs)} drills ensured'))

        # ── Schedule ──
        today = date.today()
        # Upcoming matches
        upcoming_matches_data = [
            (today + timedelta(days=3), time(18, 0), 'AUB Gymnasium', 'LAU Wolves', True),
            (today + timedelta(days=7), time(16, 0), 'USJ Arena', 'USJ Tigers', False),
            (today + timedelta(days=14), time(18, 30), 'AUB Gymnasium', 'NDU Hawks', True),
        ]
        for d, t, loc, opp, home in upcoming_matches_data:
            Match.objects.get_or_create(
                team=team, date=d, opponent=opp,
                defaults={'time': t, 'location': loc, 'is_home': home, 'created_by': coach}
            )

        # Upcoming practices
        practices_data = [
            (today + timedelta(days=1), time(16, 0), 'AUB Gym A', 'Serve Receive', ['Pepper Passing', 'Serve Receive Patterns']),
            (today + timedelta(days=2), time(15, 30), 'AUB Gym A', 'Hitting & Blocking', ['Hitting Lines', 'Block & Recover']),
            (today + timedelta(days=5), time(16, 0), 'AUB Gym B', 'Full Scrimmage', ['Wash Drill', '6 vs 6 Controlled']),
            (today + timedelta(days=6), time(15, 0), 'AUB Gym A', 'Defense Focus', ['Defensive Shuffle', 'Dig & Set']),
        ]
        for d, t, loc, focus, drill_names in practices_data:
            p, created_p = Practice.objects.get_or_create(
                team=team, date=d, focus=focus,
                defaults={'time': t, 'location': loc, 'created_by': coach}
            )
            if created_p:
                for i, dn in enumerate(drill_names, 1):
                    drill = Drill.objects.filter(name=dn).first()
                    if drill:
                        PracticeDrill.objects.get_or_create(
                            practice=p, drill=drill,
                            defaults={'order': i, 'planned_duration': drill.duration}
                        )

        self.stdout.write(self.style.SUCCESS('  Schedule created'))

        # ── Historical Matches with Full Stats ──
        opponents = [
            ('BAU Bobcats', True), ('Haigazian Hornets', False),
            ('USEK Knights', True), ('Balamand Bears', False),
            ('RHU Rams', True), ('LAU Wolves', False),
            ('Antonine Ants', True), ('NDU Hawks', False),
            ('AUL Lions', True), ('LIU Falcons', False),
        ]
        # Player stat weights (kills, blocks, aces, digs) – simulate realistic distributions
        stat_weights = {
            'Setter': {'kill': 2, 'block': 1, 'ace': 3, 'dig': 5, 'assist': 15},
            'Outside Hitter': {'kill': 12, 'block': 3, 'ace': 4, 'dig': 6, 'assist': 1},
            'Middle Blocker': {'kill': 6, 'block': 8, 'ace': 2, 'dig': 2, 'assist': 0},
            'Opposite': {'kill': 10, 'block': 4, 'ace': 3, 'dig': 3, 'assist': 1},
            'Libero': {'kill': 0, 'block': 0, 'ace': 0, 'dig': 15, 'assist': 2},
            'Defensive Specialist': {'kill': 1, 'block': 0, 'ace': 2, 'dig': 12, 'assist': 1},
        }

        for idx, (opp_name, is_home) in enumerate(opponents):
            match_date = today - timedelta(days=(len(opponents) - idx) * 5)
            match, m_created = Match.objects.get_or_create(
                team=team, date=match_date, opponent=opp_name,
                defaults={
                    'time': time(18, 0), 'location': 'AUB Gymnasium' if is_home else f'{opp_name.split()[0]} Arena',
                    'is_home': is_home, 'status': 'completed', 'created_by': coach,
                }
            )
            if not m_created:
                continue

            # Create LiveMatch
            starters = player_objs[:6]
            live = LiveMatch.objects.create(
                match=match, current_set=1, is_active=False,
                started_at=timezone.now() - timedelta(hours=2),
                ended_at=timezone.now() - timedelta(hours=1),
            )

            # Decide outcome: ~70% win rate, deliberately lose some
            we_win = random.random() < 0.7
            if we_win:
                our_set_wins = 3
                their_set_wins = random.choice([0, 1, 2])
            else:
                their_set_wins = 3
                our_set_wins = random.choice([0, 1, 2])

            total_sets = our_set_wins + their_set_wins
            our_wins_left = our_set_wins
            their_wins_left = their_set_wins

            for set_num in range(1, total_sets + 1):
                min_points = 25 if set_num < 5 else 15
                if our_wins_left > 0 and (their_wins_left == 0 or random.random() < 0.55):
                    # We win this set
                    our_score = min_points + random.randint(0, 5)
                    opp_score = our_score - random.randint(2, 6)
                    if opp_score < 10:
                        opp_score = random.randint(15, our_score - 2)
                    our_wins_left -= 1
                else:
                    # They win this set
                    opp_score = min_points + random.randint(0, 5)
                    our_score = opp_score - random.randint(2, 6)
                    if our_score < 10 and opp_score - 2 >= 15:
                        our_score = random.randint(15, opp_score - 2)
                    elif our_score < 10:
                        our_score = 10
                    their_wins_left -= 1

                SetScore.objects.create(
                    live_match=live, set_number=set_num,
                    our_score=our_score, opponent_score=opp_score,
                    is_complete=True
                )

                # Generate actions with rotation data
                total_points = our_score + opp_score
                for point_idx in range(total_points):
                    rotation = (point_idx % 6) + 1
                    # Rotation 3 is intentionally weaker for demo
                    if rotation == 3:
                        we_score = random.random() < 0.35  # weak
                    else:
                        we_score = random.random() < 0.55

                    action = Action.objects.create(
                        live_match=live,
                        action_type='point_won' if we_score else 'point_lost',
                        set_number=set_num,
                        rotation=rotation,
                        data={'our_score': min(point_idx + 1, our_score),
                              'opp_score': min(point_idx + 1, opp_score)},
                    )

                    # Tag with a player action
                    if we_score:
                        player = random.choice(starters)
                        weights = stat_weights.get(player.position, {})
                        tag_choices = []
                        for tag, w in weights.items():
                            tag_choices.extend([tag] * w)
                        if tag_choices:
                            tag_type = random.choice(tag_choices)
                            ActionTag.objects.create(
                                action=action, tag_type=tag_type, player=player
                            )

        self.stdout.write(self.style.SUCCESS(f'  {len(opponents)} historical matches with stats created'))
        self.stdout.write(self.style.SUCCESS('\nSeed complete! Login credentials:'))
        self.stdout.write('  Coach: coach@volleypilot.com / demo1234')
        self.stdout.write('  Player: player@volleypilot.com / demo1234')
