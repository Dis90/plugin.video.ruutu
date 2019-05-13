# -*- coding: utf-8 -*-

import sys
from urlparse import parse_qsl
import json
import re

from resources.lib.kodihelper import KodiHelper

base_url = sys.argv[0]
handle = int(sys.argv[1])
helper = KodiHelper(base_url, handle)

def list_pages():
    pages = helper.r.get_page('https://prod-component-api.nm-services.nelonenmedia.fi/api/navigation/')

    for page in pages['main']:
        for client in page['clients']:
            # Show only pages for ruutufi
            if client == 'ruutufi':
                if page.get('children'):
                    params = {
                        'action': 'list_children_pages',
                        'children': json.dumps(page['children'])
                    }

                    helper.add_item(page['title'], params)

                # Pages without children pages
                else:
                    # Hide frontpage category
                    if page['action']['page_id'] != 200:
                        params = {
                            'action': 'list_grids',
                            'page_id': str(page['action']['page_id']),
                            'userroles': helper.check_userrole()
                        }

                        helper.add_item(page['title'], params)

    # Search
    helper.add_item(helper.language(30007), params={'action': 'search'})

    # Show 'Oma Ruutu' only when user is logged in
    if helper.r.get_credentials().get('accountId'):

        params = {
            'action': 'list_grids',
            'page_id': 2000,
            'userroles': helper.check_userrole()
        }

        helper.add_item(helper.language(30011), params)

    # Frontpage grids
    list_grids(200, helper.check_userrole())

    helper.eod()

# List TV -> Jännitys ja draama, Cirkus - Brittidaama, Kaikki ohjelmat etc
def list_children_pages(children):
    for page in json.loads(children):
        for client in page['clients']:
            # Show only pages for ruutufi
            if client == 'ruutufi':
                # Check that it is actually category and not just placeholder
                if page.get('action'):
                    params = {
                        'action': 'list_grids',
                        'page_id': str(page['action']['page_id']),
                        'userroles': helper.check_userrole()
                    }

                    helper.add_item(page['label']['text'], params)

    helper.eod()

def list_search_result_grids(search_term):
    ruutu_params = {
        'offset': 0,
        'search_term': search_term
    }

    results = helper.r.get_grid_json('https://prod-component-api.nm-services.nelonenmedia.fi/api/component/336', json.dumps(ruutu_params))

    for result in results['items']:
        # Hide empty categories
        if result['content']['hits'] > 0:
            title = result['label']['text']

            params = {
                'action': 'list_grid_content',
                'url': result['content']['query']['url'],
                'ruutu_params': json.dumps(result['content']['query']['params']),
                'kodi_page': 1
            }

            info = {
                'plot': helper.language(30008) + str(result['content']['hits'])
            }

            helper.add_item(title, params=params, info=info)

    helper.eod()

# List Katsotuimmat, Ruutu suosittelee etc
def list_grids(page_id, userroles):
    grids = helper.r.get_page_json('page', page_id, userroles)

    for grid in grids['components']:
        # 545 & 665 = Urheilulähetykset, 687 & 689 = Tv-opas, 6530200 = Tulossa olevat sarjat, 653 & 653200 = Tulossa olevat elokuvat
        hide_grids = [545, 665, 687, 689, 6530200, 653, 653200]
        if grid['label'].get('text') and grid['id'] not in hide_grids:

            # Jatka katsomista
            if 'user_unfinished_videos' in grid['content']['query']['params'].keys():
                history = helper.r.get_page(
                    'https://gatling.nelonenmedia.fi/storage/history?unfinished=true&gatling_token=' +
                    helper.r.get_credentials()[
                        'token'])

                user_unfinished_videos = ''
                for x in history:
                    # Remove watched videos from list
                    if x['unfinished'] is True:
                        user_unfinished_videos+= ',' + str(x['video'])

                ruutu_params = {
                    'offset': 0,
                    'user_unfinished_videos': user_unfinished_videos

                }

            # Omat suosikit
            elif 'user_favorite_series' in grid['content']['query']['params'].keys():
                favorite = helper.r.get_page(
                    'https://gatling.nelonenmedia.fi/storage/favorite?gatling_token=' + helper.r.get_credentials()[
                        'token'])

                user_favorite_series = ''
                for x in favorite:
                    # Show only Ruutu favorites
                    if x['type'] == 'series':
                        user_favorite_series += ',' + str(x['item'])

                ruutu_params = {
                    'offset': 0,
                    'user_favorite_series': user_favorite_series

                }

            else:
                ruutu_params = grid['content']['query']['params']


            params = {
                'action': 'list_grid_content',
                'url': grid['content']['query']['url'],
                'ruutu_params': json.dumps(ruutu_params),
                'kodi_page': 1
            }

            helper.add_item(grid['label']['text'], params)

    helper.eod()

def list_grid_content(url, ruutu_params, kodi_page):
    page_size = helper.get_setting('items_per_page')
    offset = (int(kodi_page) - 1) * int(page_size)

    items = helper.r.get_grid_json(url, ruutu_params, offset=offset, limit=page_size)

    # Load favorites and history only when user is logged in
    if helper.r.get_credentials().get('accountId'):
        favorite = helper.r.get_page('https://gatling.nelonenmedia.fi/storage/favorite?gatling_token=' + helper.r.get_credentials()['token'])
        user_favorite_series = ",".join([str(x['item']) for x in favorite])

        history = helper.r.get_page('https://gatling.nelonenmedia.fi/storage/history?unfinished=true&gatling_token=' + helper.r.get_credentials()['token'])
        user_unfinished_videos = ",".join([str(x['video']) for x in history])

    # Extra info for episodes
    if json.loads(ruutu_params).get('current_series_id'):

        ruutu_params2 = {
            'current_primary_content': 'series',
            'current_series_id': json.loads(ruutu_params)['current_series_id']
        }

        tvshow_extra_info = helper.r.get_grid_json('https://prod-component-api.nm-services.nelonenmedia.fi/api/component/26001', json.dumps(ruutu_params2))

        genre = tvshow_extra_info['items'][0]['subtitle'].split(', ')
        tvshowtitle = tvshow_extra_info['items'][0]['title']

    for item in items['items']:
        if item['link']: # Movie or episode is available
            # Movies and episodes
            if item['link']['target']['type'] == 'video_id':
                # Remove episode number from title
                title = re.sub(r'\d+\ -', '', item['title']).lstrip()
                # Remove agelimit from title
                title = re.sub(r'\(.*?\)', '', title).rstrip()

                if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker') is False:
                    list_title = title + ' [RUUTU+]'
                else:
                    list_title = title

                params = {
                    'action': 'play',
                    'type': 'video',
                    'video_id': item['link']['target']['value'],
                    'sticker': item['sticker'] if item['sticker'] else None
                }

                info = {
                    'mediatype': 'episode',
                    'title': title,
                    'plot': item.get('description'),
                    'duration': item['timebar']['end'] if item.get('timebar') else None,
                    'aired': helper.r.unix_to_datetime(item['rights'][0]['start']) if item.get('rights') else None
                }

                if item.get('tv_ratings'):
                    info['mpaa'] = item['tv_ratings']['agelimit'] if item['tv_ratings']['agelimit'] != 0 else None

                # Watched status from Ruutu
                if helper.r.get_credentials().get('accountId'):
                    if str(item['link']['target']['value']) in user_unfinished_videos:
                        for h in history:
                            if h['video'] == item['link']['target']['value']:
                                if h['unfinished'] is False: # Watched video
                                    info['playcount'] = 1
                                    resume = 0
                                    total = item['timebar']['end']
                                elif h['watched'] is None: # Unwatched video
                                    info['playcount'] = 0
                                    resume = 0
                                    total = 1
                                else: # Partly watched
                                    resume = h['watched']
                                    total = item['timebar']['end']
                    else: # Unwatched video
                        info['playcount'] = 0
                        resume = 0
                        total = 1
                else: # User is not logged in, use Kodi internal resume points
                    resume = None
                    total = None

                # Get extra info for episodes
                if json.loads(ruutu_params).get('current_series_id'):
                    info['tvshowtitle'] = tvshowtitle
                    info['genre'] = genre

                # Get season and episode number from description
                if item.get('description'):
                    pattern = re.compile(
                        r"""(?:Kausi)(?:\s)(?P<s>\d+)(?:.*)(?:Jakso|\n)(?:\s)(?P<ep>\d+)""",
                        re.VERBOSE)
                    se = re.search(pattern, item['description'])
                    if se:
                        info['season'] = se.group('s')
                        info['episode'] = se.group('ep')

                if item.get('media'):
                    if item['media'].get('images'):
                        item_art = {
                            'fanart': item['media']['images']['1920x1080'] if item['media']['images'].get('1920x1080') else None
                        }

                        if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker'):
                            item_art['thumb'] = helper.create_ruutuplus_thumb(item['media']['images']['640x360'],
                                                                              item['link']['target']['value'])
                        else:
                            item_art['thumb'] = item['media']['images']['640x360']
                    else:
                        item_art = {}
                else:
                    item_art = {}

                helper.add_item(list_title, params=params, info=info, art=item_art, content='episodes', playable=True, resume=resume, total=total)

            # Tv-shows
            if item['link']['target']['type'] == 'series_id':

                if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker') is False:
                    title = item['title'] + ' [RUUTU+]'
                else:
                    title = item['title']

                params = {
                    'action': 'list_seasons',
                    'series_id': item['id']
                }

                info = {
                    'mediatype': 'tvshow',
                    'plot': item.get('description')
                }

                # Show context menu only when user is logged in
                if helper.r.get_credentials().get('accountId'):
                    if str(item['id']) not in user_favorite_series:
                        menu = []
                        menu.append((helper.language(30015), 'RunPlugin(plugin://plugin.video.ruutu/?action=add_favorite&series_id=' + str(item['id']) + '&gatling_token=' + helper.r.get_credentials()['token'] + ')',))
                    else:
                        menu = []
                        menu.append((helper.language(30016), 'RunPlugin(plugin://plugin.video.ruutu/?action=remove_favorite&series_id=' + str(item['id']) + '&gatling_token=' + helper.r.get_credentials()['token'] + ')',))
                else:
                    menu = None

                if item.get('media'):
                    if item['media'].get('images'):
                        item_art = {
                            'fanart': item['media']['images']['1920x1080'] if item['media']['images'].get('1920x1080') else None
                        }

                        if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker'):
                            item_art['thumb'] = helper.create_ruutuplus_thumb(item['media']['images']['640x360'],
                                                                          item['id'])
                        else:
                            item_art['thumb'] = item['media']['images']['640x360']
                    else:
                        item_art = {}
                else:
                    item_art = {}

                helper.add_item(title, params, info=info, art=item_art, content='tvshows', menu=menu)

            # Channels
            if item['link']['target']['type'] == 'channel_id':
                channel_name = item['title_detail']
                show_name = item['title_time'] + ' ' + item['title']

                if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker') is False:
                    title = channel_name + ' [RUUTU+]'
                else:
                    title = channel_name

                video_id =  helper.r.get_page_json('channel', item['link']['target']['value'], helper.check_userrole())['components'][0]['content']['items'][0]['content']['items'][0]['video_id']

                params = {
                    'action': 'play',
                    'type': 'live',
                    'video_id': video_id,
                    'sticker': item['sticker'] if item['sticker'] else None
                }

                info = {
                    'mediatype': 'video',
                    'title': channel_name,
                    'plot': show_name
                }

                if item.get('media'):
                    if item['media'].get('images'):
                        item_art = {
                            'fanart': item['media']['images']['1920x1080'] if item['media']['images'].get('1920x1080') else None
                        }

                        if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker'):
                            item_art['thumb'] = helper.create_ruutuplus_thumb(item['media']['images']['640x360'],
                                                                              video_id)
                        else:
                            item_art['thumb'] = item['media']['images']['640x360']
                    else:
                        item_art = {}
                else:
                    item_art = {}

                helper.add_item(title, params=params, info=info, art=item_art, content='videos', playable=True)

            # Sport streams
            if item['link']['target']['type'] == 'stream_id':
                if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker') is False:
                    title = item['title_time'] + ' ' + item['title'] + ' [RUUTU+]'
                else:
                    title = item['title_time'] + '' + item['title']

                video_id = helper.r.get_page_json('stream', item['link']['target']['value'], helper.check_userrole())['components'][0]['content']['items'][0]['video_id']

                params = {
                    'action': 'play',
                    'type': 'live',
                    'video_id': video_id,
                    'sticker': item['sticker'] if item['sticker'] else None
                }

                info = {
                    'mediatype': 'video',
                    'title': item['title'],
                    'plot': item.get('description')
                }

                if item.get('media'):
                    if item['media'].get('images'):
                        item_art = {
                            'fanart': item['media']['images']['1920x1080'] if item['media']['images'].get('1920x1080') else None
                        }

                        if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker'):
                            item_art['thumb'] = helper.create_ruutuplus_thumb(item['media']['images']['640x360'],
                                                                              video_id)
                        else:
                            item_art['thumb'] = item['media']['images']['640x360']
                    else:
                        item_art = {}
                else:
                    item_art = {}

                helper.add_item(title, params=params, info=info, art=item_art, content='videos', playable=True)

        # Upcoming videos
        else:
            if item.get('upcoming'):
                if item['upcoming'] is True:
                    # Remove episode number from title
                    title = re.sub(r'\d+\ -', '', item['title']).lstrip()

                    if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker') is False:
                        title = title + ' [RUUTU+] ' + helper.language(30010) + ' ' + helper.r.unix_to_datetime(item['rights'][0]['start'])
                    else:
                        title = title + ' ' + helper.language(30010) + ' ' + helper.r.unix_to_datetime(item['rights'][0]['start'])

                    params = {}

                    info = {
                        'mediatype': 'episode',
                        'title': title,
                        'plot': item.get('description')
                    }

                    # Get extra info for episodes
                    if json.loads(ruutu_params).get('current_series_id'):
                        info['tvshowtitle'] = tvshowtitle
                        info['genre'] = genre

                    # Get season and episode number from description
                    if item.get('description'):
                        pattern = re.compile(
                            r"""(?:Kausi)(?:\s)(?P<s>\d+)(?:.*)(?:Jakso|\n)(?:\s)(?P<ep>\d+)""",
                            re.VERBOSE)
                        m = re.search(pattern, item['description'])
                        if m:
                            info['season'] = m.group('s')
                            info['episode'] = m.group('ep')

                    if item.get('media'):
                        if item['media'].get('images'):
                            item_art = {
                                'fanart': item['media']['images']['1920x1080'] if item['media']['images'].get(
                                    '1920x1080') else None
                            }
                            # current_series_id for ruutu+ thumb filename
                            if item['sticker'] == 'entertainment' and helper.get_setting('ruutuplus_sticker'):
                                item_art['thumb'] = helper.create_ruutuplus_thumb(item['media']['images']['640x360'],
                                                                                  json.loads(ruutu_params)['current_series_id'])
                            else:
                                item_art['thumb'] = item['media']['images']['640x360']
                        else:
                            item_art = {}
                    else:
                        item_art = {}

                    helper.add_item(title, params=params, info=info, art=item_art, content='episodes', playable=False)

    # Next page
    if len(items['items']) >= int(page_size):
        params = {
            'action': 'list_grid_content',
            'url': url,
            'ruutu_params': ruutu_params,
            'kodi_page': int(kodi_page) + 1
        }
        helper.add_item(helper.language(30013), params)

    helper.eod()

def list_seasons(series_id):
    ruutu_params = {
        'current_series_id': series_id
    }

    seasons = helper.r.get_grid_json('https://prod-component-api.nm-services.nelonenmedia.fi/api/component/26003', json.dumps(ruutu_params))

    for season in seasons['items']:

        title = season['label'].get('text')
        params = {
            'action': 'list_grid_content',
            'url': season['content']['items'][0]['content']['query']['url'],
            'ruutu_params': json.dumps(season['content']['items'][0]['content']['query']['params']),
            'kodi_page': 1
        }

        info = {
            'mediatype': 'season'
        }

        helper.add_item(title, params, info=info, content='seasons')

    helper.eod()

def search():
    search_term = helper.get_user_input(helper.language(30007))
    if search_term:
        list_search_result_grids(search_term=search_term)
    else:
        helper.log('No search query provided.')
        return False

def router(paramstring):
    """
    Router function that calls other functions
    depending on the provided paramstring
    :param paramstring: URL encoded plugin paramstring
    :type paramstring: str
    """
    # Parse a URL-encoded paramstring to the dictionary of
    # {<parameter>: <value>} elements
    params = dict(parse_qsl(paramstring))
    # Check the parameters passed to the plugin
    if 'setting' in params:
        if params['setting'] == 'reset_credentials':
            helper.reset_credentials()
    elif 'action' in params:
        if params['action'] == 'list_grids':
            list_grids(page_id=params['page_id'], userroles=params['userroles'])
        elif params['action'] == 'list_children_pages':
            list_children_pages(children=params['children'])
        elif params['action'] == 'list_grid_content':
            list_grid_content(url=params['url'], ruutu_params=params['ruutu_params'], kodi_page=params['kodi_page'])
        elif params['action'] == 'list_seasons':
            list_seasons(series_id=params['series_id'])
        elif params['action'] == 'play':
            # Play a video from a provided URL.
            helper.play_item(video_id=params['video_id'], type=params['type'], sticker=params['sticker'])
        elif params['action'] == 'search':
            search()
        elif params['action'] == 'add_favorite':
            helper.r.add_favorite(series_id=params['series_id'], gatling_token=params['gatling_token'])
        elif params['action'] == 'remove_favorite':
            helper.r.remove_favorite(series_id=params['series_id'], gatling_token=params['gatling_token'])
    else:
        if helper.check_for_credentials():
            try:
                helper.login_process()
            except helper.r.RuutuError as error:
                helper.dialog('ok', helper.language(30006), error.value)
            list_pages()
        else:
            list_pages()


if __name__ == '__main__':
    # Call the router function and pass the plugin call parameters to it.
    # We use string slicing to trim the leading '?' from the plugin call paramstring
    router(sys.argv[2][1:])
