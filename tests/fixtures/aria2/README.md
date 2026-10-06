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
