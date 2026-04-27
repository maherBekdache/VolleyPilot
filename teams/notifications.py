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


# === NEW ADDITION START: SMTP email helper for team invitations ===
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_team_invitation_email(invite, invited_by, accept_url):
    """Send a team invitation using Django's configured SMTP/email backend.

    SMTP is configured in volleypilot/settings.py through VOLLEYPILOT_EMAIL_* env vars.
    Keeping this in one helper makes the invite trigger reusable and testable.
    """
    invited_by_name = invited_by.get_full_name() or invited_by.email or 'A VolleyPilot coach'
    role_label = invite.get_role_display()
    subject = f"You're invited to join {invite.team.name} on VolleyPilot"

    text_body = (
        f"Hello,\n\n"
        f"{invited_by_name} invited you to join {invite.team.name} as {role_label}.\n\n"
        f"Use this link to accept or decline the invitation:\n{accept_url}\n\n"
        f"If you were not expecting this invitation, you can ignore this email.\n"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#0f172a;">
      <h2 style="color:#2563eb;">VolleyPilot Team Invitation</h2>
      <p>Hello,</p>
      <p><strong>{invited_by_name}</strong> invited you to join
         <strong>{invite.team.name}</strong> as <strong>{role_label}</strong>.</p>
      <p>
        <a href="{accept_url}"
           style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;
                  padding:12px 18px;border-radius:8px;font-weight:700;">
          Accept or decline invitation
        </a>
      </p>
      <p style="font-size:13px;color:#64748b;">If the button does not work, copy this link:</p>
      <p style="font-size:13px;word-break:break-all;color:#334155;">{accept_url}</p>
    </div>
    """

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invite.email],
    )
    email.attach_alternative(html_body, "text/html")
    return email.send(fail_silently=False) > 0
# === NEW ADDITION END: SMTP email helper for team invitations ===
