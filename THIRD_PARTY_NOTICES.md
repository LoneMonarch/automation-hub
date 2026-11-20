# Third-party components

Automation Hub uses the following separately licensed components. Distributions must retain their upstream copyright and licence files, including the files installed alongside the Python packages and Chromium resources. This notice is an index, not a replacement for the full licence texts.

| Component | Upstream | Licence family |
|---|---|---|
| Python | https://www.python.org | PSF |
| PySide6 / Qt / Shiboken | https://www.qt.io/qt-for-python | LGPLv3 / GPLv3 / commercial (use LGPL-compatible dynamic distribution) |
| Playwright | https://github.com/microsoft/playwright-python | Apache-2.0 |
| Chromium | https://www.chromium.org | BSD-style and third-party notices |
| keyring | https://github.com/jaraco/keyring | MIT |
| packaging | https://github.com/pypa/packaging | Apache-2.0 / BSD |
| Rich | https://github.com/Textualize/rich | MIT |
| PyInstaller | https://pyinstaller.org | GPL with distribution exception |

The packaging build collects installed dependency licence metadata into the distribution. Qt shared libraries remain separate and replaceable; do not convert them to a statically linked executable. Module authors must include notices for any additional vendored dependencies. Consult the upstream licence texts for the exact terms applying to a chosen release.
