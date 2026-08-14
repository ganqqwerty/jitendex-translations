# APP-CAP — Apple Dictionary Capability Contract

## APP-CAP-SCOPE — Scope and status

APP-CAP-SCOPE-1 — This contract covers Dictionary Services XML, CSS, plist, resources, and the native `.dictionary` bundle gate.

APP-CAP-SCOPE-2 — The source profile follows Apple's archived markup and build guides named by EXP-SRC-5 and EXP-SRC-6. The installed compiler is the tested authority.

APP-CAP-SCOPE-3 — Dictionary.app and Dictionary Development Kit 26.6 are installed on macOS 26.5.2. The kit is outside iCloud under `~/Library/Application Support/jitendex-translations/export-tools/`.

APP-CAP-SCOPE-4 — The native client gate remains `OPEN`. A release command fails unless the user supplies the pinned build tool. Schema validation is optional because Apple's schema depends on obsolete remote modules that are not shipped in the kit.

APP-CAP-SCOPE-5 — Project generation is allowed for schema research. It is not evidence that the bundle installs or works in contextual Look Up.

## APP-CAP-TOOL — Tool contract

| ID | Item | Required value | Current result |
|---|---|---|---|
| APP-CAP-TOOL-1 | Build kit | Apple Dictionary Development Kit with provenance and SHA-256 | Installed from Additional Tools for Xcode 26.6 |
| APP-CAP-TOOL-2 | Schema | RELAX NG schema shipped with the same kit | Installed; remote XHTML includes are unavailable |
| APP-CAP-TOOL-3 | Static validator | `xmllint --relaxng` with the pinned schema | Available; blocked by the schema's obsolete remote includes |
| APP-CAP-TOOL-4 | Full client | Dictionary.app on macOS 26.5.2 | Available, unprobed |
| APP-CAP-TOOL-5 | Compact client | System contextual Look Up | Available, unprobed |
| APP-CAP-TOOL-6 | Project generator | XML, CSS, plist, Makefile, and `OtherResources` | Implemented; common probe passes |

APP-CAP-TOOL-7 — The build records the tool and schema hashes and the exact command. A hash mismatch is a hard failure.

APP-CAP-TOOL-8 — The Apple DMG SHA-256 is `d7138cebe372b3bf9a4a06669036f6ee75cbe246dcc990e1b71fc98eca241004`. The `build_dict.sh` SHA-256 is `96c60abedd89f1932bf5a54fe65ed03f739423b0434a1afe9e0cec9aae124ffc`. The shipped schema SHA-256 is `dacdb7713f1a73f47be8446184f58de8fc1a13c0d2f8b822b37c35b137bd63cf`.

## APP-CAP-MAP — Source mapping

| ID | Source feature | Dictionary Services mapping | Fidelity before app probe |
|---|---|---|---|
| APP-CAP-MAP-1 | Expression | Primary `d:index` and visible heading | Exact |
| APP-CAP-MAP-2 | Reading | Separate `d:index` with `d:yomi` | Exact by schema guide, unprobed |
| APP-CAP-MAP-3 | Multiple variants | Ordered XHTML sections in one `d:entry` | Lossless transform |
| APP-CAP-MAP-4 | `div`, `span` | XHTML `div` and `span` with stable classes | Exact by schema guide, unprobed |
| APP-CAP-MAP-5 | `ol`, `ul`, `li` | Native XHTML lists | Exact by schema guide, unprobed |
| APP-CAP-MAP-6 | `table`, `tr`, `th`, `td` | Native XHTML table | Exact by schema guide, unprobed |
| APP-CAP-MAP-7 | `ruby`, `rt` | XHTML ruby when schema accepts it; otherwise styled base and reading spans | Unknown until schema probe |
| APP-CAP-MAP-8 | Internal `a` | `x-dictionary:d:` URI to the canonical expression | Exact by guide, unprobed |
| APP-CAP-MAP-9 | External `a` | HTTPS hyperlink | Exact by guide, unprobed |
| APP-CAP-MAP-10 | `img` | Relative bundle image URL and alt text | Exact by guide, codec unprobed |
| APP-CAP-MAP-11 | `details` | Expanded XHTML block with visible summary | Lossless transform |
| APP-CAP-MAP-12 | Inline emphasis | XHTML element or stable CSS class | Lossless transform |
| APP-CAP-MAP-13 | `listStyleType` | Approved CSS class, not raw source style | Lossless transform |
| APP-CAP-MAP-14 | Semantic `data.content` | `sc-*` CSS class | Lossless transform |
| APP-CAP-MAP-15 | Semantic `data.class` | `dc-*` CSS class | Lossless transform |
| APP-CAP-MAP-16 | Other semantic data keys | `meta-*` CSS class plus visible value when meaningful | Lossless transform |
| APP-CAP-MAP-17 | Tags and tooltips | Visible badge with `title` and front-matter legend | Exact by XHTML behavior, unprobed |
| APP-CAP-MAP-18 | AVIF | Deterministic PNG resource until AVIF is proven | Lossless transform of content |
| APP-CAP-MAP-19 | SVG | Original resource until the schema or client rejects it | Unknown until app probe |
| APP-CAP-MAP-20 | Attribution | Front matter and visible article footer | Exact |

APP-CAP-MAP-21 — Every source tag in EXPINV-TAG-001 through EXPINV-TAG-013 is covered above. Probe-only `details` and `summary` are covered by APP-CAP-MAP-11.

APP-CAP-MAP-22 — Every semantic content name in EXPINV-CONT-001 through EXPINV-CONT-040 uses APP-CAP-MAP-14. Every semantic class in EXPINV-CLASS-001 through EXPINV-CLASS-012 uses APP-CAP-MAP-15.

## APP-CAP-KEY — Index and identity rules

APP-CAP-KEY-1 — Each canonical expression has one stable `d:entry` ID derived from its UTF-8 expression bytes.

APP-CAP-KEY-2 — The expression and each distinct reading receive separate `d:index` elements. `d:yomi` holds the reading, not a display-only transliteration.

APP-CAP-KEY-3 — Exact duplicate index tuples are removed. Real expression entries are never replaced by aliases.

APP-CAP-KEY-4 — Internal links target the canonical expression. Missing targets remain visible text and are recorded as degraded.

APP-CAP-KEY-5 — NUL, invalid XML characters, empty expressions, unsafe resource paths, and resource collisions fail before XML output.

## APP-CAP-IMPL — Automated probe result

APP-CAP-IMPL-1 — The common probe passes namespace-aware XML parsing, expression and yomi index counts, XHTML rich rendering, resource conversion, and the four-argument build-tool contract.

APP-CAP-IMPL-2 — The build-contract test uses a local fake tool. It does not close the schema, installation, Dictionary.app, or contextual Look Up gates.

APP-CAP-IMPL-3 — DDK 26.6 compiled the full Run 59 corpus into export 72 with 433,885 articles, 415,836 headwords, and 656,024 indexes. The verified archive SHA-256 is `3bedac203b1591184563b6cda2d348d6e21ee041d5b97b910e8723d11c72e3dc`.

## APP-CAP-GATE — Release gate

| ID | Required probe | Status |
|---|---|---|
| APP-CAP-GATE-1 | DDK provenance, version, license, and hashes recorded | CLOSED |
| APP-CAP-GATE-2 | Common probe validates against the shipped schema | OPEN |
| APP-CAP-GATE-3 | Common probe compiles and installs | OPEN |
| APP-CAP-GATE-4 | Expression and `d:yomi` lookup work in Dictionary.app | OPEN |
| APP-CAP-GATE-5 | Contextual Look Up preserves examples and layout | OPEN |
| APP-CAP-GATE-6 | Light and dark rendering inspected | OPEN |
| APP-CAP-GATE-7 | 10,000-entry and full-corpus limits measured | OPEN |
| APP-CAP-GATE-8 | Repeated native build reproducibility measured | OPEN |

APP-CAP-GATE-9 — Until every gate is closed, the implementation may emit a complete DDK project but must not claim Apple Dictionary release compatibility.
