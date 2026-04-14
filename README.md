# VolleyPilot — Sprint 1 Demo

Volleyball team management app built with Django for CMPS 430.

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Django
pip install django

# 3. Run migrations
python manage.py migrate

# 4. Seed demo data
python manage.py seed_data

# 5. Start the server
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser.

## Demo Accounts

| Role      | Email                        | Password   |
|-----------|------------------------------|------------|
| Coach     | coach@volleypilot.com        | demo1234   |
| Assistant | assistant@volleypilot.com    | demo1234   |
| Player    | player@volleypilot.com       | demo1234   |

New users register as **fan** by default and see league-wide data.

## Features

| Feature          | Description                                                    |
|------------------|----------------------------------------------------------------|
| Dashboard        | Team overview, win rate, calendar with match/practice dots      |
| Team Roster      | Add/edit/remove players; click a player to see individual stats |
| Schedule         | Upcoming/Completed tabs, colored badges (Home/Away/Practice)    |
| Statistics       | Team & league-wide filtering, search, per-player view           |
| Game Results     | Win/loss history with set scores, filter by outcome             |
| Practice Drills  | Drill library with search/filter, assign drills to practices    |
| Fan Dashboard    | League-wide browsing for fan-role users                         |
| Registration     | Auto-links player accounts by email match                       |

## Role Permissions

| Feature         | Coach | Assistant | Player | Fan   |
|-----------------|-------|-----------|--------|-------|
| Dashboard       | ✅    | ✅        | ✅     | ✅ (fan view) |
| Manage Roster   | ✅    | ✅        | ❌     | ❌    |
| View Roster     | ✅    | ✅        | ✅     | ✅ (all teams) |
| Schedule        | ✅    | ✅        | ✅     | ✅ (all teams) |
| Statistics      | ✅    | ✅        | ✅     | ✅ (league) |
| Practice Drills | ✅    | ✅        | ✅     | ❌    |
| Game Results    | ✅    | ✅        | ✅     | ✅ (all teams) |

## Project Structure

```
volleypilot/
├── accounts/       # Auth, registration, user model, roles
├── teams/          # Team & player management, roster
├── schedule/       # Matches, practices, availability
├── drills/         # Drill library, practice assignments
├── dashboard/      # Dashboard, statistics, results, CSV export
├── matches/        # Match data models (stats storage)
├── templates/      # All HTML templates
├── static/css/     # Stylesheet
└── volleypilot/    # Project settings & root URLs
```

## Tech Stack

- **Backend:** Django 6.0
- **Database:** SQLite
- **Frontend:** Django templates, vanilla JS, CSS
- **Auth:** Session-based, custom User model (email login)

## Seeded Demo Data

- **AUB Eagles** team with 12 players
- 3 upcoming matches, 4 upcoming practices with assigned drills
- 10 historical completed matches with full set scores and player stats
- 12 drills across all categories

## Reset Data

```bash
rm db.sqlite3
python manage.py migrate
python manage.py seed_data
```
