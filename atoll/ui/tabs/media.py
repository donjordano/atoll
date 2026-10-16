"""Media tab: now playing from any MPRIS player, with prev/play/next. Off by default (see tabs/__init__.py)."""
import urllib.request

from gi.repository import Gio, GLib, GdkPixbuf, Gtk

from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import bg, button, lbl

MPRIS_PATH, PLAYER = "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player"


def pick_player(players):
    """[(bus_name, status)] -> the playing one, else the first; None if empty."""
    return next((n for n, s in players if s == "Playing"), players[0][0] if players else None)


class MediaTab(Tab):
    title, glyph = "Media", ""

    def __init__(self, island):
        super().__init__(island)
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.player, self.art_url, self.art_cache = None, None, {}
        row = Gtk.Box(spacing=14)
        self.art = Gtk.Image()
        self.art.set_size_request(72, 72)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=1)  # 1 = START
        self.song = lbl("No media playing", "title", ellipsize=3)
        self.artist = lbl(cls="dim", ellipsize=3)
        self.app = lbl(cls="dim", ellipsize=3)
        for w in (self.song, self.artist, self.app):
            info.pack_start(w, False, False, 0)
        row.pack_start(self.art, False, False, 0)
        row.pack_start(info, True, True, 0)
        self.pack_start(row, False, False, 0)
        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("ok")
        self.pack_start(self.progress, False, False, 0)
        ctrl = Gtk.Box(spacing=18, halign=3)  # 3 = CENTER
        self.play = button("", self.control, "flat icon", "PlayPause")
        for w in (button("", self.control, "flat icon", "Previous"), self.play,
                  button("", self.control, "flat icon", "Next")):
            ctrl.pack_start(w, False, False, 0)
        self.pack_start(ctrl, False, False, 0)
        GLib.timeout_add_seconds(2, self.poll)

    def call(self, name, iface, method, args=None, rtype=None):
        return self.bus.call_sync(name, MPRIS_PATH, iface, method, args, rtype,
                                  Gio.DBusCallFlags.NONE, 300, None)  # 300 ms: a hung player must not freeze the island

    def poll(self):
        if self.get_mapped():
            self.on_show()
        return True

    def on_show(self):
        try:
            names = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                       "ListNames", None, GLib.VariantType("(as)"),
                                       Gio.DBusCallFlags.NONE, 300, None).unpack()[0]
            props = {}
            for n in (n for n in names if n.startswith("org.mpris.MediaPlayer2.")):
                try:
                    props[n] = self.call(n, "org.freedesktop.DBus.Properties", "GetAll",
                                         GLib.Variant("(s)", (PLAYER,)), GLib.VariantType("(a{sv})")).unpack()[0]
                except GLib.Error:
                    pass  # player vanished between ListNames and GetAll
        except GLib.Error:
            props = {}
        self.player = pick_player([(n, p.get("PlaybackStatus")) for n, p in props.items()])
        if not self.player:
            self.song.set_text("No media playing")
            self.artist.set_text("Start Spotify, a browser video, or any MPRIS player")
            self.app.set_text("")
            self.art.clear()
            self.progress.set_fraction(0)
            return
        p = props[self.player]
        md = p.get("Metadata", {})
        self.song.set_text(md.get("xesam:title") or "Unknown title")
        self.artist.set_text(", ".join(md.get("xesam:artist") or []) or md.get("xesam:album", ""))
        self.app.set_text(self.player.split(".")[3].capitalize())
        self.play.set_label("" if p.get("PlaybackStatus") == "Playing" else "")
        length = md.get("mpris:length") or 0
        self.progress.set_fraction(min(1, (p.get("Position") or 0) / length) if length else 0)
        self.set_art(md.get("mpris:artUrl"))

    def set_art(self, url):
        if url == self.art_url:
            return
        self.art_url = url
        if not url:
            self.art.clear()
        elif url in self.art_cache:
            self.art.set_from_pixbuf(self.art_cache[url])
        else:
            def load():
                if url.startswith("file://"):
                    return GdkPixbuf.Pixbuf.new_from_file_at_scale(GLib.filename_from_uri(url)[0], 72, 72, True)
                with urllib.request.urlopen(url, timeout=5) as r:
                    loader = GdkPixbuf.PixbufLoader()
                    loader.write(r.read())
                    loader.close()
                    return loader.get_pixbuf().scale_simple(72, 72, GdkPixbuf.InterpType.BILINEAR)

            def done(pix):
                if isinstance(pix, GdkPixbuf.Pixbuf):
                    self.art_cache[url] = pix
                    if self.art_url == url:
                        self.art.set_from_pixbuf(pix)
            bg(load, done)

    def control(self, method):
        if self.player:
            try:
                self.call(self.player, PLAYER, method)
            except GLib.Error:
                pass  # e.g. Next unsupported by this player
            GLib.timeout_add(250, lambda: self.on_show() and False)
