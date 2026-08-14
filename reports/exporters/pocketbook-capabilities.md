# PB-CAP — PocketBook Capability Contract

## PB-CAP-SCOPE — Scope and status

PB-CAP-SCOPE-1 — This contract covers the XDXF source profile and the native PocketBook `.dic` build gate.

PB-CAP-SCOPE-2 — The source profile is based on PocketBook's installation guide, the XDXF project, PocketBookDic, and the `jaK` and `jaR` converter language files named by EXP-SRC-1 through EXP-SRC-4.

PB-CAP-SCOPE-3 — The pinned PocketBook converter, Japanese `jaK` files, and Wine 11.0 are installed outside iCloud under `~/Library/Application Support/jitendex-translations/export-tools/`. No PocketBook device or firmware test target is present.

PB-CAP-SCOPE-4 — The native gate is `OPEN`. A release command must fail before compilation unless the user supplies a compiler path, compiler SHA-256, and pinned Japanese language directory.

PB-CAP-SCOPE-5 — Source rendering is allowed for research and review. It is not evidence that the generated `.dic` works on a device.

## PB-CAP-TOOL — Tool contract

| ID | Item | Required value | Current result |
|---|---|---|---|
| PB-CAP-TOOL-1 | Compiler | External PocketBook converter with recorded source and SHA-256 | Installed from pinned Git commit; full corpus compiled |
| PB-CAP-TOOL-2 | Runtime | Native Windows or Wine for a Windows executable | Wine 11.0 installed; full corpus compiled |
| PB-CAP-TOOL-3 | Language files | One pinned `jaK` or `jaR` directory containing `keyboard.txt`, `collates.txt`, and `morphems.txt` | Pinned `jaK` installed and hashed |
| PB-CAP-TOOL-4 | Device | Maintained PocketBook model and firmware | Missing |
| PB-CAP-TOOL-5 | Intermediate | Deterministic UTF-8 XDXF in `visual` format | Implemented; common probe passes |

PB-CAP-TOOL-6 — The build records every external file hash and the exact command. A hash mismatch is a hard failure.

## PB-CAP-MAP — Source mapping

| ID | Source feature | XDXF source mapping | Fidelity before device probe |
|---|---|---|---|
| PB-CAP-MAP-1 | Expression | First `<k>` in one `<ar>` | Exact |
| PB-CAP-MAP-2 | Reading | Additional deduplicated `<k>` and visible reading line | Unknown on device |
| PB-CAP-MAP-3 | Multiple variants | Ordered labeled blocks in one article | Lossless transform |
| PB-CAP-MAP-4 | `div`, `span` | Nested content with semantic line breaks | Lossless transform |
| PB-CAP-MAP-5 | `ol`, `ul`, `li` | Numbered or bulleted text with nesting indentation | Degraded |
| PB-CAP-MAP-6 | `table`, `tr`, `th`, `td` | Labeled rows separated by `│` and line breaks | Degraded |
| PB-CAP-MAP-7 | `ruby`, `rt` | Base text followed by parenthesized reading | Degraded |
| PB-CAP-MAP-8 | Internal `a` | `<kref>` with visible destination | Unknown on device |
| PB-CAP-MAP-9 | External `a` | `<iref>` with visible URL fallback | Unknown on device |
| PB-CAP-MAP-10 | `img` | `<rref>` to a package resource plus alt text | Unknown on device |
| PB-CAP-MAP-11 | `details` | Expanded content; summary stays visible | Lossless transform |
| PB-CAP-MAP-12 | Inline emphasis | XDXF bold and italic visual markup | Unknown on device |
| PB-CAP-MAP-13 | `listStyleType` | Ordered or unordered prefix chosen from the property | Degraded |
| PB-CAP-MAP-14 | Semantic `data.content` | Structural XDXF fallback plus loss-ledger identity | Degraded; XDXF has no portable data attribute |
| PB-CAP-MAP-15 | Semantic `data.class` | Structural XDXF fallback plus loss-ledger identity | Degraded; XDXF has no portable data attribute |
| PB-CAP-MAP-16 | Other semantic data keys | Structural XDXF fallback plus loss-ledger identity | Degraded; XDXF has no portable data attribute |
| PB-CAP-MAP-17 | Tags and tooltips | `<abr>` where accepted, with the description kept in `<co>` | Unknown on device |
| PB-CAP-MAP-18 | AVIF | Deterministic PNG resource | Lossless transform of content |
| PB-CAP-MAP-19 | SVG | Original resource and text alternative | Unknown on device |
| PB-CAP-MAP-20 | Attribution | Visible footer and package attribution file | Exact |

PB-CAP-MAP-21 — Every source tag in EXPINV-TAG-001 through EXPINV-TAG-013 is covered above. Probe-only `details` and `summary` are covered by PB-CAP-MAP-11.

PB-CAP-MAP-22 — Every semantic content name in EXPINV-CONT-001 through EXPINV-CONT-040 uses PB-CAP-MAP-14. Every semantic class in EXPINV-CLASS-001 through EXPINV-CLASS-012 uses PB-CAP-MAP-15.

## PB-CAP-KEY — Index and collision rules

PB-CAP-KEY-1 — One article owns one canonical expression key. Readings are additional keys only when non-empty and different.

PB-CAP-KEY-2 — Keys are deduplicated by exact Unicode value. No normalization silently merges Japanese spellings.

PB-CAP-KEY-3 — A reading that is also another real expression remains a key on both articles. Device behavior for the duplicate result is part of the open probe gate.

PB-CAP-KEY-4 — NUL, invalid XML characters, empty expressions, unsafe resource paths, and resource collisions fail before XDXF output.

## PB-CAP-IMPL — Automated probe result

PB-CAP-IMPL-1 — The common probe passes deterministic XDXF parsing, multiple-key generation, rich fallbacks, resource conversion, and the external compiler argument contract.

PB-CAP-IMPL-2 — The compiler-contract test uses a local fake tool. It does not close any native compiler or device gate.

PB-CAP-IMPL-3 — Commit `3bb444c7a5b1a011e0fca9e99fba0e7ae025e36f`, converter SHA-256 `9eda24d32a9bb76697c8c0ca713d6299c7881ade76bfb317b9ac7bf95d06936f`, and `jaK` compiled the full Run 59 corpus through Wine into export 71. The archive contains 433,885 articles and 415,836 headwords, passed structural verification, and has SHA-256 `348be94570d633078158babd87a5719c13542b201768960e5758e36f00ebb31d`.

## PB-CAP-GATE — Release gate

| ID | Required probe | Status |
|---|---|---|
| PB-CAP-GATE-1 | Compiler provenance and license recorded | OPEN |
| PB-CAP-GATE-2 | `jaK` versus `jaR` search behavior measured | OPEN |
| PB-CAP-GATE-3 | Common probe compiles without warnings | OPEN |
| PB-CAP-GATE-4 | Expression and reading lookup work on device | OPEN |
| PB-CAP-GATE-5 | Rich markup and resources inspected on device | OPEN |
| PB-CAP-GATE-6 | 10,000-entry and full-corpus limits measured | OPEN |
| PB-CAP-GATE-7 | Repeated native build reproducibility measured | OPEN |

PB-CAP-GATE-8 — Until every gate is closed, the implementation may emit XDXF probe material but must not claim PocketBook release compatibility.
