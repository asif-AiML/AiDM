# aria2c 1.37.0 captures

Captured on Linux, 2026-10-06, from installed aria2c using a loopback-only HTTP
server: 1 MiB, sent in 16 KiB chunks at 50 ms intervals. No internet source.
Files contain unedited stdout including summary duplication and completion noise.
stderr was empty. Random transfer IDs, temporary paths and timestamps are inert
fixtures, not expected output names.

- `normal.txt`: existing `build_direct_command(url, destination)` unchanged.
- `unknown.txt`: no HTTP Content-Length. Readout/color/truncation flags below,
  but default human-readable units. `/0B` denotes unknown total, not an empty file.
- `exact.txt`: Content-Length 1048576, with a 1.2 second initial pause to capture
  zero progress. GUI telemetry flags:
  `--show-console-readout=true --enable-color=false`
  `--truncate-console-readout=false --human-readable=false`.

The last active snapshot can be less than 100% even on successful exit. Completion
summaries must not be interpreted as telemetry or used to manufacture 100%.

Extended GiB and hour/minute ETA unit tests use synthetic records following the
same version's source (not additional live captures):
[ConsoleStatCalc.cc](https://github.com/aria2/aria2/blob/release-1.37.0/src/ConsoleStatCalc.cc)
and `util::abbrevSize` / `util::secfmt` in
[util.cc](https://github.com/aria2/aria2/blob/release-1.37.0/src/util.cc).


## Milestone 18 parallel captures

`parallel.txt` and `parallel-unknown.txt` were captured from installed aria2c
1.37.0 on 2026-10-09 using a threaded loopback HTTP server. Three responses of
524288, 1048576 and 1572864 bytes were sent in 16384-byte chunks every 100 ms;
Content-Disposition supplied the resolved filenames. The unknown capture omits
Content-Length for the third response. Both commands exited 0; stderr was empty.
These are unedited stdout captures, including inert temporary paths and GIDs.

Command options: the existing direct flags, `--max-concurrent-downloads=3`,
`--input-file=<three loopback URLs>`, `--dir=<temporary output directory>`,
`--show-console-readout=true --enable-color=false`,
`--truncate-console-readout=false --human-readable=false`, and the GUI-only
`--console-log-level=notice` override. Initial warning-level captures proved
that live completion notices were suppressed; the notice-level captures above
supply the live completion evidence used by the parser.

Detailed summary records carry each GID's exact bytes, individual speed and FILE
path. The blank line closes a full active snapshot. Notice completion paths match
those FILE paths while other GIDs continue. Compact aggregate DL values retain
some completed-transfer speed and are deliberately ignored. Final OK result rows
supply explicit GIDs; reaching 100% or disappearing is not proof of success.

`serve_bulk.py` is a reusable local manual fixture with throttling, HEAD and Range
support for Retry. It serves 4–6 direct URLs, resolved runtime names, an optional
unknown-length response and 404 failures. Run:

```bash
python3 tests/fixtures/aria2/serve_bulk.py
```

Follow the Milestone 18 manual steps in `docs/gui-master-plan.md`. This script
binds only 127.0.0.1:8765 and does not access internet sources or source files.
