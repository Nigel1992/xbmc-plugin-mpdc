# MPD Control (MPDC) — Kodi Addon

MPDC is a Kodi audio addon that lets you control remote MPD (Music Player Daemon)
servers from inside Kodi. It provides browsing (files, artists, albums), player
controls, playlist management, server profiles, and album art caching — playback
runs on the MPD server itself.

Key features
------------
- Browse music files on MPD server and play individual tracks
- Browse by artist → album → tracks
- View and manage the MPD playlist (add/remove/move/clear/save)
- Player controls (play/pause toggle, next, previous, stop)
- Album art retrieval (MPD albumart) with local caching
- Multiple server profiles

Installation
------------
1. Copy the `plugin.audio.mpdc` folder into Kodi's `addons` directory, or
   zip the folder and install via Kodi's Add-on manager.
2. Launch the addon from Add-ons → Music → Add-ons.
3. Add an MPD server profile (host+port) and select the server.

Usage
-----
- Browse `Files`, `Artists`, `Playlists`, or open `Current queue` to manage
  the server playlist. Use the context menu on items to add tracks to the
  queue or to another saved playlist.

Development
-----------
- The addon includes a self-contained MPD client at `resources/lib/mpdclient.py`.
- To iterate quickly during development, copy the addon directory into your
  Kodi profile's `addons/` folder and restart Kodi.

License
-------
This project is distributed under the MIT License — see `LICENSE`.

Contributing
------------
Pull requests and issues are welcome. Open a GitHub issue to discuss larger
changes before implementing.
