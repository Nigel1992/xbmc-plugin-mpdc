#!/usr/bin/env python3
# Kodi MPD control plugin (minimal)
import sys
import os
import json
import urllib.parse
import time
import hashlib
import imghdr
import glob

try:
    import xbmc
    import xbmcgui
    import xbmcplugin
    import xbmcaddon
except Exception:
    xbmc = xbmcgui = xbmcplugin = xbmcaddon = None

from resources.lib.mpdclient import MPDClient

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

def translate_path(p):
    # Try xbmc.translatePath (older Kodi) first, then xbmcvfs.translatePath,
    # then fall back to xbmcaddon.Addon().getAddonInfo('profile') if available.
    try:
        if xbmc and hasattr(xbmc, 'translatePath'):
            return xbmc.translatePath(p)
    except Exception:
        pass
    try:
        import xbmcvfs
        if hasattr(xbmcvfs, 'translatePath'):
            return xbmcvfs.translatePath(p)
    except Exception:
        pass
    try:
        if xbmcaddon:
            addon = xbmcaddon.Addon()
            profile = addon.getAddonInfo('profile')
            if profile:
                if p.startswith('special://profile'):
                    rest = p[len('special://profile'):].lstrip('/\\')
                    return os.path.join(profile, rest)
                if p.startswith('special://home'):
                    home = addon.getAddonInfo('path')
                    rest = p[len('special://home'):].lstrip('/\\')
                    return os.path.join(home, rest)
    except Exception:
        pass
    # Last resort: try a reasonable user-home fallback for special://profile
    if p.startswith('special://profile'):
        rest = p[len('special://profile'):].lstrip('/\\')
        kodi_home = os.path.expanduser('~/.kodi')
        return os.path.join(kodi_home, rest)
    return os.path.expanduser(p)

DATA_DIR = translate_path('special://profile/addon_data/plugin.audio.mpdc')
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except Exception:
        pass

PROFILES_FILE = os.path.join(DATA_DIR, 'servers.json')
DEBUG_LOG = os.path.join(DATA_DIR, 'mpdc.log')

def write_log(msg):
    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (ts, msg))
    except Exception:
        pass
    try:
        if xbmc and hasattr(xbmc, 'log'):
            xbmc.log('MPDC: %s' % msg)
    except Exception:
        pass


ART_CACHE_DIR = os.path.join(DATA_DIR, 'artcache')
if not os.path.exists(ART_CACHE_DIR):
    try:
        os.makedirs(ART_CACHE_DIR)
    except Exception:
        pass

def _cached_art_path_for_key(key):
    # return existing cached file if present
    pattern = os.path.join(ART_CACHE_DIR, key + '.*')
    matches = glob.glob(pattern)
    return matches[0] if matches else None

def ensure_art(file_uri, client):
    """Fetch album art via MPD `albumart` and cache it locally. Returns local path or None."""
    try:
        key = hashlib.md5(file_uri.encode('utf-8')).hexdigest()
    except Exception:
        key = hashlib.md5(file_uri.encode('utf-8', 'ignore')).hexdigest()
    existing = _cached_art_path_for_key(key)
    if existing:
        return existing
    try:
        data = client.albumart(file_uri)
    except Exception as e:
        write_log('ensure_art: albumart failed for %s: %s' % (file_uri, e))
        return None
    if not data:
        return None
    fmt = imghdr.what(None, h=data)
    if fmt == 'jpeg':
        ext = '.jpg'
    elif fmt == 'png':
        ext = '.png'
    elif fmt == 'gif':
        ext = '.gif'
    else:
        ext = '.bin'
    path = os.path.join(ART_CACHE_DIR, key + ext)
    try:
        with open(path, 'wb') as f:
            f.write(data)
        return path
    except Exception as e:
        write_log('ensure_art: write failed %s' % e)
        return None

def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        profiles = [{'name': 'Local MPD', 'host': '127.0.0.1', 'port': 6600}]
        save_profiles(profiles)
        return profiles
    try:
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return [{'name': 'Local MPD', 'host': '127.0.0.1', 'port': 6600}]

def save_profiles(profiles):
    with open(PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)

def build_url(params):
    return BASE_URL + '?' + urllib.parse.urlencode(params)

def parse_args():
    qs = ''
    if len(sys.argv) > 2:
        qs = sys.argv[2]
    if qs.startswith('?'):
        qs = qs[1:]
    return {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}

def show_servers():
    profiles = load_profiles()
    for idx, p in enumerate(profiles):
        url = build_url({'mode': 'server', 'idx': idx})
        label = '%s (%s:%s)' % (p.get('name'), p.get('host'), p.get('port'))
        li = xbmcgui.ListItem(label)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)

    add_url = build_url({'mode': 'add_server'})
    li = xbmcgui.ListItem('Add MPD server...')
    xbmcplugin.addDirectoryItem(HANDLE, add_url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def add_server():
    d = xbmcgui.Dialog()
    name = d.input('Server name', type=xbmcgui.INPUT_ALPHANUM)
    if not name:
        return
    host = d.input('Host (ip or hostname)', defaultt='127.0.0.1')
    port = d.input('Port', defaultt='6600')
    try:
        port = int(port)
    except Exception:
        port = 6600
    profiles = load_profiles()
    profiles.append({'name': name, 'host': host, 'port': port})
    save_profiles(profiles)
    xbmcgui.Dialog().notification('MPD', 'Server added', time=1500)
    xbmc.executebuiltin('Container.Refresh')

def connect_profile(idx):
    profiles = load_profiles()
    try:
        p = profiles[int(idx)]
    except Exception:
        raise
    client = MPDClient(p.get('host', '127.0.0.1'), int(p.get('port', 6600)))
    try:
        client.connect()
    except Exception as e:
        write_log('connect_profile: failed to connect to %s:%s -> %s' % (p.get('host'), p.get('port'), e))
        raise
    return client, p

def show_server_menu(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    title = '%s @ %s:%s' % (p.get('name'), p.get('host'), p.get('port'))

    # Playlists
    url = build_url({'mode': 'playlists', 'idx': idx})
    li = xbmcgui.ListItem('Playlists')
    xbmcplugin.addDirectoryItem(HANDLE, url, li, True)

    # Artists
    url = build_url({'mode': 'artists', 'idx': idx})
    xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem('Artists'), True)

    # Files (browse root)
    url = build_url({'mode': 'files', 'idx': idx, 'path': ''})
    xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem('Browse files'), True)

    # Queue
    url = build_url({'mode': 'queue', 'idx': idx})
    xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem('Current queue'), True)

    # Now Playing
    url = build_url({'mode': 'now_playing', 'idx': idx})
    xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem('Now playing'), True)

    # Controls
    url = build_url({'mode': 'controls', 'idx': idx})
    xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem('Player controls'), True)

    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.endOfDirectory(HANDLE)

def show_files(params):
    idx = params.get('idx')
    path = params.get('path', '')
    client, p = connect_profile(idx)
    items = client.lsinfo(path)
    for it in items:
        if 'directory' in it:
            url = build_url({'mode': 'files', 'idx': idx, 'path': it['directory']})
            li = xbmcgui.ListItem(it['directory'])
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
        elif 'file' in it:
            file_path = it.get('file')
            url = build_url({'mode': 'play', 'idx': idx, 'file': file_path})
            label = it.get('Title') or os.path.basename(file_path)
            li = xbmcgui.ListItem(label)
            li.setInfo('music', {'title': label, 'artist': it.get('Artist'), 'album': it.get('Album')})
            try:
                li.setProperty('IsPlayable', 'true')
            except Exception:
                pass
            # try to attach album art asynchronously (cached)
            try:
                art = ensure_art(file_path, client)
                if art:
                    li.setArt({'thumb': art, 'icon': art, 'fanart': art})
            except Exception as e:
                write_log('show_files: ensure_art failed: %s' % e)
            # add context menu items: add to queue, add to playlist
            try:
                cmds = []
                cmds.append(('Add to queue', 'RunPlugin(%s)' % build_url({'mode': 'add_to_queue', 'idx': idx, 'file': file_path})))
                cmds.append(('Add to playlist...', 'RunPlugin(%s)' % build_url({'mode': 'pick_playlist_for_add', 'idx': idx, 'file': file_path})))
                li.addContextMenuItems(cmds)
            except Exception:
                pass
            xbmcplugin.addDirectoryItem(HANDLE, url, li, False)

    xbmcplugin.endOfDirectory(HANDLE)

def play_file(params):
    idx = params.get('idx')
    file_path = params.get('file')
    client, p = connect_profile(idx)
    try:
        write_log('play_file: idx=%s file=%s' % (idx, file_path))
        # Prefer addid/playid to ensure the exact added track is played.
        played = False
        try:
            song_id = client.addid(file_path)
            write_log('addid result: %r' % (song_id,))
            if song_id is not None:
                client.playid(song_id)
                write_log('playid issued for id %r' % song_id)
                played = True
        except Exception as e_addid:
            write_log('addid/playid not supported or failed: %s' % e_addid)

        if not played:
            # Fallback to clear/add/play flow
            try:
                client.clear()
                write_log('playlist cleared (fallback)')
            except Exception as e_clear:
                write_log('clear failed: %s' % e_clear)
            try:
                res = client.add(file_path)
                write_log('add result (fallback): %r' % (res,))
            except Exception as e_add:
                write_log('add failed: %s' % e_add)
            try:
                client.play(0)
                write_log('play(0) issued (fallback)')
            except Exception as e_play0:
                write_log('play(0) failed: %s; trying play() (fallback)' % e_play0)
                try:
                    client.play()
                    write_log('play() issued (fallback)')
                except Exception as e_play:
                    write_log('play failed (fallback): %s' % e_play)

        st = client.status()
        write_log('status after play: %r' % (st,))
        try:
            xbmcgui.Dialog().notification('MPD', 'Playing on server (%s)' % st.get('state', '?'), time=1500)
        except Exception:
            pass
    except Exception as e:
        write_log('play_file failed: %s' % e)
        try:
            xbmcgui.Dialog().notification('MPD', 'Play failed: %s' % (str(e),), time=2500)
        except Exception:
            pass

def show_controls(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    # Simple controls
    actions = [
        ('Play/Pause', 'toggle'),
        ('Stop', 'stop'),
        ('Next', 'next'),
        ('Previous', 'previous')
    ]
    for label, act in actions:
        url = build_url({'mode': 'control_action', 'idx': idx, 'action': act})
        xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem(label), False)
    xbmcplugin.endOfDirectory(HANDLE)

def control_action(params):
    idx = params.get('idx')
    act = params.get('action')
    client, p = connect_profile(idx)
    try:
        if act == 'toggle':
            # prefer MPD 'toggle' command if supported, else fallback to status-based toggle
            try:
                client.command('toggle')
                write_log('control_action: used MPD toggle command')
            except Exception as e_toggle:
                write_log('control_action: toggle command failed: %s; falling back' % e_toggle)
                st = client.status()
                if st.get('state') == 'play':
                    client.pause()
                else:
                    client.play()
        elif act == 'stop':
            client.stop()
        elif act == 'next':
            client.next()
        elif act == 'previous':
            client.previous()
        xbmcgui.Dialog().notification('MPD', 'Command sent', time=800)
    except Exception as e:
        xbmcgui.Dialog().notification('MPD', 'Command failed', time=1500)

def show_queue(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    # top-level actions
    try:
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'queue_clear', 'idx': idx}), xbmcgui.ListItem('Clear playlist'), False)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'playlist_save', 'idx': idx}), xbmcgui.ListItem('Save current playlist...'), False)
    except Exception:
        pass

    entries = client.playlistinfo()
    for e in entries:
        title = e.get('Title') or e.get('file')
        fpath = e.get('file')
        # pos and id may be returned as 'Pos'/'pos' and 'Id'/'id'
        pos = None
        try:
            pos = int(e.get('Pos') or e.get('pos'))
        except Exception:
            try:
                pos = int(e.get('position'))
            except Exception:
                pos = None
        id_ = None
        try:
            id_ = int(e.get('Id') or e.get('id'))
        except Exception:
            id_ = None

        # Play URL prefers id when available
        if id_ is not None:
            url = build_url({'mode': 'queue_play', 'idx': idx, 'id': id_})
        elif pos is not None:
            url = build_url({'mode': 'queue_play', 'idx': idx, 'pos': pos})
        else:
            url = '#'

        li = xbmcgui.ListItem(title)
        try:
            art = ensure_art(fpath, client)
            if art:
                li.setArt({'thumb': art, 'icon': art, 'fanart': art})
        except Exception as exc:
            write_log('show_queue: ensure_art failed: %s' % exc)

        # context menu: play, remove, move up/down
        try:
            cmds = []
            cmds.append(('Play', 'RunPlugin(%s)' % url))
            cmds.append(('Add to playlist...', 'RunPlugin(%s)' % build_url({'mode': 'pick_playlist_for_add', 'idx': idx, 'file': fpath})))
            # remove by id if available else by pos
            cmds.append(('Remove from playlist', 'RunPlugin(%s)' % build_url({'mode': 'queue_remove', 'idx': idx, 'pos': pos if pos is not None else -1, 'id': id_ if id_ is not None else -1})))
            if pos is not None:
                cmds.append(('Move up', 'RunPlugin(%s)' % build_url({'mode': 'queue_move', 'idx': idx, 'frompos': pos, 'topos': max(0, pos - 1)})))
                cmds.append(('Move down', 'RunPlugin(%s)' % build_url({'mode': 'queue_move', 'idx': idx, 'frompos': pos, 'topos': pos + 1})))
            li.addContextMenuItems(cmds)
        except Exception:
            pass

        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)

    xbmcplugin.endOfDirectory(HANDLE)

def show_playlists(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    pls = client.listplaylists()
    for pl in pls:
        name = pl.get('playlist')
        url = build_url({'mode': 'playlist_items', 'idx': idx, 'playlist': name})
        xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem(name), True)
    xbmcplugin.endOfDirectory(HANDLE)

def show_playlist_items(params):
    idx = params.get('idx')
    name = params.get('playlist')
    client, p = connect_profile(idx)
    items = client.listplaylist(name)
    for it in items:
        title = it.get('Title') or it.get('file')
        file_path = it.get('file')
        url = build_url({'mode': 'play', 'idx': idx, 'file': file_path})
        li = xbmcgui.ListItem(title)
        try:
            art = ensure_art(file_path, client)
            if art:
                li.setArt({'thumb': art, 'icon': art, 'fanart': art})
        except Exception as exc:
            write_log('show_playlist_items: ensure_art failed: %s' % exc)
        try:
            cmds = []
            cmds.append(('Add to queue', 'RunPlugin(%s)' % build_url({'mode': 'add_to_queue', 'idx': idx, 'file': file_path})))
            cmds.append(('Add to playlist...', 'RunPlugin(%s)' % build_url({'mode': 'pick_playlist_for_add', 'idx': idx, 'file': file_path})))
            li.addContextMenuItems(cmds)
        except Exception:
            pass
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)


def show_artists(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    try:
        artists = client.list_field('artist')
    except Exception as e:
        write_log('show_artists: failed: %s' % e)
        artists = []
    for a in artists:
        url = build_url({'mode': 'artist_albums', 'idx': idx, 'artist': a})
        xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem(a), True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_artist_albums(params):
    idx = params.get('idx')
    artist = params.get('artist')
    client, p = connect_profile(idx)
    try:
        albums = client.list_field('album', 'artist', artist)
    except Exception as e:
        write_log('show_artist_albums: failed: %s' % e)
        albums = []
    for al in albums:
        url = build_url({'mode': 'album_tracks', 'idx': idx, 'artist': artist, 'album': al})
        xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem(al), True)
    xbmcplugin.endOfDirectory(HANDLE)


def show_album_tracks(params):
    idx = params.get('idx')
    artist = params.get('artist')
    album = params.get('album')
    client, p = connect_profile(idx)
    try:
        tracks = client.command('search', 'artist', artist, 'album', album)
    except Exception as e:
        write_log('show_album_tracks: search failed: %s' % e)
        tracks = []
    for t in tracks:
        file_path = t.get('file')
        title = t.get('Title') or os.path.basename(file_path)
        url = build_url({'mode': 'play', 'idx': idx, 'file': file_path})
        li = xbmcgui.ListItem(title)
        li.setInfo('music', {'title': title, 'artist': t.get('Artist'), 'album': t.get('Album')})
        try:
            art = ensure_art(file_path, client)
            if art:
                li.setArt({'thumb': art, 'icon': art, 'fanart': art})
        except Exception as e:
            write_log('show_album_tracks: ensure_art failed: %s' % e)
        try:
            li.setProperty('IsPlayable', 'true')
        except Exception:
            pass
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)


def show_now_playing(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    try:
        st = client.status()
        cs = client.currentsong()
        title = cs.get('Title') or cs.get('file') or 'Unknown'
        artist = cs.get('Artist') or ''
        album = cs.get('Album') or ''
        label = '%s - %s' % (artist, title) if artist else title
        li = xbmcgui.ListItem(label)
        li.setInfo('music', {'title': title, 'artist': artist, 'album': album})
        try:
            art = None
            if cs.get('file'):
                art = ensure_art(cs.get('file'), client)
            if art:
                li.setArt({'thumb': art, 'icon': art, 'fanart': art})
        except Exception as e:
            write_log('show_now_playing: ensure_art failed: %s' % e)

        # context menu actions
        try:
            cmds = []
            cmds.append(('Toggle Play/Pause', 'RunPlugin(%s)' % build_url({'mode': 'control_action', 'idx': idx, 'action': 'toggle'})))
            cmds.append(('Next', 'RunPlugin(%s)' % build_url({'mode': 'control_action', 'idx': idx, 'action': 'next'})))
            cmds.append(('Previous', 'RunPlugin(%s)' % build_url({'mode': 'control_action', 'idx': idx, 'action': 'previous'})))
            li.addContextMenuItems(cmds)
        except Exception:
            pass

        xbmcplugin.setPluginCategory(HANDLE, 'Now Playing')
        xbmcplugin.addDirectoryItem(HANDLE, '#', li, False)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        write_log('show_now_playing failed: %s' % e)
        try:
            xbmcgui.Dialog().notification('MPD', 'Failed to retrieve now playing', time=1500)
        except Exception:
            pass


def add_to_queue_action(params):
    idx = params.get('idx')
    file_path = params.get('file')
    client, p = connect_profile(idx)
    try:
        client.add(file_path)
        xbmcgui.Dialog().notification('MPD', 'Added to queue', time=1000)
    except Exception as e:
        write_log('add_to_queue_action failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Add failed: %s' % e, time=1500)


def pick_playlist_for_add(params):
    idx = params.get('idx')
    file_path = params.get('file')
    client, p = connect_profile(idx)
    pls = client.listplaylists()
    for pl in pls:
        name = pl.get('playlist')
        url = build_url({'mode': 'playlist_add_action', 'idx': idx, 'playlist': name, 'file': file_path})
        xbmcplugin.addDirectoryItem(HANDLE, url, xbmcgui.ListItem(name), False)
    xbmcplugin.endOfDirectory(HANDLE)


def playlist_add_action(params):
    idx = params.get('idx')
    playlist = params.get('playlist')
    file_path = params.get('file')
    client, p = connect_profile(idx)
    try:
        client.playlistadd(playlist, file_path)
        xbmcgui.Dialog().notification('MPD', 'Added to playlist %s' % playlist, time=1200)
    except Exception as e:
        write_log('playlist_add_action failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Add to playlist failed', time=1500)


def queue_play(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    id_ = params.get('id')
    pos = params.get('pos')
    try:
        if id_ and str(id_) != '-1':
            client.playid(int(id_))
        elif pos and str(pos) != '-1':
            client.play(int(pos))
        else:
            xbmcgui.Dialog().notification('MPD', 'No position or id to play', time=1200)
            return
        xbmcgui.Dialog().notification('MPD', 'Playing', time=800)
    except Exception as e:
        write_log('queue_play failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Play failed: %s' % e, time=1500)


def queue_remove(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    id_ = params.get('id')
    pos = params.get('pos')
    try:
        if id_ and str(id_) != '-1':
            client.deleteid(int(id_))
        elif pos and str(pos) != '-1':
            client.delete(int(pos))
        else:
            xbmcgui.Dialog().notification('MPD', 'No position or id to remove', time=1200)
            return
        xbmcgui.Dialog().notification('MPD', 'Removed', time=800)
    except Exception as e:
        write_log('queue_remove failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Remove failed: %s' % e, time=1500)


def queue_move(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    try:
        src = int(params.get('frompos'))
        dst = int(params.get('topos'))
    except Exception:
        xbmcgui.Dialog().notification('MPD', 'Invalid move positions', time=1200)
        return
    try:
        client.move(src, dst)
        xbmcgui.Dialog().notification('MPD', 'Moved', time=800)
    except Exception as e:
        write_log('queue_move failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Move failed: %s' % e, time=1500)


def queue_clear(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    try:
        client.clear()
        xbmcgui.Dialog().notification('MPD', 'Playlist cleared', time=800)
    except Exception as e:
        write_log('queue_clear failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Clear failed: %s' % e, time=1500)


def playlist_save(params):
    idx = params.get('idx')
    client, p = connect_profile(idx)
    d = xbmcgui.Dialog()
    name = d.input('Save playlist as')
    if not name:
        return
    try:
        client.save(name)
        xbmcgui.Dialog().notification('MPD', 'Playlist saved as %s' % name, time=1200)
    except Exception as e:
        write_log('playlist_save failed: %s' % e)
        xbmcgui.Dialog().notification('MPD', 'Save failed: %s' % e, time=1500)

def router():
    params = parse_args()
    mode = params.get('mode')
    if not mode:
        show_servers()
    elif mode == 'add_server':
        add_server()
    elif mode == 'server':
        show_server_menu(params)
    elif mode == 'files':
        show_files(params)
    elif mode == 'play':
        play_file(params)
    elif mode == 'controls':
        show_controls(params)
    elif mode == 'control_action':
        control_action(params)
    elif mode == 'queue':
        show_queue(params)
    elif mode == 'playlists':
        show_playlists(params)
    elif mode == 'playlist_items':
        show_playlist_items(params)
    elif mode == 'artists':
        show_artists(params)
    elif mode == 'artist_albums':
        show_artist_albums(params)
    elif mode == 'album_tracks':
        show_album_tracks(params)
    elif mode == 'now_playing':
        show_now_playing(params)
    elif mode == 'add_to_queue':
        add_to_queue_action(params)
    elif mode == 'pick_playlist_for_add':
        pick_playlist_for_add(params)
    elif mode == 'playlist_add_action':
        playlist_add_action(params)
    elif mode == 'queue_play':
        queue_play(params)
    elif mode == 'queue_remove':
        queue_remove(params)
    elif mode == 'queue_move':
        queue_move(params)
    elif mode == 'queue_clear':
        queue_clear(params)
    elif mode == 'playlist_save':
        playlist_save(params)
    else:
        xbmcgui.Dialog().notification('MPD', 'Unknown action: %s' % mode, time=1200)

if __name__ == '__main__':
    router()
