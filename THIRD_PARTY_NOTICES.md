# Third-party sources and assets

The application and Velxio adaptations are distributed under AGPL-3.0; see
[LICENSE](LICENSE). Existing notices and separately licensed assets retain their terms.

| Source | Used for | License / retained notice |
| --- | --- | --- |
| [Velxio](https://github.com/davidmonterocrespo24/velxio), commit `3aba596b8243398e27f4a70ca6f77426f70bab4f` | React editor, board/component library, firmware simulation; downloaded at setup and modified with `services/editor/patches/` | AGPL-3.0, upstream LICENSE, repository LICENSE |
| [Circuitiny](https://github.com/mfranzon/circuitiny) | Adapted 3D breadboard/editor concepts and source in managed Velxio patches | [MIT notice](licenses/circuitiny-MIT.txt) |
| [Ohmlet](https://github.com/JENW1N/ohmlet) | Reference/adaptations for circuit visualization | [MIT notice](licenses/ohmlet-MIT.txt) |
| [Three.js](https://github.com/mrdoob/three.js) | 3D renderer, including generated `services/analyzer/frontend/rover-simulator.js` | [MIT notice](licenses/three-MIT.txt), inline bundle notices |
| [Arduino Uno with breadboard — Thctamm](https://commons.wikimedia.org/wiki/File:Arduino_Uno_with_breadboard.jpg) | Public camera example | CC BY-SA 3.0, [attribution and modifications](shared/data/photos/ATTRIBUTION.md) |
| [Adafruit Motor HAT / Motor Shield](shared/data/physical-models/README.md) | Board geometry sources and derived geometry | CC BY-SA 3.0, original license files in `shared/data/physical-models/` |

Node packages and Python dependencies retain their own licenses. The full editor
dependency graph is pinned in `services/editor/patches/velxio-package-lock.json`; upstream source
and package notices are downloaded during setup. AVR / simavr / Arduino core
packages are fetched from Ubuntu repositories into `.tools/avr`; their package
licenses remain in the extracted tree. They are not bundled into this Git repository.

User uploads, analysis results, API keys, preinstalled tools, and third-party
checkouts are not included in the public source snapshot. Historical development
documents may reference local `outputs/` evidence which is intentionally not published.
