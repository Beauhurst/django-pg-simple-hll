import uuid

from django.db import models


class Session(models.Model):
    user_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    user_int = models.IntegerField(editable=False)
    user_str = models.TextField(editable=False)
    created = models.DateTimeField()
