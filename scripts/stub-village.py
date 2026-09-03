"""A Village that answers one question, for the smoke script.

WHY THIS EXISTS

    V29 and V30 read the department list from the Village over HTTP. `broker/departments`
    holds no fallback copy on purpose - when nothing has seeded and the Village cannot be
    reached, the answer is None and the rules report NOT_RUN, which is the honest state.

    In the smoke environment nothing could be reached, so Gate 2 blocked on every run:

        run ea4e3e9e stopped at gate 2 (blocked)
          rule(s) ['V29', 'V30'] did not run. NOT_RUN is not a pass.

    Seven checks below the ladder assume the run reaches gate 4 and the review form
    renders. They had never once run, because a TypeError two steps earlier was aborting
    the script before it got there; when that was fixed they failed against a page that
    was working and had nothing to draw.

WHY A STUB SERVER RATHER THAN `departments.seed()`

    `seed()` installs a list in the calling process. The API runs in a different one, so
    seeding from this script would leave the server's own view empty.

    It is also the wrong shape for a smoke test. The point of this script is that the
    real path runs: the fetch, the parse, the cache, the degrade-on-error branch. A
    seeded in-process list skips all of it and would pass on a build where the HTTP
    client was broken.

WHAT IT SERVES

    `scripts/fixtures/village-departments.json`, unmodified, at the one path
    `broker/village.departments()` asks for. The same file `tests/world.py` reads, so the
    stub and the suite cannot drift - and if the Village's real shape changes, one file
    is wrong rather than two places quietly disagreeing.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts" / "fixtures" / "village-departments.json"

#: The only path this answers. Anything else is a 404, because a stub that answers
#: everything hides the difference between "The Office asked for this" and "The Office
#: asked for something nobody has implemented".
PATH = "/api/org/departments"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != PATH:
            self.send_error(404, f"stub Village serves only {PATH}")
            return
        body = FIXTURE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Quiet. The smoke script's output is the record, not this."""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    count = len(payload["departments"])
    print(f"stub Village on {port}: {count} departments from {FIXTURE.name}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
