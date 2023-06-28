import uuid

from django.db import models


class Group(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField()


class Session(models.Model):
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    user_int = models.IntegerField(editable=False)
    user_str = models.TextField(editable=False)
    user_hash = models.PositiveIntegerField(editable=False)
    created = models.DateTimeField()

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="sessions")
