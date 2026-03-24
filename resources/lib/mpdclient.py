"""
Minimal MPD client used by plugin.audio.mpdc.

This is a small, self-contained MPD client implementing the subset
of the MPD protocol needed for browsing and simple playback control.
It intentionally keeps parsing simple; it works with typical MPD servers.
"""
import socket

class MPDError(Exception):
    pass

class MPDClient:
    def __init__(self, host='127.0.0.1', port=6600, timeout=5.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        # read greeting
        line = self._readline()
        if not line.startswith('OK') and 'MPD' not in line:
            raise MPDError('Invalid greeting: %r' % line)

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None

    def _readline(self):
        buf = b''
        while True:
            ch = self.sock.recv(1)
            if not ch:
                raise MPDError('Connection closed')
            if ch == b'\n':
                break
            buf += ch
        return buf.decode('utf-8', errors='ignore').rstrip('\r')

    def _read_until_ok(self):
        lines = []
        while True:
            line = self._readline()
            if line.startswith('OK'):
                return lines
            if line.startswith('ACK'):
                raise MPDError(line)
            lines.append(line)

    def _quote(self, s):
        if isinstance(s, int):
            return str(s)
        s = s.replace('"', '\"')
        if ' ' in s or '"' in s:
            return '"%s"' % s
        return s

    def command(self, cmd, *args):
        if not self.sock:
            raise MPDError('Not connected')
        if args:
            cmd_line = cmd + ' ' + ' '.join(self._quote(str(a)) for a in args)
        else:
            cmd_line = cmd
        self.sock.sendall((cmd_line + '\n').encode('utf-8'))
        lines = self._read_until_ok()
        return self._parse_lines(lines)

    def _parse_lines(self, lines):
        # Parse key: value lines into list of dicts. Group on 'file' or 'directory' or 'playlist'.
        items = []
        cur = {}
        for line in lines:
            if not line:
                continue
            if ': ' in line:
                k, v = line.split(': ', 1)
            else:
                continue
            # grouping keys
            if k in ('file', 'directory', 'playlist') and cur:
                items.append(cur)
                cur = {}
            # multiple same keys -> append numbered keys
            if k in cur:
                # convert to list
                if isinstance(cur[k], list):
                    cur[k].append(v)
                else:
                    cur[k] = [cur[k], v]
            else:
                cur[k] = v
        if cur:
            items.append(cur)
        return items

    def _read_n_bytes(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise MPDError('Connection closed while reading binary data')
            data += chunk
        return data

    def albumart(self, uri):
        """Retrieve binary album art for a given file URI using MPD's albumart command.

        Returns raw bytes on success or raises MPDError on failure.
        """
        if not self.sock:
            raise MPDError('Not connected')
        cmd_line = 'albumart ' + self._quote(uri)
        self.sock.sendall((cmd_line + '\n').encode('utf-8'))
        # first response should be 'size: N' or an ACK error
        line = self._readline()
        if line.startswith('ACK'):
            raise MPDError(line)
        if not line.startswith('size:'):
            raise MPDError('Unexpected albumart response: %r' % line)
        try:
            size = int(line.split(':', 1)[1].strip())
        except Exception:
            raise MPDError('Invalid size in albumart response: %r' % line)
        data = self._read_n_bytes(size)
        # read until OK (or ACK)
        while True:
            l = self._readline()
            if l.startswith('OK'):
                break
            if l.startswith('ACK'):
                raise MPDError(l)
        return data

    def list_field(self, field, *args):
        """Helper to run `list <field> [filter ...]` and return a flat list of values."""
        if args:
            res = self.command('list', field, *args)
        else:
            res = self.command('list', field)
        out = []
        if not res:
            return out
        for item in res:
            for k, v in item.items():
                if k.lower() == field.lower():
                    if isinstance(v, list):
                        out.extend(v)
                    else:
                        out.append(v)
        # fallback: if a single dict contains lists or single values, extract them
        if not out and len(res) == 1:
            item = res[0]
            for v in item.values():
                if isinstance(v, list):
                    out.extend(v)
                else:
                    out.append(v)
        return out

    # Convenience methods
    def status(self):
        res = self.command('status')
        return res[0] if res else {}

    def currentsong(self):
        res = self.command('currentsong')
        return res[0] if res else {}

    def play(self, id_or_pos=None):
        if id_or_pos is None:
            return self.command('play')
        return self.command('play', id_or_pos)

    def pause(self):
        return self.command('pause', 1)

    def stop(self):
        return self.command('stop')

    def next(self):
        return self.command('next')

    def previous(self):
        return self.command('previous')

    def add(self, uri):
        return self.command('add', uri)

    def addid(self, uri):
        """Add `uri` to the playlist and return the assigned song id (if supported).

        Returns the numeric Id or None if the server doesn't report an id.
        """
        res = self.command('addid', uri)
        if not res:
            return None
        for item in res:
            # MPD typically returns a line like 'Id: <n>' which becomes {'Id': '<n>'}
            if 'Id' in item:
                try:
                    return int(item['Id'])
                except Exception:
                    try:
                        return int(item['id'])
                    except Exception:
                        return None
        return None

    def delete(self, pos):
        return self.command('delete', pos)

    def deleteid(self, id_):
        return self.command('deleteid', id_)

    def move(self, from_pos, to_pos):
        return self.command('move', from_pos, to_pos)

    def playlistadd(self, playlist, uri):
        return self.command('playlistadd', playlist, uri)

    def playlistclear(self, name):
        return self.command('playlistclear', name)

    def save(self, name):
        return self.command('save', name)

    def clear(self):
        return self.command('clear')

    def lsinfo(self, path=''):
        if path:
            return self.command('lsinfo', path)
        return self.command('lsinfo')

    def listplaylists(self):
        return self.command('listplaylists')

    def listplaylist(self, name):
        return self.command('listplaylist', name)

    def playlistinfo(self):
        return self.command('playlistinfo')

    def listallinfo(self):
        return self.command('listallinfo')

    def find(self, what, term):
        return self.command('find', what, term)

    def playid(self, id_):
        """Play a song by MPD song id."""
        return self.command('playid', id_)
