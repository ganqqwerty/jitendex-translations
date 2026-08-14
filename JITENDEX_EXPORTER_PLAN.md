# EXP — Rich Dictionary Exporter Plan

## EXP-GOAL — Goal and order

EXP-GOAL-1 — Add exporters for EX1 PocketBook, EX2 Apple Dictionary, and EX3 MDict.

EXP-GOAL-2 — Preserve structure, rich text, examples, tags, links, ruby, tables, and images before using a simpler fallback.

EXP-GOAL-3 — Study and test all three formats before production exporter work starts.

EXP-GOAL-4 — Keep the requested implementation order: EX1, EX2, then EX3.

EXP-GOAL-5 — Use the full Run 59 corpus as the release corpus. It has 433,885 articles and no untranslated headwords.

EXP-GOAL-6 — A format is not complete when it merely opens. Search, readings, layout, examples, media, links, and attribution must also work.

## EXP-BASE — Current export base

EXP-BASE-1 — All exporters will start from `materialize_run()` in `src/jitendex_ru/build_dictionary.py`.

EXP-BASE-2 — Every exporter will load the approved Russian tag catalog and run the same tag localization used by Yomitan and GoldenDict.

EXP-BASE-3 — The input remains the structured Yomitan article tree. New exporters must not parse rendered GoldenDict HTML.

EXP-BASE-4 — The current tree contains links, lists, details, ruby, tables, images, spans, inline styles, language markers, and semantic `data` fields.

EXP-BASE-5 — The current source archive contains 201 AVIF images and 48 SVG images. It contains no audio, but the model must keep future audio support.

EXP-BASE-6 — One shared export model will represent entries, variants, index keys, readings, tags, rich nodes, links, resources, and attribution.

EXP-BASE-7 — Each target gets its own renderer. A lowest-common-denominator HTML renderer is forbidden.

EXP-BASE-8 — The existing GoldenDict exporter remains unchanged until the shared model proves byte-equivalent output in its tests.

## EXP-RULE — Fidelity rules

EXP-RULE-1 — Preserve meaning first, presentation second, and decoration third.

EXP-RULE-2 — Keep semantic classes even when a target cannot keep the original CSS.

EXP-RULE-3 — Keep examples next to their sense. Do not move all examples to an article footer.

EXP-RULE-4 — Keep tag labels and tooltips. If a target has no tooltip, show the description in a visible legend or note.

EXP-RULE-5 — Keep Japanese expression and reading as separate values whenever the target supports that distinction.

EXP-RULE-6 — Keep tables as tables when tested support exists. Otherwise use labeled rows, not unstructured text.

EXP-RULE-7 — Keep ruby when tested support exists. Otherwise render base text followed by a readable parenthesized annotation.

EXP-RULE-8 — Keep internal links when tested support exists. Otherwise render the destination text without a dead link.

EXP-RULE-9 — Keep a usable image when the source codec is unsupported. Codec conversion is preferred over omission.

EXP-RULE-10 — Expand collapsible content when disclosure widgets are unsupported. Hidden content is not an acceptable fallback.

EXP-RULE-11 — Do not add JavaScript to dictionary entries unless a research result proves it is required. The default is static HTML or XML.

EXP-RULE-12 — Every transformation is classified as `exact`, `lossless-transform`, `degraded`, or `omitted` in the build manifest.

EXP-RULE-13 — Any `omitted` content fails the build unless an explicit, tested rule names the omitted feature and its reason.

EXP-RULE-14 — All outputs retain Jitendex, JMdict, Tatoeba, and CC BY-SA attribution.

## EXP-EVID — Evidence known before probes

| ID | Area | EX1 PocketBook | EX2 Apple Dictionary | EX3 MDict |
|---|---|---|---|---|
| EXP-EVID-1 | Native package | Binary `.dic` | `.dictionary` bundle | `.mdx` plus optional `.mdd` |
| EXP-EVID-2 | Build source | XDXF is the best documented route to the converter | UTF-8 Dictionary Services XML, CSS, plist, and resources | UTF-8 headword and HTML records |
| EXP-EVID-3 | Rich body | XDXF has semantic tags, but converter survival is unknown | XHTML plus Dictionary Services markup | HTML and CSS are advertised by MDict |
| EXP-EVID-4 | Search aliases | Multiple XDXF keys are possible; device behavior is unknown | Multiple `d:index` values are supported | Extra keys and `@@@LINK` redirects are common |
| EXP-EVID-5 | Japanese reading | `jaK` and `jaR` language files exist; their exact behavior is unknown | `d:yomi` is designed for Japanese readings | Reading keys can redirect to an expression entry |
| EXP-EVID-6 | Images | XDXF resources exist in the standard; PocketBook support is unknown | Bundle resources and images are documented | Images can be stored in MDD |
| EXP-EVID-7 | Audio | Unknown and must be probed | Sounds and movies are documented | Audio resources and `sound://` links are supported by common clients |
| EXP-EVID-8 | CSS | No reliable CSS path is documented | A dictionary CSS file is part of the build | CSS can be linked from entry HTML and stored with resources |
| EXP-EVID-9 | Main risk | Old proprietary converter and device limits | Archived build kit and schema | Proprietary format and different client renderers |

EXP-EVID-10 — The evidence table is not a support promise. Only probe results may become a target capability contract.

## EXP-RSCH — Common research protocol

EXP-RSCH-1 — Create `reports/exporters/source-feature-inventory.md` from the full source archive and Run 59 output.

EXP-RSCH-2 — Count every structured tag, semantic class, style property, link form, image option, resource codec, and maximum article size.

EXP-RSCH-3 — Create one small probe dictionary with at least one case for every source feature.

EXP-RSCH-4 — Include Japanese expressions, kana readings, mixed scripts, multiple readings, duplicate expressions, and reading-only entries.

EXP-RSCH-5 — Include nested senses, examples, tags with tooltips, ruby, tables with spans, lists, internal links, attribution, and long text.

EXP-RSCH-6 — Include AVIF, SVG, PNG, transparent images, dark images, missing alt text, and a future-audio placeholder.

EXP-RSCH-7 — Include boundary cases for XML characters, NUL rejection, long headwords, long articles, duplicate keys, and resource name collisions.

EXP-RSCH-8 — Build each probe with a pinned tool version. Record the source URL, license, SHA-256, host OS, and command line.

EXP-RSCH-9 — Test the compiled probe in the real target application or device. A browser preview is not enough.

EXP-RSCH-10 — Capture light and dark screenshots when the target offers both themes.

EXP-RSCH-11 — Test expression search, reading search, result labels, repeated keys, internal links, and back navigation.

EXP-RSCH-12 — Record each result as supported, transformed, unsupported, broken, or still unknown.

EXP-RSCH-13 — Write one capability report per format under `reports/exporters/`.

EXP-RSCH-14 — Finish all three capability reports before adding production exporter modules.

EXP-RSCH-15 — The approved reports become the fixed renderer contracts. Later degradation requires a report update and a regression test.

## EX1-RSCH — PocketBook research gate

EX1-RSCH-1 — Obtain the PocketBook converter from a traceable source. Do not commit the executable until its redistribution license is known.

EX1-RSCH-2 — Record the exact converter hash. Test it on Windows and through Wine because it is a Windows binary.

EX1-RSCH-3 — Obtain and pin the Japanese `jaK` and `jaR` `keyboard.txt`, `collates.txt`, and `morphems.txt` files.

EX1-RSCH-4 — Explain the difference between `jaK` and `jaR` from their file contents and observed device search behavior.

EX1-RSCH-5 — Compare XDXF `logical` and `visual` articles. Choose the form that keeps more structure after compilation.

EX1-RSCH-6 — Probe XDXF `def`, `pos`, `tr`, `dtrn`, `ex`, `co`, `abr`, `c`, `kref`, `rref`, and nested `su` markup.

EX1-RSCH-7 — Probe basic visual tags such as bold, italic, line break, lists, tables, ruby, and inline color.

EX1-RSCH-8 — Probe multiple `<k>` values for expression and reading lookup. Compare this with separate alias articles.

EX1-RSCH-9 — Probe kana, kanji, half-width forms, punctuation, long vowel marks, iteration marks, and mixed Latin text.

EX1-RSCH-10 — Probe image and resource handling in both the converter and the current PocketBook firmware.

EX1-RSCH-11 — Probe tooltip alternatives. Prefer XDXF abbreviation or comment semantics before making descriptions permanently visible.

EX1-RSCH-12 — Find the maximum safe headword length, article length, entry count, block count, and final `.dic` size.

EX1-RSCH-13 — Compile a representative 10,000-entry sample before attempting the full corpus.

EX1-RSCH-14 — Compile the full corpus and measure time, peak memory, file size, startup time, and lookup latency.

EX1-RSCH-15 — Test on at least one maintained PocketBook model with current firmware. Record model and firmware.

EX1-RSCH-16 — Write the results to `reports/exporters/pocketbook-capabilities.md`.

EX1-RSCH-17 — The EX1 gate passes only when Japanese expression and reading lookup work and every rich feature has an approved mapping or fallback.

## EX1-IMPL — PocketBook implementation

EX1-IMPL-1 — Add `src/jitendex_ru/pocketbook.py` after EX1-RSCH passes.

EX1-IMPL-2 — Render a deterministic UTF-8 XDXF intermediate file from the shared export model.

EX1-IMPL-3 — Keep XDXF semantic elements that survive the probe. Use visual markup only where it preserves more tested information.

EX1-IMPL-4 — Treat the external PocketBook compiler as a required tool with a configured path and verified SHA-256.

EX1-IMPL-5 — Keep the compiler outside the Python package unless redistribution is clearly allowed.

EX1-IMPL-6 — Convert media only according to the tested device profile. Preserve the original source path in the manifest.

EX1-IMPL-7 — Add `translationctl export-pocketbook --run-id ID --output PATH`.

EX1-IMPL-8 — Package the `.dic`, manifest, attribution, installation note, and capability-profile version in a deterministic ZIP.

EX1-IMPL-9 — Add `translationctl verify-pocketbook PATH`.

EX1-IMPL-10 — Verification checks the XDXF, compiler exit, package hash, entry counts, index counts, resources, loss ledger, and probe-device result.

## EX2-RSCH — Apple Dictionary research gate

EX2-RSCH-1 — The Dictionary Development Kit was acquired from Apple Developer Downloads in `Additional Tools for Xcode 26.6`; Apple's download terms apply and its hashes are recorded in the capability contract.

EX2-RSCH-2 — Do not assume the archived 2007 guide matches the compiler. Treat the installed schema and compiler as the tested authority.

EX2-RSCH-3 — This workstation has Dictionary.app and Dictionary Development Kit 26.6 on macOS 26.5.2. The kit is stored outside iCloud under `~/Library/Application Support/jitendex-translations/export-tools/`.

EX2-RSCH-4 — Confirm that the kit builds and installs an unsigned custom bundle on macOS 26.5.2.

EX2-RSCH-5 — Probe the installed RELAX NG schema with headings, lists, tables, ruby, images, links, language attributes, classes, and inline styles.

EX2-RSCH-6 — Probe whether semantic `data-*` attributes are accepted. If not, map them to stable CSS classes.

EX2-RSCH-7 — Probe AVIF, SVG, PNG, transparent images, audio, and relative resource paths inside the bundle.

EX2-RSCH-8 — Probe CSS layout, dark mode, inherited colors, relative font sizes, print-like rules, and the small contextual lookup window.

EX2-RSCH-9 — Do not use absolute font families or sizes unless a probe proves they are needed.

EX2-RSCH-10 — Probe multiple `d:index` elements, `d:yomi`, duplicate expressions, multiple readings, and reading-only entries.

EX2-RSCH-11 — Probe `d:anchor` and `x-dictionary:` links for cross-references and anchored subentry lookup.

EX2-RSCH-12 — Keep examples at normal priority. Do not use `d:priority="2"` because that can hide them in contextual lookup.

EX2-RSCH-13 — Add front matter with attribution, license, version, provenance, and a compact tag legend.

EX2-RSCH-14 — Test lookup in Dictionary.app and the system contextual Look Up panel.

EX2-RSCH-15 — Test Japanese search by kanji and kana, result ordering, displayed title, link navigation, and compact-window layout.

EX2-RSCH-16 — Check whether compiler output is reproducible. If it is not, identify and normalize only proven variable metadata.

EX2-RSCH-17 — Build a representative 10,000-entry sample before attempting the full corpus.

EX2-RSCH-18 — Build the full corpus and measure XML size, compiler time, peak memory, bundle size, app indexing time, and lookup latency.

EX2-RSCH-19 — Write the results to `reports/exporters/apple-dictionary-capabilities.md`.

EX2-RSCH-20 — The EX2 gate passes only when the bundle works in both full and contextual views and Japanese reading search is correct.

## EX2-IMPL — Apple Dictionary implementation

EX2-IMPL-1 — Add `src/jitendex_ru/apple_dictionary.py` after EX2-RSCH passes.

EX2-IMPL-2 — Stream deterministic UTF-8 Dictionary Services XML. Do not hold the full 433,885-entry XML document in memory.

EX2-IMPL-3 — Give every `d:entry` and link target a stable ID derived from canonical entry identity, not output order.

EX2-IMPL-4 — Index the expression and reading with separate `d:index` elements and the tested `d:yomi` mapping.

EX2-IMPL-5 — Render valid XHTML with target CSS and tested resource paths.

EX2-IMPL-6 — Generate the plist, CSS, front matter, resources, and Dictionary Development Kit project files.

EX2-IMPL-7 — Treat the Apple build tool as an external, hashed dependency.

EX2-IMPL-8 — Add `translationctl export-apple-dictionary --run-id ID --output PATH`.

EX2-IMPL-9 — Package the `.dictionary` bundle, manifest, source report, and installation note in a deterministic ZIP.

EX2-IMPL-10 — Add `translationctl verify-apple-dictionary PATH`.

EX2-IMPL-11 — Verification checks the source XML against the pinned schema, bundle structure, indexes, resources, counts, links, loss ledger, and app smoke results.

## EX3-RSCH — MDict research gate

EX3-RSCH-1 — Treat MDict as a proprietary format with an official feature description but no public authoritative binary specification.

EX3-RSCH-2 — Use unencrypted MDX version 2.0 as the first candidate because `mdict-utils` can write it and common readers support it.

EX3-RSCH-3 — Pin and inspect the exact `mdict-utils` release. Record its MIT license and package hash.

EX3-RSCH-4 — Compare `mdict-utils` output with the official MdxBuilder on the same probe input.

EX3-RSCH-5 — Use an independent parser to inspect output. Do not verify a package only with the library that wrote it.

EX3-RSCH-6 — Probe HTML headings, lists, tables, ruby, details, images, language attributes, inline styles, classes, and semantic `data-*` attributes.

EX3-RSCH-7 — Probe external CSS beside the MDX and CSS stored inside the MDD. Choose the most portable tested path.

EX3-RSCH-8 — Probe light and dark themes without assuming `prefers-color-scheme` works in every client.

EX3-RSCH-9 — Probe `entry://` links, anchors, `@@@LINK` redirects, redirect chains, duplicate keys, and redirect cycles.

EX3-RSCH-10 — Probe expression keys, reading keys, mixed scripts, punctuation, key case, and `StripKey` behavior.

EX3-RSCH-11 — Probe MDD path separators, leading slashes, case sensitivity, nested folders, and resource name collisions.

EX3-RSCH-12 — Probe AVIF, SVG, PNG, transparent images, CSS resources, and common audio formats.

EX3-RSCH-13 — Test at least the official Windows, Android, and iOS MDict clients, or explicitly narrow the compatibility contract when one is unavailable.

EX3-RSCH-14 — Record renderer differences. The contract uses the intersection of tested clients unless a client-specific profile is approved.

EX3-RSCH-15 — Exclude JavaScript from the base profile even when one client can run it.

EX3-RSCH-16 — Check header dates, sorting, compression, block sizes, and writer iteration order for reproducible output.

EX3-RSCH-17 — Build a representative 10,000-entry sample before attempting the full corpus.

EX3-RSCH-18 — Build the full corpus and measure MDX and MDD sizes, time, memory, import time, lookup latency, and duplicate-key behavior.

EX3-RSCH-19 — Write the results to `reports/exporters/mdict-capabilities.md`.

EX3-RSCH-20 — The EX3 gate passes only when all required clients render the approved profile and expression and reading lookups work.

## EX3-IMPL — MDict implementation

EX3-IMPL-1 — Add `src/jitendex_ru/mdict.py` after EX3-RSCH passes.

EX3-IMPL-2 — Generate deterministic UTF-8 HTML records and an unencrypted MDX version 2.0 file.

EX3-IMPL-3 — Store CSS and converted media in a same-basename MDD when the capability contract approves that path.

EX3-IMPL-4 — Use one canonical expression record and tested reading redirects where this avoids duplicate article bodies.

EX3-IMPL-5 — Detect key collisions, duplicate redirects, missing redirect targets, redirect chains over the approved limit, and cycles.

EX3-IMPL-6 — Pin `mdict-utils`, or keep a small reviewed writer patch if deterministic output cannot be achieved upstream.

EX3-IMPL-7 — Add `translationctl export-mdict --run-id ID --output PATH`.

EX3-IMPL-8 — Package the MDX, MDD, manifest, attribution, installation note, and capability-profile version in a deterministic ZIP.

EX3-IMPL-9 — Add `translationctl verify-mdict PATH`.

EX3-IMPL-10 — Verification uses an independent parser to check headers, blocks, keys, redirects, records, MDD resources, loss ledger, and hashes.

## EXP-MAP — Shared semantic mapping

| ID | Source feature | Preferred target mapping |
|---|---|---|
| EXP-MAP-1 | Expression | Native primary index key and visible heading |
| EXP-MAP-2 | Reading | Native yomi or reading index; tested alias only when needed |
| EXP-MAP-3 | Multiple variants | One visible article with ordered variant sections |
| EXP-MAP-4 | Sense groups | Nested semantic groups or ordered blocks |
| EXP-MAP-5 | Examples | Dedicated example block directly under its sense |
| EXP-MAP-6 | Tags | Visible badge or semantic label with Russian tooltip text retained |
| EXP-MAP-7 | Ruby | Native ruby, then base text plus parenthesized reading |
| EXP-MAP-8 | Tables | Native table, then labeled row blocks |
| EXP-MAP-9 | Internal links | Native dictionary URI or reference element |
| EXP-MAP-10 | External links | Safe hyperlink when supported, otherwise visible URL text |
| EXP-MAP-11 | Collapsible content | Native disclosure only when tested; otherwise expanded |
| EXP-MAP-12 | Images | Original codec when tested; otherwise deterministic PNG |
| EXP-MAP-13 | Inline style | Approved target CSS property, then semantic class, then readable plain layout |
| EXP-MAP-14 | Attribution | Visible article attribution plus package front matter |

EXP-MAP-15 — The capability reports replace each preferred mapping with an exact mapping for that format.

## EXP-CODE — Shared code structure

EXP-CODE-1 — Add `src/jitendex_ru/export_model.py` for immutable normalized entry and resource types.

EXP-CODE-2 — Add `src/jitendex_ru/export_render.py` only for safe escaping, shared traversal, loss recording, and codec helpers.

EXP-CODE-3 — Keep target markup, CSS, index rules, package rules, and external tool calls inside the target module.

EXP-CODE-4 — Move reusable GoldenDict code only after characterization tests protect its current output.

EXP-CODE-5 — Use sorted canonical identities for entries, index keys, links, and resources.

EXP-CODE-6 — Reject unsafe paths, absolute paths, path traversal, NUL, invalid XML characters, and resource collisions before rendering.

EXP-CODE-7 — Stream full-corpus intermediates and package files. Do not build a second full dictionary copy in memory.

EXP-CODE-8 — Record source archive SHA-256, run ID, tag catalog version, exporter version, tool hashes, capability profile, and output hashes.

## EXP-TEST — Test plan

EXP-TEST-1 — Add unit tests for every structured node and every target mapping.

EXP-TEST-2 — Add golden fixtures for the common probe corpus and each target renderer.

EXP-TEST-3 — Test XML and HTML escaping with Japanese, Russian, symbols, quotes, and malformed input.

EXP-TEST-4 — Test every index rule with expression-only, reading-only, multiple readings, duplicates, and mixed scripts.

EXP-TEST-5 — Test resource paths, codec conversion, transparency, dimensions, collisions, missing files, and unsupported codecs.

EXP-TEST-6 — Test internal links, missing targets, cycles, anchors, and target-specific URI encoding.

EXP-TEST-7 — Compare source feature counts with rendered feature and loss counts.

EXP-TEST-8 — Fail when a renderer sees a source tag, style, or semantic class that has no mapping decision.

EXP-TEST-9 — Use the target schema or compiler for static validation where available.

EXP-TEST-10 — Use an independent reader for compiled MDict output and any PocketBook parser found during research.

EXP-TEST-11 — Run real application or device smoke tests from the capability reports before release.

EXP-TEST-12 — Build every format twice and require byte-identical packages, or document a proven compiler exception before approval.

EXP-TEST-13 — Run the full Python suite after each exporter and keep the Yomitan and GoldenDict verification gates passing.

EXP-TEST-14 — Set measured full-corpus time, memory, package size, and lookup thresholds after the research builds.

## EXP-ACPT — Acceptance gates

EXP-ACPT-1 — Research is complete when all three capability reports have tested mappings for every source feature.

EXP-ACPT-2 — Shared code is complete when it represents every source feature without presentation loss.

EXP-ACPT-3 — EX1 is complete when the full `.dic` installs on the recorded PocketBook device and passes expression, reading, layout, media, and link checks.

EXP-ACPT-4 — EX2 is complete when the full bundle works in Dictionary.app and contextual Look Up with correct `d:yomi` search.

EXP-ACPT-5 — EX3 is complete when the full MDX and MDD pass independent parsing and the approved client matrix.

EXP-ACPT-6 — No exporter is complete with an unexplained `degraded` item or any unapproved `omitted` item.

EXP-ACPT-7 — Every final package has deterministic hashes, a loss ledger, attribution, installation instructions, and a verified full-corpus manifest.

## EXP-SEQ — Delivery sequence

EXP-SEQ-1 — Phase A inventories the source and builds the common probe corpus.

EXP-SEQ-2 — Phase B completes EX1-RSCH, EX2-RSCH, and EX3-RSCH without production exporter code.

EXP-SEQ-3 — Phase C reviews and freezes all three capability contracts.

EXP-SEQ-4 — Phase D adds the shared export model and characterization tests.

EXP-SEQ-5 — Phase E implements and releases EX1 PocketBook.

EXP-SEQ-6 — Phase F implements and releases EX2 Apple Dictionary.

EXP-SEQ-7 — Phase G implements and releases EX3 MDict.

EXP-SEQ-8 — Each release updates README commands and the run history only after full-corpus verification.

## EXP-RISK — Main risks

EXP-RISK-1 — PocketBook compilation depends on an old proprietary binary. License, stability, and maximum-size behavior are unknown.

EXP-RISK-2 — PocketBook XDXF is richer than the observed converter may be. The real device decides the supported subset.

EXP-RISK-3 — Apple's format is well documented, but the documentation and kit are old. Current macOS compatibility must be proven.

EXP-RISK-4 — MDict supports rich HTML, but HTML, CSS, media, and redirects can differ across clients.

EXP-RISK-5 — The full corpus is large. All three compilers may expose limits that small probes miss.

EXP-RISK-6 — AVIF and SVG are not portable across all targets. Deterministic conversion and visual comparison are required.

EXP-RISK-7 — Reading aliases can collide with real expression entries. Collision policy must prefer real content and remain visible in reports.

## EXP-SRC — Research sources

EXP-SRC-1 — PocketBook documents installation of free `.dic` dictionaries in its [official installation guide](https://support.pocketbook-int.com/dictionaries/u/Dictionary%20instalation%20Guide%20EN.pdf).

EXP-SRC-2 — The [XDXF project](https://github.com/soshial/xdxf_makedict) documents the semantic exchange format and its dictionary-specific elements.

EXP-SRC-3 — [PocketBookDic](https://github.com/Markismus/PocketBookDic) documents the XDXF-to-converter route and known external tool needs.

EXP-SRC-4 — The [PocketBook converter language files](https://github.com/Markismus/LanguageFilesPocketbookConverter) provide `jaK` and `jaR` collation, keyboard, and morphology inputs.

EXP-SRC-5 — Apple's archived [Dictionary markup guide](https://developer.apple.com/library/archive/documentation/UserExperience/Conceptual/DictionaryServicesProgGuide/schema/schema.html) defines XHTML, `d:entry`, `d:index`, `d:yomi`, links, and priority behavior.

EXP-SRC-6 — Apple's archived [dictionary build guide](https://developer.apple.com/library/archive/documentation/UserExperience/Conceptual/DictionaryServicesProgGuide/prepare/prepare.html) defines the XML, CSS, plist, resources, bundle build, and Japanese dictionary flow.

EXP-SRC-7 — Apple's current [Dictionary Services API page](https://developer.apple.com/documentation/coreservices/dictionary_services) confirms that system dictionary lookup APIs still exist.

EXP-SRC-8 — MDict's [official site](https://www.mdict.cn/wp/?lang=zh) states that dictionary content supports HTML, CSS, images, and audio.

EXP-SRC-9 — [mdict-utils](https://github.com/liuyug/mdict-utils) can read MDict 3.0 and read and write unencrypted MDict 2.0 packages.

EXP-SRC-10 — [js-mdict](https://github.com/terasum/js-mdict) provides an independent reader and examples of HTML, MDD resources, duplicate keys, links, and redirects.

## EXP-STAT — Implementation status

EXP-STAT-1 — Phase A and Phase B artifacts now exist: the full source inventory, common probe, and three capability contracts are under `reports/exporters/` and `probes/exporters/`.

EXP-STAT-2 — The shared rich model, loss ledger, codec helpers, three target renderers, deterministic packages, verifiers, CLI commands, and automated probe tests are implemented.

EXP-STAT-3 — The MDict common probe is byte-reproducible. Its official client and independent full-reader gates remain open.

EXP-STAT-4 — PocketBook and Apple source projects and external-tool contracts are tested with fake tools. Their proprietary native tools and real application or device gates remain open.

EXP-STAT-5 — No target is release-complete under EXP-ACPT-3 through EXP-ACPT-5. Experimental package labels and hard external-tool failures prevent an unverified build from being presented as compatible.
