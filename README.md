# VolleyPilot — Demo

Volleyball team management app built with Django for EECE 430.

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

## Docker Submission

This repo now includes a submission-friendly Docker setup for Moodle.

### Run with Docker Compose

```bash
docker compose up --build
```

Then open **http://127.0.0.1:8000**.

What happens automatically on container startup:

- Django migrations run
- Demo data is seeded on first boot if the database is empty
- The app starts on port `8000`

### Stop the container

```bash
docker compose down
```

### Build and run without Compose

```bash
docker build -t volleypilot .
docker run --rm -p 8000:8000 volleypilot
```

### Notes for Moodle

- The container does not rely on your local `.venv`
- The SQLite database is created inside the container at runtime
- Demo accounts are recreated automatically if the container starts with an empty database
- If you do not want demo seeding, run with `VOLLEYPILOT_AUTO_SEED=false`

## Demo Accounts

| Role      | Email                        | Password   |
|-----------|------------------------------|------------|
| Coach     | coach@volleypilot.com        | demo1234   |
| Assistant | assistant@volleypilot.com    | demo1234   |
| Player    | player@volleypilot.com       | demo1234   |
| Parent    | parent@volleypilot.com       | demo1234   |

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

## AI, Analytics, Security, and Notifications Additions

The project now includes the requested VolleyPilot task additions:

| Ticket | Implementation |
|--------|----------------|
| VT-107 | Completed matches generate anonymized ML training samples with hashed team/opponent IDs and no player names, emails, usernames, jersey numbers, or notes. Coaches can export the dataset from Smart Analytics. |
| VT-106 | Smart Analytics includes heuristic predictive match analytics for the next scheduled match, including win probability, confidence, season record, sideout rate, and training sample count. |
| VT-105 | Opponent insights summarize historical record, suggested tactics, and optional specific-opponent analysis. |
| VT-104 | Training recommendations are generated from rotation losses and tagged actions such as serve errors, attack errors, digs, and kills. |
| VT-103 | Rotation loss pattern detection highlights rotations where lost-point share is highest. |
| VT-102 | `/dashboard/ai-analytics/` centralizes predictive analytics, rotation trends, opponent scouting, training recommendations, dataset export, and the Volypilot chatbot. |
| VT-100 | Added responsive AI dashboard, notification, and live-match styles for desktop and tablet layouts. |
| VT-99 | Live match actions now return the updated state payload directly, reducing extra browser round trips; database indexes were added for live action lookups. |
| VT-98 | Production HTTPS/security headers are configurable, cookies are hardened, and analytics samples can be stored in encrypted form when a storage key is provided. |
| VT-91 | In-app notifications now include optional browser alerts through a lightweight authenticated notification feed. |

### Volypilot AI chatbot

Volypilot works without an API key by returning local heuristic insights. To connect it to an OpenAI-compatible chat-completions model, set these environment variables before running Django:

```bash
export VOLLEYPILOT_AI_API_KEY="your-api-key"
export VOLLEYPILOT_AI_MODEL="gpt-4o-mini"
# Optional if using another compatible provider:
export VOLLEYPILOT_AI_API_URL="https://api.openai.com/v1/chat/completions"
```

The API key stays server-side in Django settings and is not exposed in the browser.

### Production/security environment variables

```bash
export VOLLEYPILOT_DEBUG=false
export VOLLEYPILOT_SECRET_KEY="replace-with-a-long-secret"
export VOLLEYPILOT_ALLOWED_HOSTS="your-domain.com,www.your-domain.com"
export VOLLEYPILOT_CSRF_TRUSTED_ORIGINS="https://your-domain.com,https://www.your-domain.com"
export VOLLEYPILOT_STORAGE_ENCRYPTION_KEY="replace-with-a-long-random-key"
```

When `VOLLEYPILOT_DEBUG=false`, Django enables HTTPS redirect, secure cookies, and HSTS. For local development, keep `VOLLEYPILOT_DEBUG=true` or leave it unset.
