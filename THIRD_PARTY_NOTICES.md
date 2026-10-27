# Third-Party Notices

This product distributes the following third-party open-source components. The full license text for each component is provided with the package or can be obtained from its upstream repository.

## Components Requiring Special Notice

### pystray (LGPLv3)

- **License**: GNU Lesser General Public License v3.0
- **Upstream Source**: https://github.com/moses-palmer/pystray
- **Usage**: System tray monitor for the Windows portable edition (`scripts/monitor/tray_monitor.py`)

Used in accordance with LGPLv3 terms (invoked as an independent library, permitted for closed-source host applications):
- This notice serves as the prominent notice required under Section 4 of the LGPL
- Library source code can be obtained from the upstream URL above
- The full text of LGPLv3 is distributed with the package (in site-packages `pystray-*.dist-info/COPYING.LGPL`)

### pyphen (GPL 2.0+ / LGPL 2.1+ / MPL 1.1 Tri-licensed)

- **License**: Tri-licensed; this product elects to use it under the **MPL 1.1** terms (file-level weak copyleft, does not affect the host application)
- **Upstream Source**: https://github.com/henrik-lehtinen/pyphen (dictionary data from LibreOffice)
- **Usage**: Hyphenation dependency for WeasyPrint PDF export
- **License Text**: Located in site-packages `pyphen-*.dist-info/` (includes COPYING.GPL / COPYING.LGPL / COPYING.MPL)

### WeasyPrint (BSD-3-Clause)

- **Upstream Source**: https://github.com/Kozea/WeasyPrint
- **Usage**: Research report PDF export (`app/utils/report_exporter.py`)

### mini-racer (ISC)

- **Upstream Source**: https://github.com/bpcreech/PyMiniRacer
- **Usage**: JavaScript execution engine

## SearXNG

- **License**: GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)
- **Upstream Source**: https://github.com/searxng/searxng
- **Bundled Version**: 2026.8.6+b023a28
- **License Text**: Located inside the wheel package at `searxng-*.dist-info/licenses/LICENSE` (in site-packages after installation)

### How It Is Used

SearXNG runs as an **independent process/container** (an independent process in the Windows installer package, and an independent container in Docker deployments), and this product communicates with it over its standard HTTP API (`/search?format=json`).

Because the two programs run in separate address spaces and interact solely via a network interface, they do not form a combined work; the rest of this product's codebase is not subject to the copyleft obligations of the SearXNG license.

### Local Modifications (Corresponding Source Notice)

In accordance with Section 13 and the distribution terms of AGPL-3.0, all local modifications made by this product to SearXNG are disclosed below:

**Modification Patch File**: [`config/searxng/searxng-local-modifications.patch`](config/searxng/searxng-local-modifications.patch)

| File | Modification | Reason |
|------|---------|------|
| `searx/valkeydb.py` | Wrapped `import pwd` in a `try/except ImportError` fallback | `pwd` is a Unix-only module and does not exist on Windows |
| `searx/settings.yml` | Minor adjustments to default engine configuration | Availability in mainland China network environments |

The patch file itself is licensed under AGPL-3.0. To apply it:

```bash
cd searxng/
git apply ../config/searxng/searxng-local-modifications.patch
```

### Source Code Availability

- The distributed wheel is a pure Python package; the installed `searx/*.py` files **constitute the complete Corresponding Source** (including the modifications above)
- Unmodified upstream source code can be obtained from the GitHub URL above
- Local modifications are provided in the patch file

### Search Engine Usage Notice

Search results aggregated by SearXNG originate from third-party search engines (Baidu, 360, Bing, Sogou, etc.). This product is intended solely for private deployment and internal use; restrictions on programmatic access under each search engine's terms of service should be evaluated independently by the deploying party.

## Other Dependencies

All other Python dependencies (approximately 250 packages) use permissive licenses (MIT / BSD / Apache-2.0 / PSFL / ISC) with no copyleft obligations, and their license texts are distributed in each package's `dist-info` directory. For the complete list, see `requirements.txt` and run `pip list --format=freeze` after installation.
