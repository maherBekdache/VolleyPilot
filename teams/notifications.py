from accounts.models import Notification
from .models import TeamMembership


def notify_team(team, title, body='', notif_type='match', link=''):
    """Create a Notification for every active member of the given team."""
    member_ids = TeamMembership.objects.filter(team=team).values_list('user_id', flat=True)
    notifications = [
        Notification(
            user_id=uid,
            title=title,
            body=body,
            notif_type=notif_type,
            link=link,
        )
        for uid in member_ids
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)
