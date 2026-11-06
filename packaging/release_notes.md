A polished desktop calculator for macOS, with exact decimal arithmetic, a history
panel, light and dark themes, and full keyboard support.

## Download

Download **Calculator.dmg** from the Assets list below (about 18 MB).

**Requires:** a Mac with Apple Silicon (M1 or later) and macOS 26 or newer. It
won't run on Intel Macs.

## Install

1. Open `Calculator.dmg` and drag **Calculator** onto **Applications**.
2. Double-click Calculator in Applications.

## macOS will show a security warning the first time

This is expected. This free app isn't signed with a paid Apple Developer account,
so macOS can't verify who made it. To open it:

1. Click **Done** in the warning.
2. Open **System Settings > Privacy & Security** and scroll down to **Security**.
3. Click **Open Anyway** beside the Calculator message, then confirm with your
   password or Touch ID.

You only need to do this once. If you'd rather not, the
[source code](https://github.com/yashwanted/Calculator-App) is available to read
and run yourself.

macOS has its own Calculator, so if Finder won't let you drag this one into
Applications, keep the disk image open and run this in Terminal instead:

```bash
ditto /Volumes/Calculator/Calculator.app /Applications/Calculator.app
```
