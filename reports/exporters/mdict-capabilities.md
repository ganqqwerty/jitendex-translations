# MD-CAP — MDict Capability Contract

## MD-CAP-SCOPE — Scope and status

MD-CAP-SCOPE-1 — This contract covers unencrypted MDict 2.0 MDX records and same-basename MDD resources.

MD-CAP-SCOPE-2 — MDict's official site advertises HTML, CSS, images, and audio. `mdict-utils` 1.3.14 provides an MIT-licensed MDict 2.0 writer. Its pinned wheel SHA-256 is `205f7c37a12be29de8591276bb1cca525e6eaf3c43f43c6ac2a919b6f886e235`.

MD-CAP-SCOPE-3 — The writer source was inspected. Its default header uses the current date and its key sort uses the process locale. The exporter must fix both values for deterministic output.

MD-CAP-SCOPE-4 — No official Windows, Android, or iOS MDict client is available in this workspace. No official MdxBuilder comparison has been made.

MD-CAP-SCOPE-5 — Static compilation and independent header checks can be implemented. The multi-client release gate is `OPEN`.

## MD-CAP-TOOL — Tool contract

| ID | Item | Required value | Current result |
|---|---|---|---|
| MD-CAP-TOOL-1 | Writer | `mdict-utils==1.3.14` | Pinned |
| MD-CAP-TOOL-2 | Binary profile | Unencrypted MDX and MDD version 2.0 | Selected |
| MD-CAP-TOOL-3 | Determinism | Fixed header date, C collation, sorted inputs | Implemented; common probe passes |
| MD-CAP-TOOL-4 | Independent static check | Header length, checksum, XML attributes, file hashes | Implemented; common probe passes |
| MD-CAP-TOOL-5 | Independent full reader | `js-mdict` or equivalent | Missing |
| MD-CAP-TOOL-6 | Official comparison | MdxBuilder on the same probe | Missing |
| MD-CAP-TOOL-7 | Client matrix | Official Windows, Android, and iOS clients | Missing |

## MD-CAP-MAP — Source mapping

| ID | Source feature | MDict mapping | Fidelity before client probe |
|---|---|---|---|
| MD-CAP-MAP-1 | Expression | Canonical MDX key and visible heading | Exact |
| MD-CAP-MAP-2 | Reading | `@@@LINK` for one safe target; disambiguation record for many targets | Lossless transform, unprobed |
| MD-CAP-MAP-3 | Multiple variants | Ordered HTML sections in one record | Lossless transform |
| MD-CAP-MAP-4 | `div`, `span` | Native HTML with stable classes | Exact in source, unprobed |
| MD-CAP-MAP-5 | `ol`, `ul`, `li` | Native HTML lists | Exact in source, unprobed |
| MD-CAP-MAP-6 | `table`, `tr`, `th`, `td` | Native HTML table | Exact in source, unprobed |
| MD-CAP-MAP-7 | `ruby`, `rt` | Native HTML ruby plus CSS | Exact in source, unprobed |
| MD-CAP-MAP-8 | Internal `a` | `entry://` URI with URL-encoded key | Exact in source, unprobed |
| MD-CAP-MAP-9 | External `a` | HTTPS hyperlink | Exact in source, unprobed |
| MD-CAP-MAP-10 | `img` | Leading-slash MDD resource URL and alt text | Exact in source, unprobed |
| MD-CAP-MAP-11 | `details` | Expanded HTML block with visible summary | Lossless transform |
| MD-CAP-MAP-12 | Inline emphasis | HTML element or approved CSS property | Lossless transform |
| MD-CAP-MAP-13 | `listStyleType` | Approved CSS class | Lossless transform |
| MD-CAP-MAP-14 | Semantic `data.content` | Stable `sc-*` class | Lossless transform |
| MD-CAP-MAP-15 | Semantic `data.class` | Stable `dc-*` class | Lossless transform |
| MD-CAP-MAP-16 | Other semantic data keys | Stable `meta-*` class plus visible value when meaningful | Lossless transform |
| MD-CAP-MAP-17 | Tags and tooltips | Visible badge with `title` and a package legend | Exact in source, unprobed |
| MD-CAP-MAP-18 | AVIF | Deterministic PNG in MDD | Lossless transform of content |
| MD-CAP-MAP-19 | SVG | Original MDD resource with text alternative | Exact in source, unprobed |
| MD-CAP-MAP-20 | Attribution | Visible footer and package attribution record | Exact |

MD-CAP-MAP-21 — Every source tag in EXPINV-TAG-001 through EXPINV-TAG-013 is covered above. Probe-only `details` and `summary` are covered by MD-CAP-MAP-11.

MD-CAP-MAP-22 — Every semantic content name in EXPINV-CONT-001 through EXPINV-CONT-040 uses MD-CAP-MAP-14. Every semantic class in EXPINV-CLASS-001 through EXPINV-CLASS-012 uses MD-CAP-MAP-15.

## MD-CAP-KEY — Key and redirect rules

MD-CAP-KEY-1 — Canonical expression records always win over reading aliases.

MD-CAP-KEY-2 — A reading with one target uses one `@@@LINK`. A reading with several targets uses a visible disambiguation record with `entry://` links.

MD-CAP-KEY-3 — A reading equal to a real expression does not replace that expression record. Its other targets are linked from a visible related-entry section.

MD-CAP-KEY-4 — Redirect targets must exist. Redirect chains and cycles are forbidden.

MD-CAP-KEY-5 — Keys are sorted by fixed C collation after the writer's documented strip-key transform. Exact duplicate record keys fail before writing.

MD-CAP-KEY-6 — NUL, line breaks in keys, invalid XML characters, unsafe resource paths, and resource collisions fail before MDX output.

## MD-CAP-IMPL — Automated probe result

MD-CAP-IMPL-1 — Two complete common-probe builds produced byte-identical ZIP, MDX, and MDD bytes.

MD-CAP-IMPL-2 — The independent checker verifies both binary headers without using the writer. `mdict-utils` then reads every probe key and MDD resource as a secondary interoperability check.

MD-CAP-IMPL-3 — MD-CAP-IMPL-2 is not the independent full-reader gate because the secondary reader ships in the same project as the writer.

## MD-CAP-GATE — Release gate

| ID | Required probe | Status |
|---|---|---|
| MD-CAP-GATE-1 | Common probe builds twice with byte-identical package, MDX, and MDD | PASS |
| MD-CAP-GATE-2 | Independent reader checks every probe key and resource | OPEN |
| MD-CAP-GATE-3 | Common probe compared with MdxBuilder | OPEN |
| MD-CAP-GATE-4 | `entry://`, redirects, duplicate keys, and MDD paths tested in clients | OPEN |
| MD-CAP-GATE-5 | HTML, CSS, ruby, tables, images, and themes tested in clients | OPEN |
| MD-CAP-GATE-6 | Windows, Android, and iOS intersection recorded or contract narrowed | OPEN |
| MD-CAP-GATE-7 | 10,000-entry and full-corpus limits measured | OPEN |

MD-CAP-GATE-8 — Static packages may be marked `experimental`. They must not be described as client-verified until the open gates close.
