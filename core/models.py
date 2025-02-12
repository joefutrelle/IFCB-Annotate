from django.db import models
from django.contrib.auth.models import Group, User
import uuid


# Model database tables are prefixed with "classify" to allow backwards compatibility with pre-existing
#   IFCB Annotate databases, which had the models within a classify Django app

class ClassLabel(models.Model):
    name = models.CharField(max_length=300)
    international_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'classify_classlabel'


class TagLabel(models.Model):
    name = models.CharField(max_length=300)

    class Meta:
        db_table = 'classify_taglabel'


class Timeseries(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid1)
    url = models.CharField(max_length=1000)

    class Meta:
        verbose_name_plural = 'Timeseries'
        db_table = 'classify_timeseries'


class Classification(models.Model):
    bin = models.CharField(max_length=100)
    roi = models.IntegerField()
    user_id = models.IntegerField()
    time = models.DateTimeField(auto_now_add=True)
    classification_id = models.IntegerField()
    level = models.IntegerField(default=1)
    verifications = models.IntegerField(default=0)
    verification_time = models.DateTimeField(null=True, blank=True)
    timeseries_id = models.CharField(max_length=36)

    class Meta:
        indexes = [
            models.Index(fields=['bin'])
        ]
        unique_together = (('bin', 'roi', 'user_id', 'classification_id'),)
        db_table = 'classify_classification'


class Tag(models.Model):
    bin = models.CharField(max_length=100)
    roi = models.IntegerField()
    user_id = models.IntegerField()
    time = models.DateTimeField(auto_now_add=True)
    tag_id = models.IntegerField()
    level = models.IntegerField(default=1)
    verifications = models.IntegerField(default=0)
    verification_time = models.DateTimeField(null=True, blank=True)
    timeseries_id = models.CharField(max_length=36)
    negation = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['tag_id'])
        ]
        unique_together = (('bin', 'roi', 'user_id', 'tag_id', 'negation'),)
        db_table = 'classify_tag'


# add some fields and methods to User and Group
# FIXME not recommended

Group.add_to_class('power', models.IntegerField(default=0))


def get_group_power(self):
    if self.power:
        return self.power
    return 0


Group.add_to_class('get_group_power', get_group_power)


def get_user_power(self):
    power = 0
    for g in self.groups.all():
        if g.get_group_power() > power:
            power = g.get_group_power()
    return power


User.add_to_class('get_user_power', get_user_power)
