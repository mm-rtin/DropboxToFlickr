from django.db import models


# UPLOAD HISTORY
class UploadHistory(models.Model):
    filename = models.CharField(max_length=1024)
    flickr_url = models.CharField(max_length=128, blank=True, null=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'UploadHistory'


# API KEYS
class ApiKeys(models.Model):
    keyName = models.CharField(max_length=1024)
    keyValue = models.CharField(max_length=1024)

    class Meta:
        verbose_name_plural = 'ApiKeys'
