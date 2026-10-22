"""Keep existing credentials and historical results while adding named connections."""

from django.core.management.color import no_style
from django.db import migrations


def preserve_connections(apps, schema_editor):
    alias = schema_editor.connection.alias
    AIConnection = apps.get_model("core", "AIConnection")
    AIIdentity = apps.get_model("core", "AIIdentity")
    AISession = apps.get_model("core", "AISession")
    ConnectionAttempt = apps.get_model("core", "ConnectionAttempt")
    GitConnection = apps.get_model("core", "GitConnection")
    GitHubConnection = apps.get_model("core", "GitHubConnection")
    connections = list(AIConnection.objects.using(alias).order_by("id"))
    preferred = next(
        (c.pk for c in connections if c.enabled and c.status == "CONNECTED"),
        connections[0].pk if connections else None,
    )
    for connection in connections:
        identity = AIIdentity.objects.using(alias).create(
            agent=connection.agent,
            credential_id=None,
            account=connection.account,
            status=connection.status,
            availability=connection.availability,
            retry_after=connection.retry_after,
            checked_at=connection.checked_at,
        )
        name = "ChatGPT" if connection.agent == "codex" else "Claude"
        AIConnection.objects.using(alias).filter(pk=connection.pk).update(
            identity_id=identity.pk, name=name, is_default=connection.pk == preferred
        )
        # The previous runtime selected its model outside the database. Leave
        # historical model attribution unknown instead of inventing a value.
        AISession.objects.using(alias).filter(connection_id=connection.pk).update(
            connection_name_snapshot=name, identity_snapshot=identity.pk
        )
        ConnectionAttempt.objects.using(alias).filter(provider=connection.agent).update(
            identity_id=identity.pk
        )
    legacy = GitHubConnection.objects.using(alias).filter(pk=1).first()
    if legacy:
        GitConnection.objects.using(alias).create(
            id=1,
            name="GitHub",
            provider="github",
            base_url="https://github.com",
            secret=legacy.secret,
            account=legacy.account,
            status=legacy.status,
        )
    for sql in schema_editor.connection.ops.sequence_reset_sql(
        no_style(), [AIConnection, GitConnection]
    ):
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("core", "0011_multiple_git_and_ai_connections")]
    operations = [migrations.RunPython(preserve_connections, migrations.RunPython.noop)]
