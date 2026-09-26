# Stream Inspector → AiDM Handoff Contract

## Purpose

This document defines the AiDM-side contract for consuming output produced by the AIDM Stream Inspector browser extension.

The goal is to make later streaming implementation in AiDM frictionless. AiDM should not need to rediscover how the extension formats its output, why shell quoting is necessary, how a future GUI should parse the same payload, or how the parsed data should reach yt-dlp.

The same extension output must support both:

1. the current terminal workflow; and
2. a future AiDM GUI with a paste/input field.

The handoff is intentionally textual and human-inspectable during beta, but AiDM must treat it as structured command-line arguments after parsing.

---

## High-level architecture

The extension discovers browser-side playback information that AiDM cannot reliably reconstruct on its own:

- the user-selected media candidate;
- canonical playback title;
- User-Agent when observed;
- Referer when observed;
- selected real subtitle URL(s), when present;
- other approved session/context fields that may be added to the handoff contract later.

The extension then copies a **single-line, shell-safe argument fragment**.

Example shape:

```text
--user-agent 'Mozilla/5.0 ...' --referer 'https://example.com/' --subtitle 'https://cdn.example.com/sub.vtt' --title 'Example Movie' 'https://cdn.example.com/master.m3u8?token=...'
```

The fragment deliberately does **not** include `python aidm.py`.

This allows the same payload to be used in two ways.

### Terminal path

```text
Browser Extension
    ↓
clipboard argument fragment
    ↓
python aidm.py [PASTE]
    ↓
OS shell parses shell quoting
    ↓
sys.argv
    ↓
argparse in aidm.py
    ↓
AiDM streaming route
    ↓
yt-dlp
```

### Future GUI path

```text
Browser Extension
    ↓
clipboard argument fragment
    ↓
paste into AiDM GUI input box
    ↓
Python shlex.split(...)
    ↓
same argv-style list
    ↓
same AiDM argument parser / routing layer
    ↓
AiDM streaming route
    ↓
yt-dlp
```

The GUI must **not** execute the pasted text through a shell.

The GUI should convert the pasted string to an argv-style list using Python parsing compatible with the extension's POSIX shell quoting, for example:

```python
import shlex

argv = shlex.split(pasted_text)
```

That argv list should then be fed into the same AiDM parser/routing logic used by the CLI.

Do not use:

```python
subprocess.run(pasted_text, shell=True)
```

The textual handoff is an input format, not a shell script.

---

## Core design rule: one parser, two front ends

AiDM should avoid maintaining separate parsing semantics for terminal and GUI use.

The preferred structure is:

```text
CLI shell → argv ───────┐
                       ├→ shared AiDM argument parser → shared routing
GUI text → shlex.split ┘
```

A practical refactor is to make the parser reusable rather than constructing and consuming it only inside `main()`.

For example, future structure may resemble:

```python
def build_parser() -> argparse.ArgumentParser:
    ...

def parse_args(argv: list[str] | None = None):
    return build_parser().parse_args(argv)

def run_from_args(args) -> int:
    ...

def main() -> int:
    args = parse_args()
    return run_from_args(args)
```

Then a GUI can use:

```python
argv = shlex.split(pasted_text)
args = parse_args(argv)
return run_from_args(args)
```

Exact function names are not locked by this document. The architectural requirement is that CLI and GUI converge on the same parser and downstream routing logic.

---

## Clipboard contract

The extension handoff should remain a **single-line argument fragment**.

The planned ordering is:

1. `--user-agent`
2. browser/cookie-session option, if the final extension contract later includes one
3. `--referer`
4. zero or more `--subtitle` options
5. `--title`
6. selected media URL as the final positional argument

Illustrative example:

```text
--user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --subtitle 'https://cdn.example/subs/en.vtt?token=abc&x=1' --title 'John'"'"'s Movie' 'https://cdn.example/master.m3u8?token=abc&expires=123'
```

The ordering is intended to keep exported text predictable and easy to inspect. AiDM should still use `argparse` rather than depending on manual positional scanning.

---

## Shell escaping contract

Every arbitrary string emitted by the extension must be POSIX-shell safe.

This matters because titles, signed URLs, Referers, and User-Agent strings can contain characters that have shell meaning.

Examples include:

```text
&
?
=
$
"
'
;
(
)
spaces
```

A URL such as:

```text
https://example.com/master.m3u8?token=abc&expires=123
```

cannot safely be pasted unquoted into a shell because `&` is a shell control operator.

Titles can also contain apostrophes:

```text
John's Movie
```

A correct POSIX-safe representation can look like:

```text
'John'"'"'s Movie'
```

The extension is responsible for producing correct quoting.

AiDM's terminal path receives the already-decoded values through `sys.argv`; AiDM should not try to strip shell quote characters manually.

The future GUI path should use `shlex.split()` so the same quoting grammar is decoded into the same argv values.

---

## Required AiDM arguments

AiDM's parser needs to support the extension handoff fields.

### Positional media URL

The selected media candidate is the final positional URL.

Example:

```text
'https://cdn.example/master.m3u8?...'
```

This URL is authoritative for the handoff. AiDM must not silently replace it with another candidate.

The user may deliberately override the extension's engine-recommended candidate before copying.

### `--user-agent`

Optional.

Example:

```text
--user-agent 'Mozilla/5.0 ...'
```

AiDM should preserve the value exactly after argument parsing and pass it to the streaming downloader.

### `--referer`

Optional.

Example:

```text
--referer 'https://player.example/'
```

AiDM should preserve the value and pass it to the streaming downloader.

### `--subtitle`

Optional and repeatable.

Examples:

```text
--subtitle 'https://cdn.example/en.vtt'
```

or:

```text
--subtitle 'https://cdn.example/en.vtt' --subtitle 'https://cdn.example/ur.vtt'
```

The parser should collect subtitles into a list.

A natural argparse shape is:

```python
parser.add_argument(
    "--subtitle",
    action="append",
    default=[],
)
```

No subtitle is a normal case. The absence of `--subtitle` must not be treated as an error.

### `--title`

Optional from the parser's perspective, but expected in the normal extension workflow when canonical title discovery succeeded.

Example:

```text
--title 'Example Movie'
```

If present, AiDM owns filename sanitization and output naming.

The extension supplies the human-readable title. AiDM decides the safe filesystem basename.

### Browser/cookie-session option

The browser/cookie identity contract is intentionally **not finalized yet** on the extension side.

AiDM should leave room for a future explicit option such as a browser-session/cookies source, but should not invent or infer one from User-Agent or cookie-presence information.

In particular:

- raw cookie values should not be expected in the clipboard contract;
- AiDM should not guess Firefox/Brave/Chromium from User-Agent text;
- the presence of a Cookie header in browser traffic is not equivalent to a valid `--cookies-from-browser` source.

When that extension-side contract is finalized, this document should be updated with the exact AiDM option.

---

## Fields intentionally excluded from the core handoff

### Origin

The extension may retain Origin as diagnostic information, but the beta clipboard contract excludes it.

AiDM should therefore not require Origin for normal extension-driven streaming input.

If future provider evidence proves Origin necessary, it can be added deliberately as another optional argument.

### Raw cookies

Raw cookie values should not be copied into the handoff.

Cookie/session integration should use an explicit, safer browser-session strategy once the contract is finalized.

---

## AiDM routing responsibilities

The extension does detection and selection.

AiDM does downloading and output management.

Once `aidm.py` receives the parsed arguments, it should construct the internal streaming request and route it to the appropriate downloader path.

The intended flow is:

```text
parsed extension arguments
    ↓
aidm.py gate / router
    ↓
build stream input/context
    ↓
detect or honor stream type as required
    ↓
stream downloader
    ↓
yt-dlp
    ↓
FFmpeg only when yt-dlp requires it for normal media processing
```

For extension-driven HLS/DASH playback, yt-dlp remains the actual streaming engine.

AiDM should pass the selected media URL unchanged.

---

## Mapping extension data to yt-dlp

The final command should be built as an **argument list**, never by concatenating a shell command string.

Conceptually:

```python
command = [
    "yt-dlp",
    ...
]
```

### User-Agent

Map the parsed User-Agent to yt-dlp in a way that preserves the value.

AiDM may use yt-dlp's supported header mechanisms. The existing downloader already has a generic `--add-header` path, so the implementation can remain consistent with that architecture.

Conceptually:

```text
User-Agent: <captured value>
```

### Referer

Pass Referer to yt-dlp as request context.

Conceptually:

```text
Referer: <captured value>
```

The provider tests that motivated the extension showed that Referer can materially affect whether a captured stream request succeeds, so this field must not be discarded.

### Selected media candidate

The selected HLS/DASH URL becomes the actual media URL given to yt-dlp.

AiDM must not rerank or second-guess the browser extension selection.

### Title

The title controls the output basename after sanitization.

Existing AiDM behavior already uses `sanitize_filename()` and yt-dlp output templates. Extension-driven streaming should continue that ownership model.

### Subtitle URLs

Selected subtitle URLs are independent downloadable resources.

Do not assume that yt-dlp will discover these subtitles from the media manifest or webpage.

They came from browser-side observation and must be handled explicitly.

---

## Subtitle download responsibilities

Subtitles are optional.

The valid cases are:

### Case A: media + one subtitle

Input:

```text
--subtitle '<subtitle-url>' --title 'Movie Name' '<media-url>'
```

Expected outputs should share the sanitized title basename:

```text
Movie Name.<media-extension>
Movie Name.<subtitle-extension>
```

If language metadata is later available and multiple subtitles need distinct names, the naming contract can be expanded without changing the parser architecture.

### Case B: media + multiple subtitles

AiDM should accept repeated `--subtitle` values.

The exact collision/language naming strategy can be implemented when multiple-subtitle support is wired, but AiDM must not overwrite files silently.

Possible future output shapes include:

```text
Movie Name.en.vtt
Movie Name.ur.vtt
```

or deterministic numbered sidecars when language information is unavailable:

```text
Movie Name.subtitle-1.vtt
Movie Name.subtitle-2.vtt
```

What matters for the handoff layer is that repeated subtitle arguments survive parsing intact.

### Case C: media with no subtitle

This is completely normal.

Input:

```text
--title 'Movie Name' '<media-url>'
```

AiDM must:

- download the main media;
- name the media from the sanitized title;
- skip subtitle handling cleanly;
- produce no missing-subtitle error;
- not attempt to fabricate or discover a subtitle merely because the extension handoff supports subtitles.

In this case the result is simply:

```text
Movie Name.<media-extension>
```

---

## Subtitle engine expectations

The existing AiDM architecture already separates direct-file downloading from HLS/DASH media downloading.

For browser-observed direct subtitle resources, the preferred long-term behavior is:

- direct HTTP subtitle resource → aria2c where appropriate;
- main HLS/DASH media → yt-dlp native HLS/DASH handling;
- FFmpeg only where normal downstream processing requires it.

Subtitle resources should receive the relevant request context needed to reproduce the browser request, especially User-Agent and Referer when supplied.

The main media and subtitle downloads should use the same canonical sanitized title basename.

AiDM should not re-encode the main media merely to add subtitles.

The default beta behavior should favor sidecar subtitle files.

Optional stream-copy muxing can remain a separate later feature.

---

## Filename ownership

The extension must not decide filesystem-safe filenames.

It supplies the canonical human-readable title.

AiDM owns:

- filename sanitization;
- output-template construction;
- collision handling;
- media/subtitle basename consistency.

Use the existing `sanitize_filename()` utility as the starting point.

Example:

```text
Extension title:
John's Movie: Part 1

AiDM safe basename:
John's Movie_ Part 1
```

The exact extension of the main media remains determined by the actual downloaded/remuxed output.

Subtitle extension should follow the actual subtitle format/resource rather than being forced to match the media extension.

---

## Parsing should happen before routing

Do not send a raw clipboard string down into `downloader.py`.

The raw text should be decoded at the application boundary.

Correct model:

```text
raw GUI text
    ↓
shlex.split
    ↓
argparse
    ↓
typed/normalized AiDM values
    ↓
routing
    ↓
downloader
```

For terminal use, the shell performs the first decoding step before Python starts, so `argparse` receives equivalent values.

This keeps downloader functions independent of shell syntax.

---

## Recommended internal representation

AiDM may eventually benefit from a dedicated structure for extension-driven streaming arguments.

For example:

```python
@dataclass
class StreamInput:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    stream_type: str | None = None
    title: str | None = None
    subtitles: list[str] = field(default_factory=list)
```

This is illustrative, not a mandatory exact shape.

The important point is to normalize CLI/GUI input once and pass structured values internally rather than repeatedly parsing strings.

The existing `StreamInput` already provides a natural place to evolve this design.

---

## Backward compatibility

AiDM currently accepts plain URLs, including naked stream URLs.

Milestone 0A retires the older Stream Detector form
`URL|User-Agent=...&Referer=...`. Input is no longer split or decoded into headers.
`StreamInput` and downloader header support remain available for the future
argument-based handoff, which is not implemented yet.

The new argument-based contract is preferable because:

- shell quoting is explicit and standard;
- optional fields are unambiguous;
- repeatable subtitles are natural;
- GUI parsing can reuse `shlex.split`;
- future fields can be added without inventing another custom delimiter grammar.

---

## Error handling requirements

AiDM should fail at the correct boundary and with useful messages.

Examples:

### Invalid shell-like text in future GUI

If `shlex.split()` fails because pasted text has malformed quoting, the GUI should report that the pasted Stream Inspector input is malformed.

Do not execute or partially interpret it.

### Missing media URL

If options are present but the final positional media URL is missing, argparse should reject the input normally.

### Unsupported URL scheme

Keep the existing HTTP/HTTPS validation unless a future feature explicitly extends it.

### Missing optional headers

Do not fail because User-Agent or Referer is absent.

Only pass fields that were actually supplied.

### Missing subtitles

Never an error.

### Subtitle download failure

A subtitle failure should be reported separately from the main media result.

Implementation policy should avoid deleting or invalidating a successfully downloaded main media file merely because an optional subtitle failed.

### Main media failure

Return failure normally even if a subtitle happened to download successfully.

---

## Security rule: never re-shell the parsed input

Once the terminal shell or `shlex.split()` has produced argv values, AiDM must keep them as data.

Commands to yt-dlp, aria2c, and FFmpeg should be passed as Python lists.

Use the existing pattern:

```python
subprocess.run(command)
```

Do not use:

```python
subprocess.run(command_string, shell=True)
```

This is important because extension-derived values can contain arbitrary punctuation from page titles and signed URLs.

Shell-safe clipboard quoting protects terminal paste.

Argument-list subprocess execution protects AiDM after parsing.

They solve different boundaries and both are required.

---

## Current unified AiDM baseline

As of **2026-09-25**, the Stream Inspector work no longer sits on an isolated streaming-only router.

The feature branches were deliberately reconciled into:

```text
integration/aidm-unified-router
```

This branch is now the development baseline for the AiDM-side Stream Inspector handoff.

### `aidm.py`

The unified gate now uses one multi-value positional:

```python
parser.add_argument(
    "urls",
    nargs="+",
    ...
)
```

The router already preserves these working input families:

- single YouTube video;
- YouTube playlist;
- multiple YouTube URLs;
- single direct URL;
- multiple direct URLs with Sequential/Parallel modes;
- local `.torrent` files;
- naked HLS/DASH URLs;
- generic yt-dlp fallback;
- unsupported mixed-bulk rejection.

The old streaming-only single positional `url` architecture is historical and must not be reintroduced.

The Stream Inspector parser work must extend this unified gate rather than replace it.

For an Inspector handoff, the parser may still receive exactly one selected media URL, but that is a **route-level validation rule**, not a reason to collapse the whole AiDM CLI back to one positional URL.

### `stream_parser.py`

Current `StreamInput` contains:

```python
url
headers
stream_type
```

`parse_stream_input()` now wraps a plain URL only.

The retired legacy form:

```text
URL|User-Agent=...&Referer=...
```

is no longer parsed.

The `headers` field remains intentionally available because the future argument-based Stream Inspector handoff will populate it.

### `downloader.py`

The unified downloader contains the accumulated direct, bulk-direct, torrent, generic yt-dlp, and stream paths.

For streaming specifically, it already supports:

- list-based subprocess execution;
- yt-dlp native HLS/DASH handling;
- header propagation through `--add-header`;
- optional title input;
- filename sanitization through `sanitize_filename()`;
- natural yt-dlp naming when no explicit title is supplied.

The old interactive movie/video title prompt has been removed.

A naked stream URL therefore remains a first-class feature:

```text
naked stream URL
→ try normally
→ if it works, finish normally
→ if browser context is required, use Stream Inspector
```

### `utils.py`

The unified baseline contains:

- `run_command(command: list[str])`;
- `sanitize_filename()`.

Command execution remains list-based. The Stream Inspector work must not introduce `shell=True`.

---

## Integration history note — unified router baseline

This handoff work originally began while routing intelligence was distributed across separate feature branches.

Before implementing the new Inspector argument contract, the project deliberately stopped and unified those branches first.

The integration history was:

```text
main
  ↓
integration/aidm-unified-router
  ↓
feat/2ndry-features
  ↓
feat/youtube
  ↓
cleaned feat/Streaming-URLs
```

`feat/bulk-direct-downloads` was already contained in `main`, so it did not need to be merged again.

The important engineering rule during integration was:

> merge capabilities, not whole-file ownership.

The YouTube merge produced a serious `aidm.py` conflict because both branches had evolved the central router. That conflict was resolved by combining the direct/bulk/torrent routing with YouTube bulk, playlist detection, URL normalization, and the list-based YouTube API.

After that reconciliation, **nine routing tests passed**, including direct, bulk-direct, torrent, YouTube single, YouTube bulk, YouTube playlist, naked streaming, generic fallback, and mixed-bulk/error behavior. Logs were inspected to confirm that success did not come from accidental misclassification.

The later merge of `feat/Streaming-URLs` was treated as another high-risk semantic merge. The already-proven unified router was preserved while the cleaned streaming architecture contributed:

- removal of legacy pipe-delimited Stream Detector parsing;
- removal of manual movie-name prompts;
- optional title handling;
- header plumbing;
- filename sanitization;
- preservation of naked HLS/DASH support;
- the Stream Inspector handoff contract documentation.

After that merge, the same **nine-route regression suite passed again**, with routing logs inspected for classification correctness.

That repeated green regression established `integration/aidm-unified-router` as the new baseline for Milestone 1 and later Stream Inspector work.

The original feature branches remain valuable historical/reference implementations and are not treated as disposable after integration.

---

## Suggested implementation phases in AiDM

### Phase 1 — parser contract

Add the new optional handoff arguments without changing downloader behavior yet:

```text
--user-agent
--referer
--subtitle   (repeatable)
--title
```

Preserve the unified AiDM positional model:

```text
urls    (nargs="+")
```

A normal Stream Inspector handoff supplies one selected media URL inside that broader positional model. Inspector-specific validation may require exactly one media URL when handoff options are present, but the global CLI must remain compatible with YouTube bulk and direct bulk input.

Refactor parser creation so a future GUI can call the same parser with an explicit argv list.

### Phase 2 — normalize into streaming context

Convert parsed options into AiDM's internal stream representation.

Do not keep re-reading raw argparse fields throughout downloader code.

### Phase 3 — media route

Pass:

- selected URL;
- title;
- User-Agent;
- Referer

to the current yt-dlp streaming path.

Make supplied title bypass the interactive title prompt.

### Phase 4 — subtitle sidecars

Wire zero/one/multiple `--subtitle` URLs.

No subtitle must remain a clean no-op.

Use the canonical sanitized title basename.

### Phase 5 — GUI-compatible entry point

When AiDM gets a GUI, the input box should:

1. read pasted extension text;
2. run `shlex.split()`;
3. feed the resulting argv list to the shared parser;
4. call the same router used by the terminal.

No second grammar and no shell execution.

### Phase 6 — browser-session/cookie strategy

Implement only after the extension contract explicitly defines what browser/session identifier it will emit.

Do not guess.

---

## End-to-end target examples

### Example 1 — media only

Extension copies:

```text
--user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --title 'Example Movie' 'https://cdn.example/master.m3u8?token=abc&expires=123'
```

Terminal:

```bash
python aidm.py --user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --title 'Example Movie' 'https://cdn.example/master.m3u8?token=abc&expires=123'
```

Expected logical result:

```text
Example Movie.<media-extension>
```

No subtitle warning/error is required.

### Example 2 — media + subtitle

Extension copies:

```text
--user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --subtitle 'https://cdn.example/subtitle.vtt?token=xyz&expires=123' --title 'Example Movie' 'https://cdn.example/master.m3u8?token=abc&expires=123'
```

Expected logical outputs:

```text
Example Movie.<media-extension>
Example Movie.vtt
```

### Example 3 — title containing apostrophe

Extension copies a POSIX-safe fragment such as:

```text
--title 'John'"'"'s Movie' 'https://cdn.example/master.m3u8?token=abc&x=1'
```

Terminal shell decodes the title to:

```text
John's Movie
```

Future GUI:

```python
shlex.split(pasted_text)
```

must decode to the same value.

Both paths then feed identical arguments into AiDM.

---

## Non-goals of the handoff layer

The handoff parser should not:

- detect or rerank browser candidates;
- inspect the webpage;
- infer which subtitle the user wanted;
- infer browser identity from User-Agent;
- copy or reconstruct raw cookies;
- execute pasted text as a shell command;
- require subtitles;
- re-encode media merely to attach subtitles;
- create separate CLI and GUI grammars.

Those concerns belong elsewhere or are intentionally deferred.

---

## Contract summary

The long-term contract is:

```text
AIDM Stream Inspector
    ↓
one-line POSIX-shell-safe argument fragment
    ↓
┌─────────────────────────────┐
│ terminal                    │
│ OS shell → argv             │
├─────────────────────────────┤
│ future GUI                  │
│ shlex.split(text) → argv    │
└─────────────────────────────┘
    ↓
shared AiDM argparse parser
    ↓
shared aidm.py routing
    ↓
structured streaming context
    ↓
yt-dlp for main HLS/DASH media
+ direct subtitle downloader where appropriate
    ↓
AiDM-owned sanitized output naming
```

The extension chooses and describes the browser-observed resources.

AiDM parses, validates, routes, downloads, and names them.

The same copied payload should remain valid whether the user pastes it after `python aidm.py` today or into an AiDM GUI input box later.
