# S99 — Dashboard approvals for EXTERNAL tools + image guidance

Status: landed 2026-09-27. Server + UI + one error string; Colab
and training untouched.

## Forensics (user-tested Firefox session, 9 tool calls)

`capture_window title=Firefox` → ok (S98 substring fix, live);
`read_file window.png` → binary rejection; `inspect_image` →
denied `ASK requires confirmation but no confirmer` (the
predicted wall, now hit); `detect_blank_screen` → ok; then
`read_file window.png` ×5 identical → honest FAILED at
iteration 9 via the S98-wired ladder. No verifier ran (none
set). Root gap: the model cannot SEE images (binary rejected,
inspect denied) and nothing told it where images go.

## Changes

1. **Approve/deny seam**: per-session pending slot +
   `POST /api/session/<id>/confirm` (404 unknown, 409 nothing
   pending); loop confirmer blocks up to 300s then denies safely
   (today's behavior when nobody answers); UI buttons on the
   pending tool; `pending_confirmation` in summaries. EXTERNAL
   only — DESTRUCTIVE stays DENY by policy.
2. **Binary-read guidance**: rejection names `inspect_image`
   (needs approval) and `detect_blank_screen` — pivot on turn 2
   instead of retrying to termination.
3. Housekeeping: `window.png` (user's capture) removed,
   `*.png` ignored.

## Verification

- 6 new hermetic tests (approve executes, deny blocks, timeout
  denies, 404, 409, guidance text); suite 1727 OK (1721 + 6);
  pyflakes clean; npm build green.
- **Live proof:** real session (screenshot + describe, ep11-q4)
  pended `inspect_image`, approved via API, tool executed,
  session COMPLETED.
