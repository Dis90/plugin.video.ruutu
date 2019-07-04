# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for Ruutu
"""
import os
import json
import codecs
import cookielib
import time
from datetime import datetime

import requests
import urlparse
from bs4 import BeautifulSoup
import xmltodict
import urllib

class Ruutu(object):
    def __init__(self, settings_folder, debug=False):
        self.debug = debug
        self.http_session = requests.Session()
        self.settings_folder = settings_folder
        self.tempdir = os.path.join(settings_folder, 'tmp')
        if not os.path.exists(self.tempdir):
            os.makedirs(self.tempdir)
        self.cookie_jar = cookielib.LWPCookieJar(os.path.join(self.settings_folder, 'cookie_file'))
        self.credentials_file = os.path.join(settings_folder, 'credentials')
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar

    class RuutuError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[Ruutu]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[Ruutu]: %s' % string.replace(bom, '')
            except:
                pass

    def make_request(self, url, method, params=None, payload=None, headers=None, text=False):
        """Make an HTTP request. Return the response."""
        self.log('Request URL: %s' % url)
        self.log('Method: %s' % method)
        self.log('Params: %s' % params)
        self.log('Payload: %s' % payload)
        self.log('Headers: %s' % headers)
        try:
            if method == 'get':
                req = self.http_session.get(url, params=params, headers=headers)
            elif method == 'put':
                req = self.http_session.put(url, params=params, data=payload, headers=headers)
            elif method == 'delete':
                req = self.http_session.delete(url, params=params, data=payload, headers=headers)
            else:  # post
                req = self.http_session.post(url, params=params, data=payload, headers=headers)
            self.log('Response code: %s' % req.status_code)
            self.log('Response: %s' % req.content)
            self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
            self.raise_ruutu_error(req.content)
            if text:
                return req.text
            return req.content

        except requests.exceptions.ConnectionError as error:
            self.log('Connection Error: - %s' % error.message)
            raise
        except requests.exceptions.RequestException as error:
            self.log('Error: - %s' % error.value)
            raise

    def raise_ruutu_error(self, response):
        try:
            response = json.loads(response)
            if isinstance(response, dict):
                if 'message' in response.keys():
                    if 'errorKey' in response['message'].keys():
                        raise self.RuutuError(response['message']['message'])
                        #"message":"Invalid username or password",
                        #"errorKey":"USER_NOT_FOUND",
                    else:
                        if response['message'].get('message'):
                            raise self.RuutuError(response['message']['message'])
                        else:
                            raise self.RuutuError(response['message'])

        except KeyError:
            pass
        except ValueError:  # when response is not in json
            pass

    def save_credentials(self, credentials):
        credentials_dict = json.loads(credentials)

        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials_dict))

    def reset_credentials(self):
        credentials = {}
        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials))

    def get_credentials(self):
        try:
            with open(self.credentials_file, 'r') as fh_credentials:
                credentials_dict = json.loads(fh_credentials.read())
                return credentials_dict
        except IOError:
            self.reset_credentials()
            with open(self.credentials_file, 'r') as fh_credentials:
                return json.loads(fh_credentials.read())

    def login(self, username=None, password=None):
        #https://prod-component-api.nm-services.nelonenmedia.fi/auth/init/login?widget=true&client=ruutu-prod&ref_url=https%3A%2F%2Fwww.ruutu.fi%2F&region=fi-FI&iframe=true
        login_page_url = 'https://prod-component-api.nm-services.nelonenmedia.fi/auth/init/login'

        login_page_params = {
            'widget': 'true',
            'client': 'ruutu-prod',
            'ref_url': 'https://www.ruutu.fi/',
            'region': 'fi-FI',
            'iframe': 'true'
        }

        login_page_content = self.make_request(login_page_url, 'get', params=login_page_params)

        # Parse json from html
        soup = BeautifulSoup(login_page_content, 'html.parser')
        data = soup.find_all('script')[5]
        data = data.get_text()

        data = data.strip()  # strip() is used to remove starting and trailing
        data = data.encode('utf-8').decode('unicode_escape')
        data = data.replace("window.App=", "")
        data = ''.join(data.split())  # remove all whitespace characters (space, tab, newline, and so on)

        data = data.replace(
            'functionStoreConnector(props,context){React.Component.apply(this,arguments);this.state=this.getStateFromStores();this._onStoreChange=null;this._isMounted=false;}',
            '""')
        data = data.replace('function(t,a,n){try{returne(t,a,n)}catch(e){returnn(e)}}', '""')
        data = data[:-1]

        login_page_json = json.loads(data)

        csrf = login_page_json['context']['plugins']['FetchrPlugin']['xhrContext']['_csrf']

        client_id = \
            login_page_json['context']['dispatcher']['stores']['RouteStore']['currentNavigate']['route']['query'][
            'client_id']
        cancel_uri = \
            login_page_json['context']['dispatcher']['stores']['RouteStore']['currentNavigate']['route']['query'][
            'cancel_uri']
        redirect_uri = \
            login_page_json['context']['dispatcher']['stores']['RouteStore']['currentNavigate']['route']['query'][
            'redirect_uri']
        state = json.loads(data)['context']['dispatcher']['stores']['RouteStore']['currentNavigate']['route']['query'][
            'state']
        service = \
            login_page_json['context']['dispatcher']['stores']['RouteStore']['currentNavigate']['route']['query'][
            'service']

        querystring = '?cancel_uri=' + cancel_uri + '&client_id=' + client_id + '&facebookAuth=true&googleAuth=true&hide_logo=false&iframe=true&redirect_uri=' + redirect_uri + '&service=' + service + '&silent=false&state=' + state + '&style=ruutu2&email=' + username

        sso_url = 'https://tili.sanoma.fi/sso/api'

        params = {
            '_csrf': csrf
        }

        payload = {
            "requests": {
                "g0":
                    {"resource": "loginService", "operation": "create", "params": {}, "body":
                        {"client_id": client_id, "redirect_uri": redirect_uri, "state": state,
                         "queryString": querystring, "service": service, "username": username, "password": password,
                         "failedAttempts": 0}
                     }

            },
            "context":
                {"_csrf": csrf}

        }

        headers = {'content-type': 'application/json'}

        request = json.loads(self.make_request(sso_url, 'post', params=params, payload=json.dumps(payload), headers=headers))

        if request['g0']['data']['message'] == 'Login successful':
            parsed = urlparse.urlparse(request['g0']['data']['redirectUri'])
            code =  urlparse.parse_qs(parsed.query)['code']
            state = urlparse.parse_qs(parsed.query)['state']

            access_token = self.get_tokens(code, state)['tokens']['access_token']
            gatling_token = self.create_session(access_token)['token']

            credentials = self.get_user_data(gatling_token)
            self.save_credentials(json.dumps(credentials))

        return True

    def get_tokens(self, code, state):
        url = 'https://prod-component-api.nm-services.nelonenmedia.fi/auth/get-tokens'

        params = {
            'code': code,
            'state': state,
            'client': 'ruutu-prod'
        }

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def create_session(self, access_token):
        url = 'https://gatling.nelonenmedia.fi/auth/create-session-by-access-token'

        payload = {
            'access_token': access_token
        }

        headers = {'content-type': 'application/x-www-form-urlencoded'}

        data = json.loads(self.make_request(url, 'post', payload=payload, headers=headers))

        return data

    def get_user_data(self, gatling_token):
        url = 'https://gatling.nelonenmedia.fi/auth/identify/v2'

        params = {
            'gatling_token': gatling_token,
            'service': 'ruutu'
        }

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def get_page(self, url):

        data = json.loads(self.make_request(url, 'get'))

        return data

    def get_page_json(self, page_type, page_id, userroles):
        url = 'https://prod-component-api.nm-services.nelonenmedia.fi/api/{page_type}/{page_id}'.format(page_type=page_type, page_id=page_id)

        params = {
            'app': 'ruutu',
            'client': 'web',
            'userroles': userroles
        }

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def get_grid_json(self, url, ruutu_params=None, offset=None, limit=None):
        params = json.loads(ruutu_params)

        if offset is not None and limit is not None:
            params['offset'] = offset
            params['limit'] = limit

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def add_favorite(self, series_id, gatling_token):
        url = 'https://gatling.nelonenmedia.fi/storage/favorite'

        payload = {
            'gatling_token': gatling_token,
            'type': 'series',
            'item': series_id
        }

        return self.make_request(url, 'post', params=None, payload=payload, headers=None)

    def remove_favorite(self, series_id, gatling_token):
        url = 'https://gatling.nelonenmedia.fi/storage/favorite'

        payload = {
            'gatling_token': gatling_token,
            'type': 'series',
            'item': series_id
        }

        return self.make_request(url, 'delete', params=None, payload=payload, headers=None)

    def update_unfinished(self, video_id, time, gatling_token):
        url = 'https://gatling.nelonenmedia.fi/storage/unfinished'

        payload = {
            'video': video_id,
            'bucket': 'ruutu',
            'time': time,
            'gatling_token': gatling_token
        }

        return self.make_request(url, 'post', params=None, payload=payload, headers=None)

    def update_finished(self, video_id, gatling_token):
        url = 'https://gatling.nelonenmedia.fi/storage/unfinished'

        payload = {
            'video': video_id,
            'bucket': 'ruutu',
            'finished': 1,
            'gatling_token': gatling_token
        }

        return self.make_request(url, 'delete', params=None, payload=payload, headers=None)

    def get_next_episode_id(self, video_id):
        url = 'https://gatling.nelonenmedia.fi/recommend'

        params = {
            'api_key': 'cb60991daf94becc1a88b17b16d648b4',
            'id': video_id
        }

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def get_episode_info(self, video_id):
        url = 'https://dynamic-gatling.nelonenmedia.fi/cos/videos/'

        params = {
            'api_key': 'cb60991daf94becc1a88b17b16d648b4',
            'id': video_id
        }

        data = json.loads(self.make_request(url, 'get', params=params))

        return data

    def get_stream(self, video_id, type):
        stream = {}

        url = 'https://gatling.nelonenmedia.fi/media-xml-cache?id={video_id}&v=2'.format(video_id=video_id)

        media_xml = xmltodict.parse(self.make_request(url, 'get', headers=None))

        if type == 'live':
            stream_auth_url = 'https://gatling.nelonenmedia.fi/auth/access/v2'

            stream_auth_params = {
                'stream': media_xml['Playerdata']['Clip']['AppleMediaFiles']['AppleMediaFile'],
                'timestamp': '1546978227167',
                'gatling_token': self.get_credentials()['token']
            }

            stream_auth_m3u8 = self.make_request(stream_auth_url, 'get', params=stream_auth_params)

            stream['drm_protected'] = False
            stream['video_url'] = stream_auth_m3u8

        # DRM Protection check
        elif media_xml['Playerdata']['Clip']['DRM']:
            stream['drm_protected'] = True

            drm_check_url = media_xml['Playerdata']['Clip']['DRM']['@check_url']
            asset_id = media_xml['Playerdata']['Clip']['DRM']['@asset_id']

            params = {
                'device_type': 'WEB',
                'nid': video_id,
                'asset_id': asset_id,
                'drm': 'CENC',
                'format': 'DASH',
                'anonymous': 'false',
                'account_id': 'true',
                'device_id': '03b9e8df-f03f-4d61-bccb-c5c6c82258c2',
                'api_key': 'cb60991daf94becc1a88b17b16d648b4'
            }

            # If user is logged in add gatling_token to params, this is needed for playing drm protected Ruutu+ videos
            if self.get_credentials().get('accountId'):
                params['gatling_token'] = self.get_credentials()['token']

            drm_json = json.loads(self.make_request(drm_check_url, 'get', params=params))

            stream['drm_token'] = urllib.quote_plus(drm_json['empDrmKey']['playToken'])
            stream['video_url'] = 'https:' + drm_json['empDrmKey']['mediaLocator']

            mpd_playlist = xmltodict.parse(self.make_request(stream['video_url'], 'get'))

            if mpd_playlist['MPD']['Period']['@id'] == 'P0':
                stream['license_url'] = mpd_playlist['MPD']['Period']['AdaptationSet'][0]['ContentProtection'][1]['ms:laurl']['@licenseUrl']

        else:
            stream['drm_protected'] = False

            params = {
                'stream': media_xml['Playerdata']['Clip']['AppleMediaFiles']['AppleMediaFile']
            }

            video_url = self.make_request('https://gatling.nelonenmedia.fi/auth/access/v2', 'get', params=params)

            stream['video_url'] = video_url

            #stream['video_url'] = media_xml['Playerdata']['Clip']['AppleMediaFiles']['AppleMediaFile']

        return stream

    def unix_to_datetime(self, unix_timestamp):
        local_time = datetime.fromtimestamp(unix_timestamp)

        return local_time.strftime("%d.%m.%Y %H.%M")
