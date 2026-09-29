# Runtime license notices

These files preserve upstream license and copyright texts for the desktop runtime components described below. `SOURCES.json` records the official source URL, retrieval date, and SHA-256 of each text. Texts are unmodified except that the HACL file contains the complete leading license comment extracted from its upstream source file.

| Component | Included notice |
|---|---|
| CPython 3.12 | `PYTHON-3.12-LICENSE.txt`, `PYTHON-3.12-THIRD-PARTY.rst` |
| CPython 3.14 | `PYTHON-3.14-LICENSE.txt`, `PYTHON-3.14-THIRD-PARTY.rst` |
| PyInstaller bootloader, runtime loader/hooks | `PYINSTALLER-COPYING.txt`, including the bootloader distribution exception and applicable license texts |
| OpenSSL 3 | `OPENSSL-LICENSE.txt` |
| libffi | `LIBFFI-LICENSE.txt` |
| zlib | `ZLIB-LICENSE.txt` |
| bzip2 | `BZIP2-LICENSE.txt` |
| XZ / liblzma | `XZ-COPYING.txt`, `XZ-COPYING.0BSD.txt` |
| Expat | `EXPAT-COPYING.txt` |
| Zstandard | `ZSTD-LICENSE.txt` |
| libmpdec | `MPDEC-LICENSE.txt` |
| HACL* code used by CPython | `HACL-LICENSE.txt`, plus CPython third-party notices |

The `.rst` files are the upstream Python license documents, including their additional standard-library component notices. Their source-document include/link syntax has been preserved; the corresponding main Python license text is supplied alongside them under the names above.

The tested local Python 3.14 bundle included libssl, libcrypto, liblzma, libzstd and libmpdec shared libraries; its standard-library modules also included the zlib, bzip2, Expat, ctypes and hash modules. Public CI uses Python 3.12. `BUILD.json` identifies each package's Python version and host. The exact set of shared libraries is platform-dependent: this directory is a collection of relevant upstream notices, not a claim that every listed component appears in every package or that every future toolchain's dependencies have been audited.

Keep these notices with redistributed TVCare desktop packages. When changing runtime/toolchain versions, review the actual collected binary dependencies and update the relevant notices. In particular, operating-system or compiler runtime redistributables may have additional platform-specific terms. ADB is not included by default and is not covered by this notice collection.
