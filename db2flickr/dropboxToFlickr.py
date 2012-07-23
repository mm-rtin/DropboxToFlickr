from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.utils import simplejson

from google.appengine.api import memcache

from dropbox import session, client
import flickrapi
import flickrapi.shorturl

import logging

from db2flickr.models import UploadHistory, ApiKeys

# KEYNAMES
DROPBOX_APP_KEY = 'DROPBOX_APP_KEY'
DROPBOX_APP_SECRET = 'DROPBOX_APP_SECRET'

FLICKR_API_KEY = 'FLICKR_API_KEY'
FLICKR_API_SECRET = 'FLICKR_API_SECRET'

ACCESS_TYPE = 'app_folder'
UPLOAD_PER_REQUEST = 6

# clients
dropboxClient = None
flickrClient = None

# constants
TAG_LINKS = {'Diablo': 'diablo', 'Gw2': 'guildwars2'}


# setAPIKey
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def setAPIKey(request):

    if all(k in request.GET for k in ('key_name', 'key_value')):

        # get user parameters
        keyName = request.GET.get('key_name')
        keyValue = request.GET.get('key_value')

    # set key
    output = setKey(keyName, keyValue)

    return render_to_response('index.html', {'output': output})


# setKey
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def setKey(keyName, keyValue):

    # get existing key
    try:
        apiKey = ApiKeys.objects.get(keyName=keyName)
    except ApiKeys.DoesNotExist:
        apiKey = None

    # update existing keyName
    if apiKey:
        apiKey.keyName = keyName
        apiKey.keyValue = keyValue

    # create new key
    else:
        apiKey = ApiKeys(
            keyName=keyName,
            keyValue=keyValue
        )

    apiKey.save()

    # save to memcache
    if not memcache.add(keyName, keyValue):

        # update memcache
        memcache.set(key=keyName, value=keyValue)

    return 'keyName=%s keyValue=%s' % (keyName, keyValue)


# getKey
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def getKey(keyName):

    # find key in memcache
    apiKey = memcache.get(keyName)

    # key not found in memcache
    if not apiKey:

        # fetch from ApiKeys table
        try:
            apiKeyRecord = ApiKeys.objects.get(keyName=keyName)
            # save to memcache
            if not memcache.add(apiKeyRecord.keyName, apiKeyRecord.keyValue):
                logging.error('memcache set failed')

            apiKey = apiKeyRecord.keyValue

        except ApiKeys.DoesNotExist:
            apiKey = None

    return apiKey


# getUploadHistory
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def getUploadHistory(request):

    uploadHistory = UploadHistory.objects.filter()
    historyList = []

    # uploadHistory found
    if uploadHistory:

        # construct python dictionary
        for item in uploadHistory:
            historyList.append({'id': item.pk, 'url': item.url, 'filename': item.filename})

    return HttpResponse(simplejson.dumps(historyList), mimetype='application/json')


# getDropboxSession
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def getDropboxSession():
    return session.DropboxSession(getKey(DROPBOX_APP_KEY), getKey(DROPBOX_APP_SECRET), ACCESS_TYPE)


# getDropboxClient
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def getDropboxClient(dropbox_access_token_key, dropbox_access_token_secret):
    sess = getDropboxSession()
    sess.set_token(dropbox_access_token_key, dropbox_access_token_secret)
    return client.DropboxClient(sess)


# dropbox
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def dropbox(request):

    # check for saved access_token
    dropbox_access_token_key = getKey('dropbox_access_token_key')
    dropbox_access_token_secret = getKey('dropbox_access_token_secret')

    # existing dropbox_access_token_key found
    if dropbox_access_token_key and dropbox_access_token_secret:
        return render_to_response('index.html', {'output': 'authorized'})

    # new authorization
    else:

        url = getDropboxAuthURL(request)

        return render_to_response('index.html', {'output': url})


# getDropboxAuthURL
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def getDropboxAuthURL(request):

    sess = getDropboxSession()
    request_token = sess.obtain_request_token()

    # cache request_token under (request_token.key == oauth_token)
    setKey(request_token.key, request_token)

    callback = """%sdropboxauthorize""" % request.build_absolute_uri(request.get_full_path())
    url = sess.build_authorize_url(request_token, oauth_callback=callback)

    return url


# dropboxAuthorize
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def dropboxAuthorize(request):

    # get return oauth_token
    oauth_token = request.GET.get('oauth_token')

    # create session
    sess = getDropboxSession()

    # fetch request token (request_token.key == oauth_token)
    request_token = getKey(oauth_token)

    # get access_token
    access_token = sess.obtain_access_token(request_token)

    # cache access_token
    setKey('dropbox_access_token_key', access_token.key)
    setKey('dropbox_access_token_secret', access_token.secret)

    return render_to_response('index.html', {'output': 'authorized'})


# flickr
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def flickr(request):

    flickr_access_token = getKey('flickr_access_token')

    flickrClient = flickrapi.FlickrAPI(getKey(FLICKR_API_KEY), getKey(FLICKR_API_SECRET), token=flickr_access_token, store_token=False)

    if flickr_access_token:
        # We have a token, but it might not be valid
        logging.info('Verifying token')
        try:
            flickrClient.auth_checkToken()
        except flickrapi.FlickrError:
            flickr_access_token = None

            setKey('flickr_access_token', '')

        return render_to_response('index.html', {'output': 'authorized'})

    if not flickr_access_token:

        # No valid token, so redirect to Flickr
        logging.info('Redirecting user to Flickr to get frob')
        url = flickrClient.web_login_url(perms='write')
        return render_to_response('index.html', {'output': url})


# flickrAuthorize
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def flickrAuthorize(request):
    logging.info('We got a callback from Flickr, store the token')

    flickrClient = flickrapi.FlickrAPI(getKey(FLICKR_API_KEY), getKey(FLICKR_API_SECRET), store_token=False)

    frob = request.GET['frob']
    token = flickrClient.get_token(frob)

    logging.info('callback')

    setKey('flickr_access_token', token)

    return render_to_response('index.html', {'output': 'authorized'})


# transferToFlickr
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def transferToFlickr(request):

    # get flickr token
    flickr_access_token = getKey('flickr_access_token')
    # get dropbox token
    dropbox_dropbox_access_token_key = getKey('dropbox_access_token_key')
    dropbox_dropbox_access_token_secret = getKey('dropbox_access_token_secret')

    logging.info('######### TRANSFER TO FLICKR ##########')
    logging.info(dropbox_dropbox_access_token_key)
    logging.info(dropbox_dropbox_access_token_secret)
    logging.info(flickr_access_token)
    logging.info('##############################')
    logging.info('##############################')

    # make sure we have flickr and dropbox authorization
    if flickr_access_token and dropbox_dropbox_access_token_key and dropbox_dropbox_access_token_secret:

        # get flickr client
        flickrClient = flickrapi.FlickrAPI(getKey(FLICKR_API_KEY), getKey(FLICKR_API_SECRET), token=flickr_access_token, store_token=False)
        # get dropbox client
        dropboxClient = getDropboxClient(dropbox_dropbox_access_token_key, dropbox_dropbox_access_token_secret)

        # get dropbox folder data
        folder_metadata = dropboxClient.metadata('/')

        mediaObjects = []
        count = 1

        # for each item in app folder
        for item in folder_metadata['contents']:

            logging.info('------ GET DROPBOX ITEM ------')
            logging.info(item['path'])
            logging.info('------------------------------')
            logging.info('------------------------------')

            # create media link and get url > append to imageURLs
            mediaItem = dropboxClient.media(item['path'])

            # split path by '-'
            filenameComponents = item['path'].split('-')

            # first substring before '-' is default tag
            tag = filenameComponents[0][1:]

            # iterate TAG_LINKS and match
            for key, value in TAG_LINKS.items():
                if (tag.find(key) > -1):
                    tag = value

            # construct object
            mediaObject = {'url': mediaItem['url'], 'filename': item['path'], 'tags': tag}

            mediaObjects.append(mediaObject)

            # upload 2 photos per request
            if (count == UPLOAD_PER_REQUEST):
                break
            count = count + 1

        # upload to flickr
        for mediaObject in mediaObjects:

            logging.info('------ UPLOAD TO FLICKR ------')
            logging.info(mediaObject['url'])
            logging.info('------------------------------')
            logging.info('------------------------------')

            response = flickrClient.upload(mediaObject['url'], callback=None, tags=mediaObject['tags'], is_public='1', content_type='2', hidden='1')

            # get short url
            photoid = response.find('photoid').text
            shortURL = flickrapi.shorturl.url(photoid)

            # upload complete
            flickrUploadComplete(dropboxClient, shortURL, mediaObject['filename'], mediaObject['url'])

        return HttpResponse(mediaObjects, mimetype='text', status='200')

    logging.info('------------------------------')
    logging.info('----- NOT AUTHORIZED ---------')
    logging.info('------------------------------')

    return render_to_response('index.html', {'output': 'not authorized'})


# flickrUploadComplete
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def flickrUploadComplete(dropboxClient, flickrURL, dropboxFilename, dropboxURL):

    logging.info('------ UPLOAD COMPLETE -------')
    logging.info(flickrURL)
    logging.info('------------------------------')
    logging.info('------------------------------')

    historyItem = UploadHistory(
        filename=dropboxFilename,
        flickr_url=flickrURL
    )
    historyItem.save()

    # delete file on dropbox
    dropboxClient.file_delete(dropboxFilename)
