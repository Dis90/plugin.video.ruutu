# -*- coding: utf-8 -*-

import os
import urllib.request, urllib.parse, urllib.error
import re
import sys

from .ruutu import Ruutu

import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
from xbmcaddon import Addon
import inputstreamhelper
import AddonSignals

from PIL import Image
from io import StringIO

class KodiHelper(object):
    def __init__(self, base_url=None, handle=None):
        addon = self.get_addon()
        self.base_url = base_url
        self.handle = handle
        self.addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
        self.addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
        self.addon_name = addon.getAddonInfo('id')
        self.addon_version = addon.getAddonInfo('version')
        self.language = addon.getLocalizedString
        self.logging_prefix = '[%s-%s]' % (self.addon_name, self.addon_version)
        if not xbmcvfs.exists(self.addon_profile):
            xbmcvfs.mkdir(self.addon_profile)
        self.r = Ruutu(self.addon_profile, True)
        AddonSignals.registerSlot('upnextprovider', self.addon_name + '_play_action', self.play_upnext)

    def get_addon(self):
        """Returns a fresh addon instance."""
        return Addon()

    def get_setting(self, setting_id):
        addon = self.get_addon()
        setting = addon.getSetting(setting_id)
        if setting == 'true':
            return True
        elif setting == 'false':
            return False
        else:
            return setting

    def set_setting(self, key, value):
        return self.get_addon().setSetting(key, value)

    def log(self, string):
        msg = '%s: %s' % (self.logging_prefix, string)
        xbmc.log(msg=msg, level=xbmc.LOGDEBUG)

    def dialog(self, dialog_type, heading, message=None, options=None, nolabel=None, yeslabel=None):
        dialog = xbmcgui.Dialog()
        if dialog_type == 'ok':
            dialog.ok(heading, message)
        elif dialog_type == 'yesno':
            return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
        elif dialog_type == 'select':
            ret = dialog.select(heading, options)
            if ret > -1:
                return ret
            else:
                return None

    def get_user_input(self, heading, hidden=False):
        keyboard = xbmc.Keyboard('', heading, hidden)
        keyboard.doModal()
        if keyboard.isConfirmed():
            query = keyboard.getText()
            self.log('User input string: %s' % query)
        else:
            query = None

        if query and len(query) > 0:
            return query
        else:
            return None

    def check_for_credentials(self):
        username = self.get_setting('username')
        password = self.get_setting('password')

        if not username or not password:
            return False
        else:
            return True

    def check_userrole(self):
        # "userroles":[
        # "authenticated",
        # "ruutu_plus_pro",
        # "ruutu_plus_urheilu",
        # "ruutu_plus_viihde",
        # "subscriber"
        # ],

        # For registered user ruutuRole is null
        if self.check_for_credentials():
            if self.r.get_credentials().get('accountId'):
                if self.r.get_credentials()['service']['ruutuRole'] is None:
                    return 'authenticated' # Logged in user without Ruutu+
                else:
                    return self.r.get_credentials()['service']['ruutuRole'] # Ruutu+ user
            else:
                return 'anonymous' # Credentials file not found
        else:
            return 'anonymous' # Not logged in user

    def login_process(self):
        username = self.get_setting('username')
        password = self.get_setting('password')
        self.r.login(username, password)

    def reset_credentials(self):
        self.r.reset_credentials() # Reset credentials file
        self.set_setting('username', '')
        self.set_setting('password', '')

    def create_ruutuplus_thumb(self, thumb_url, id):
        thumb = self.r.make_request(thumb_url, 'get')

        background = Image.open(StringIO(thumb))
        foreground = Image.open(self.addon_path + '/resources/sticker.png')

        background.paste(foreground, (5, 5), foreground)
        background.save(self.r.tempdir + '/' + str(id) + '.png')
        return self.r.tempdir + '/' + str(id) + '.png'

    def add_item(self, title, params, items=False, folder=True, playable=False, info=None, art=None, content=False, menu=None, resume=None, total=None):
        addon = self.get_addon()
        listitem = xbmcgui.ListItem(label=title)

        if playable:
            listitem.setProperty('IsPlayable', 'true')
            folder = False
        if resume:
            listitem.setProperty("ResumeTime", str(resume))
            listitem.setProperty("TotalTime", str(total))
        if art:
            listitem.setArt(art)
        else:
            art = {
                'icon': addon.getAddonInfo('icon'),
                'fanart': addon.getAddonInfo('fanart')
            }
            listitem.setArt(art)
        if info:
            listitem.setInfo('video', info)
        if content:
            xbmcplugin.setContent(self.handle, content)
        if menu:
            listitem.addContextMenuItems(menu)

        recursive_url = self.base_url + '?' + urllib.parse.urlencode(params)

        if items is False:
            xbmcplugin.addDirectoryItem(self.handle, recursive_url, listitem, folder)
        else:
            items.append((recursive_url, listitem, folder))
            return items

    def eod(self):
        """Tell Kodi that the end of the directory listing is reached."""
        xbmcplugin.endOfDirectory(self.handle)

    def play_upnext(self, data):
        self.log('Start playing from UpNext')
        self.log('Video id: ' + str(data['video_id']))

        xbmc.executebuiltin('PlayerControl(Stop)')
        media = 'plugin://' + self.addon_name + '/?action=play&video_id={video_id}&type=video&sticker={sticker}'.format(video_id=data['video_id'], sticker=data['sticker'])
        xbmc.executebuiltin('PlayMedia({})'.format(media))

    def play_item(self, video_id, type, sticker):
        if self.check_userrole() in ('authenticated', 'anonymous') and sticker == 'entertainment':
            self.dialog('ok', self.language(30006), self.language(30012))
        else:
            stream = self.r.get_stream(video_id, type)
            playitem = xbmcgui.ListItem(path=stream['video_url'])

            # DRM protected videos
            if stream['drm_protected']:
                is_helper = inputstreamhelper.Helper('mpd', drm='com.widevine.alpha')
                if is_helper.check_inputstream():
                    playitem.setProperty('inputstream', 'inputstream.adaptive')
                    playitem.setProperty('inputstream.adaptive.manifest_type', 'mpd')
                    playitem.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')

                    license_url = stream['license_url'] + '&token=' + stream['drm_token']

                    playitem.setProperty('inputstream.adaptive.license_key', license_url + '||R{SSM}|')

            if type == 'video':

                # Get current episode info
                current_ep_info = self.r.get_episode_info(video_id)
                info = {
                    'mediatype': 'episode',
                    'title': current_ep_info['videos'][0]['episode_name'] if current_ep_info['videos'][0].get(
                        'episode_name') else current_ep_info['videos'][0].get('name'),
                    'tvshowtitle': current_ep_info['videos'][0].get('series'),
                    'season': current_ep_info['videos'][0].get('season'),
                    'episode': current_ep_info['videos'][0].get('episode'),
                    'plot': current_ep_info['videos'][0].get('description'),
                    'duration': current_ep_info['videos'][0].get('runtime'),
                    'aired': current_ep_info['videos'][0].get('created')
                }

                playitem.setInfo('video', info)

                art = {
                    'fanart': current_ep_info['videos'][0]['media']['images'][0]['1920x1080'] if
                    current_ep_info['videos'][0]['media']['images'][0].get('1920x1080') else None,
                    'thumb': current_ep_info['videos'][0]['media']['images'][0]['1920x1080'] if
                    current_ep_info['videos'][0]['media']['images'][0].get('1920x1080') else None
                }

                playitem.setArt(art)

                # Watched status from Ruutu
                if self.r.get_credentials().get('accountId'):
                    history = self.r.get_page('https://gatling.nelonenmedia.fi/storage/history?unfinished=true&gatling_token=' + self.r.get_credentials()['token'])
                    user_unfinished_videos = ",".join([str(x['video']) for x in history])

                    if str(current_ep_info['videos'][0]['id']) in user_unfinished_videos:
                        for h in history:
                            if h['video'] == current_ep_info['videos'][0]['id']:
                                if h['unfinished'] is False: # Watched video
                                    resume = 0
                                    total = current_ep_info['videos'][0].get('runtime')
                                elif h['watched'] is None: # Unwatched video
                                    resume = 0
                                    total = 1
                                else: # Partly watched
                                    self.log('Resume from: ' + str(h['watched']))
                                    resume = h['watched']
                                    total = current_ep_info['videos'][0].get('runtime')
                    else: # Unwatched video
                        resume = 0
                        total = 1

                    playitem.setProperty("ResumeTime", str(resume))
                    playitem.setProperty("TotalTime", str(total))

            player = RuutuPlayer()
            player.resolve(playitem)

            if type == 'video':
                player.video_id = video_id
                player.current_episode_info = info
                player.current_episode_art = art

                if self.r.get_credentials().get('accountId'):

                    while not xbmc.abortRequested and player.running:
                        if player.isPlayingVideo():
                            player.video_totaltime = player.getTotalTime()
                            player.video_lastpos = player.getTime()
                            player.logged_in = True

                        xbmc.sleep(1000)

class RuutuPlayer(xbmc.Player):
    def __init__(self):
        base_url = sys.argv[0]
        handle = int(sys.argv[1])
        self.helper = KodiHelper(base_url, handle)
        self.video_id = 0
        self.current_episode_info = ''
        self.current_episode_art = ''
        self.video_lastpos = 0
        self.video_totaltime = 0
        self.running = False
        self.logged_in = False

    def resolve(self, li):
        xbmcplugin.setResolvedUrl(self.helper.handle, True, listitem=li)
        self.running = True

    def onPlayBackStarted(self):
        self.helper.log('Getting next episode info')
        next_ep_id = self.helper.r.get_next_episode_id(self.video_id)

        if next_ep_id['next_in_sequence'].get('nid'):
            next_ep_info = self.helper.r.get_episode_info(next_ep_id['next_in_sequence']['nid'])

            next_ep_title = next_ep_info['videos'][0]['episode_name'] if next_ep_info['videos'][0].get('episode_name') else next_ep_info['videos'][0].get('name')

            self.helper.log('Next episode name: ' + next_ep_title.encode('utf-8'))
            self.helper.log('Current episode name: ' + self.current_episode_info['title'].encode('utf-8'))

            current_episode = {}
            current_episode["episodeid"] = self.video_id
            current_episode["tvshowid"] = ''
            current_episode["title"] = self.current_episode_info['title']
            current_episode["art"] = {}
            current_episode["art"]["tvshow.poster"] = ''
            current_episode["art"]["thumb"] = self.current_episode_art['thumb']
            current_episode["art"]["tvshow.fanart"] = self.current_episode_art['fanart']
            current_episode["art"]["tvshow.landscape"] = ''
            current_episode["art"]["tvshow.clearart"] = ''
            current_episode["art"]["tvshow.clearlogo"] = ''
            current_episode["plot"] = self.current_episode_info['title']
            current_episode["showtitle"] = self.current_episode_info['tvshowtitle']
            current_episode["playcount"] = ''
            current_episode["season"] = self.current_episode_info['season']
            current_episode["episode"] = self.current_episode_info['episode']
            current_episode["rating"] = None
            current_episode["firstaired"] = self.current_episode_info['aired']

            next_episode = {}
            next_episode["episodeid"] = next_ep_info['videos'][0]['id']
            next_episode["tvshowid"] = ''
            next_episode["title"] = next_ep_title
            next_episode["art"] = {}
            next_episode["art"]["tvshow.poster"] = ''
            next_episode["art"]["thumb"] = next_ep_info['videos'][0]['media']['images'][0]['1920x1080'] if next_ep_info['videos'][0]['media']['images'][0].get('1920x1080') else None
            next_episode["art"]["tvshow.fanart"] = next_ep_info['videos'][0]['media']['images'][0]['1920x1080'] if next_ep_info['videos'][0]['media']['images'][0].get('1920x1080') else None
            next_episode["art"]["tvshow.landscape"] = ''
            next_episode["art"]["tvshow.clearart"] = ''
            next_episode["art"]["tvshow.clearlogo"] = ''
            next_episode["plot"] = next_ep_info['videos'][0].get('description')
            next_episode["showtitle"] = next_ep_info['videos'][0].get('series')
            next_episode["playcount"] = ''
            next_episode["season"] = next_ep_info['videos'][0].get('season')
            next_episode["episode"] = next_ep_info['videos'][0].get('episode')
            next_episode["rating"] = None
            next_episode["firstaired"] = next_ep_info['videos'][0].get('created')

            if next_ep_info['videos'][0]['premium'] == 1:
                sticker = 'entertainment'
            else:
                sticker = None

            play_info = {}
            play_info['video_id'] = next_ep_info['videos'][0]['id']
            play_info['sticker'] = sticker

            next_info = {
                'current_episode': current_episode,
                'next_episode': next_episode,
                'play_info': play_info,
                'notification_time': ''
            }

            AddonSignals.sendSignal("upnext_data", next_info, source_id=self.helper.addon_name)

        else:
            self.helper.log('No next episode available')

    def onPlayBackEnded(self):
        if self.logged_in:
            if self.running:
                self.running = False
                self.helper.log('Playback ended')
                self.helper.r.update_finished(self.video_id, self.helper.r.get_credentials()['token'])
                return xbmc.executebuiltin('Container.Refresh')

    def onPlayBackStopped(self):
        if self.logged_in:
            if self.running:
                self.running = False
                self.helper.log('Stopped video id:' + str(self.video_id))
                video_lastpos2 = format(self.video_lastpos, '.2f')
                video_totaltime2 = format(self.video_totaltime, '.2f')
                self.helper.log('totaltime: ' + video_totaltime2)
                self.helper.log('lastpos: ' + video_lastpos2)

                if (self.video_lastpos * 100) / self.video_totaltime >= 90:  # Watched
                    self.helper.r.update_finished(self.video_id, self.helper.r.get_credentials()['token'])
                    return xbmc.executebuiltin('Container.Refresh')
                else:
                    self.helper.r.update_unfinished(self.video_id, video_lastpos2, self.helper.r.get_credentials()['token'])
                    return xbmc.executebuiltin('Container.Refresh')

