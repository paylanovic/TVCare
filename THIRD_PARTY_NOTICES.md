# Third-party components

TVCare application source is provided under the MIT License in LICENSE.

Packaged desktop releases embed a Python runtime and its standard library. Python and bundled third-party modules retain their upstream copyright and license notices. Relevant runtime components may include Python Software Foundation License terms, OpenSSL (Apache License 2.0 for OpenSSL 3), libffi, zlib, bzip2 and xz/liblzma; the exact set is host/build dependent. Consult the notices distributed with the runtime and its upstream projects.

- Python licensing: https://docs.python.org/3/license.html
- PyInstaller: https://pyinstaller.org/en/stable/license.html — GPL with the bootloader distribution exception; packaging does not change TVCare's source license.
- OpenSSL: https://openssl-library.org/source/license/
- libffi: https://github.com/libffi/libffi/blob/master/LICENSE
- zlib: https://zlib.net/zlib_license.html
- bzip2: https://sourceware.org/bzip2/
- xz/liblzma: https://tukaani.org/xz/

Android Platform Tools / ADB is not bundled in the default release. Users download it separately from Google's official site and review its terms. A maintainer explicitly bundling ADB must preserve its notices and verify redistribution rights.

The Android companion's application code is part of TVCare. Android SDK tools are build tools and are not included in the source repository or default desktop archives. No private APK signing key is distributed.

Upstream contributor names or licensing contact addresses in third-party notices identify those projects, not TVCare users. These notices must not be removed by a personal-data scrub.
