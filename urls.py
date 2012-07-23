from django.conf.urls.defaults import *

handler500 = 'djangotoolbox.errorviews.server_error'

urlpatterns = patterns('',
    ('^_ah/warmup$', 'djangoappengine.views.warmup'),

    # dropbox auth
    (r'^dropbox/$', 'db2flickr.dropboxToFlickr.dropbox'),
    (r'^dropbox/dropboxauthorize/$', 'db2flickr.dropboxToFlickr.dropboxAuthorize'),

    # flickr auth
    (r'^flickr/$', 'db2flickr.dropboxToFlickr.flickr'),
    (r'^flickr/flickrauthorize/$', 'db2flickr.dropboxToFlickr.flickrAuthorize'),

    # transfer from dropbox to flickr
    (r'^startapp/$', 'db2flickr.dropboxToFlickr.transferToFlickr'),

    # rest
    (r'^upload_history/$', 'db2flickr.dropboxToFlickr.getUploadHistory'),

    # management
    (r'^set_api_key/$', 'db2flickr.dropboxToFlickr.setAPIKey'),
)
