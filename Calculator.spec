# PyInstaller build recipe for Calculator.app. Run it through ./build_app.sh.

import platform
import re
import sys
from pathlib import PurePosixPath

sys.path.insert(0, SPECPATH)
from calculator import __version__  # noqa: E402

BUNDLE_IDENTIFIER = "com.yashwant.calculator"

# Keeping just one CPU architecture removes about half of each universal Qt
# library. A rebuilt app runs on Macs with this kind of processor.
ARCHITECTURE = platform.machine()

# The app only imports QtCore, QtGui and QtWidgets. These are listed as well so
# that nothing can pull in the rest of Qt indirectly.
UNUSED_QT_MODULES = [
    f"PySide6.{name}"
    for name in """
    Qt3DAnimation Qt3DCore Qt3DExtras Qt3DInput Qt3DLogic Qt3DRender QtAxContainer
    QtBluetooth QtCanvasPainter QtCharts QtConcurrent QtDBus QtDataVisualization
    QtDesigner QtGraphs QtGraphsWidgets QtHelp QtHttpServer QtLocation QtMultimedia
    QtMultimediaWidgets QtNetwork QtNetworkAuth QtNfc QtOpenGL QtOpenGLWidgets QtPdf
    QtPdfWidgets QtPositioning QtPrintSupport QtQml QtQuick QtQuick3D QtQuickControls2
    QtQuickTest QtQuickWidgets QtRemoteObjects QtScxml QtSensors QtSerialBus
    QtSerialPort QtSpatialAudio QtSql QtStateMachine QtSvg QtSvgWidgets QtTest
    QtTextToSpeech QtUiTools QtWebChannel QtWebEngineCore QtWebEngineQuick
    QtWebEngineWidgets QtWebSockets QtWebView QtXml
    """.split()
]

UNUSED_PYTHON_MODULES = [
    "asyncio",
    "doctest",
    # Compression the app never uses. Its Homebrew library also needs a newer
    # macOS than everything else in the bundle.
    "_lzma",
    "lzma",
    "multiprocessing",
    "pdb",
    "pip",
    "pydoc",
    "pytest",
    "setuptools",
    "sqlite3",
    "ssl",
    "test",
    "tkinter",
    "unittest",
]

# The only Qt plugins the app needs: the macOS window system and native style.
# Icons and images are drawn in code, so image format plugins aren't needed.
KEPT_QT_PLUGINS = {"platforms/libqcocoa.dylib", "styles/libqmacstyle.dylib"}

# The Qt libraries those need. Others get collected only because the plugins
# removed above depend on them, so they must be filtered out explicitly as well.
KEPT_QT_FRAMEWORKS = {"QtCore", "QtDBus", "QtGui", "QtWidgets"}


def is_wanted(entry):
    """Filter out the parts of Qt which the app never loads."""
    path = PurePosixPath(entry[0]).as_posix()
    if "/Qt/translations/" in path or "/Qt/qml/" in path:
        return False
    marker = "/Qt/plugins/"
    if marker in path:
        return path.split(marker, 1)[1] in KEPT_QT_PLUGINS
    # Matches a framework's files and its shortcut at the top of the bundle.
    framework = re.search(r"/Qt/lib/(\w+)\.framework(/|$)|^(Qt\w+)$", path)
    if framework:
        return (framework.group(1) or framework.group(3)) in KEPT_QT_FRAMEWORKS
    return True


analysis = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    excludes=UNUSED_QT_MODULES + UNUSED_PYTHON_MODULES,
    noarchive=False,
)
analysis.binaries = [entry for entry in analysis.binaries if is_wanted(entry)]
analysis.datas = [entry for entry in analysis.datas if is_wanted(entry)]

archive = PYZ(analysis.pure)

executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Calculator",
    console=False,  # A windowed app: no Terminal window opens.
    target_arch=ARCHITECTURE,
    upx=False,
)

collected = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="Calculator",
    upx=False,
)

app = BUNDLE(
    collected,
    name="Calculator.app",
    icon="packaging/Calculator.icns",
    bundle_identifier=BUNDLE_IDENTIFIER,
    version=__version__,
    info_plist={
        "CFBundleName": "Calculator",
        "CFBundleDisplayName": "Calculator",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSApplicationCategoryType": "public.app-category.utilities",
        # The Homebrew Python and libraries it was built with need macOS 26.
        "LSMinimumSystemVersion": "26.0",
        "NSHighResolutionCapable": True,
        # False means the app supports both light and dark mode.
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "© 2026 Yashwant",
    },
)
