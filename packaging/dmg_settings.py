# dmgbuild settings for Calculator.dmg. Run through ./build_app.sh, which passes
# the app and background paths with -D app=... -D background=...
# Positions and sizes must match packaging/make_dmg_background.py.

import os.path

application = defines["app"]  # noqa: F821 (provided by dmgbuild)
app_name = os.path.basename(application)

format = "ULMO"
filesystem = "APFS"
files = [application]
symlinks = {"Applications": "/Applications"}
icon = defines["icon"]  # noqa: F821
background = defines["background"]  # noqa: F821

window_rect = ((200, 160), (640, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = False

icon_size = 128
text_size = 13
arrange_by = None
icon_locations = {
    app_name: (170, 180),
    "Applications": (470, 180),
}
