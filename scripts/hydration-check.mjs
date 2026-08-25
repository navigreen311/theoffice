// Load real pages in a real browser and fail if any of them breaks after arriving.
//
// Every other render check in this repository asks the server a question, and the server
// answers 200 to a page that is about to die in the browser. Three "Application error: a
// client-side exception has occurred" reports have now come in by hand for pages the
// smoke script called green, and each time the check that should have caught it was a
// `curl` returning 200:
//
//   - a React 19 API (`useActionState`, `<form action={async fn}>`) against the pinned
//     React 18.3.1: type-checks, builds, renders on the server, throws on hydration;
//   - `Date.now()` and `toLocaleString()` during SSR, where the server HTML and the
//     client render disagree and React discards the tree;
//   - a JS chunk answering 400 because `next build` rewrote `.next` under a running
//     `next start`, so the HTML referenced chunks the server no longer had.
//
// None of those is visible to a request that only reads the HTML. This opens the page,
// waits for hydration, and reports what the browser reports: uncaught exceptions,
// console errors, and any sub-resource that failed to load.
//
// Usage: node hydration-check.mjs <base-url> <session-cookie> <path> [<path> ...]

const [base, cookie, ...given] = process.argv.slice(2);

// Accepted as `/agents`, `./agents` or `agents`. Callers on Git Bash must avoid a
// leading slash: any such argument is rewritten into a Windows path before it ever
// reaches this process, and `/` in particular strips to nothing and disappears.
const paths = given.map((p) => {
  const bare = p.replace(/^\./, "");
  return bare.startsWith("/") ? bare : `/${bare}`;
});
if (!base || !cookie || given.length === 0) {
  console.error("usage: hydration-check.mjs <base-url> <session-cookie> <path>...");
  process.exit(2);
}

// A sweep that quietly covers less than the caller meant is the failure this whole
// file exists to catch, so the caller states how many routes it expects and a
// mismatch is fatal rather than a shorter list of green lines.
const expected = Number(process.env.EXPECTED_ROUTES ?? 0);
if (expected && expected !== paths.length) {
  console.error(
    `FAIL expected ${expected} routes, received ${paths.length}: ` +
      "some were lost before reaching the browser",
  );
  process.exit(2);
}

const DEBUG_PORT = process.env.CDP_PORT ?? "9222";
const endpoint = `http://127.0.0.1:${DEBUG_PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Chrome accepts connections slightly after the port opens.
let targets = null;
for (let attempt = 0; attempt < 25 && targets === null; attempt += 1) {
  try {
    targets = await (await fetch(`${endpoint}/json/list`)).json();
  } catch {
    await sleep(400);
  }
}
if (targets === null) {
  console.error(`FAIL no browser answering CDP on ${endpoint}`);
  process.exit(2);
}

const page = targets.find((t) => t.type === "page");
if (!page) {
  console.error("FAIL the browser exposed no page target");
  process.exit(2);
}

const ws = new WebSocket(page.webSocketDebuggerUrl);
let next = 0;
const pending = new Map();
let events = [];

ws.addEventListener("message", (message) => {
  const data = JSON.parse(message.data);
  if (data.id !== undefined) {
    pending.get(data.id)?.(data);
    pending.delete(data.id);
  } else {
    events.push(data);
  }
});

await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve);
  ws.addEventListener("error", reject);
});

const send = (method, params = {}) =>
  new Promise((resolve) => {
    const id = ++next;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

for (const domain of ["Runtime", "Log", "Page", "Network"]) await send(`${domain}.enable`);

await send("Network.setCookie", {
  name: "office_session",
  value: cookie,
  domain: new URL(base).hostname,
  path: "/",
  httpOnly: true,
});

// Noise that says nothing about whether the page works. Kept deliberately short: a
// filter that grows is a filter that eventually hides the failure it was meant to skip.
const IGNORE = [/favicon\.ico/, /Download the React DevTools/];

let failures = 0;

for (const path of paths) {
  events = [];
  await send("Page.navigate", { url: `${base}${path}` });

  // Hydration is not done when the document loads. Poll for React having adopted the
  // tree, then give it a moment more, rather than sleeping a fixed guess.
  let ready = false;
  for (let attempt = 0; attempt < 30 && !ready; attempt += 1) {
    await sleep(200);
    const probe = await send("Runtime.evaluate", {
      expression: "document.readyState === 'complete'",
      returnByValue: true,
    });
    ready = probe.result?.result?.value === true;
  }
  await sleep(1200);

  const rendered = await send("Runtime.evaluate", {
    expression: "document.body ? document.body.innerText.slice(0, 300) : ''",
    returnByValue: true,
  });
  const text = rendered.result?.result?.value ?? "";

  const problems = [];
  for (const event of events) {
    if (event.method === "Runtime.exceptionThrown") {
      const detail = event.params.exceptionDetails;
      problems.push(
        `uncaught: ${(detail.exception?.description ?? detail.text ?? "").split("\n")[0]}`,
      );
    }
    if (
      event.method === "Runtime.consoleAPICalled" &&
      event.params.type === "error"
    ) {
      const args = event.params.args
        .map((a) => a.value ?? a.description ?? "")
        .join(" ")
        .split("\n")[0];
      if (args.trim()) problems.push(`console.error: ${args}`);
    }
    if (event.method === "Network.responseReceived") {
      const { status, url } = event.params.response;
      // A page's own 4xx is the server's business and other checks cover it. A
      // sub-resource that fails is what breaks hydration, and it is invisible in HTML.
      if (status >= 400 && !url.endsWith(path)) {
        problems.push(`asset ${status}: ${url.replace(base, "")}`);
      }
    }
  }

  const kept = [...new Set(problems)].filter(
    (problem) => !IGNORE.some((pattern) => pattern.test(problem)),
  );
  const errored = /client-side exception|Application error/i.test(text);
  const blank = text.trim().length === 0;

  if (errored || blank || kept.length > 0) {
    failures += 1;
    const why = errored
      ? "rendered Next's client-side exception page"
      : blank
        ? "rendered nothing at all"
        : "reported errors after loading";
    console.log(`FAIL ${path} ${why}`);
    for (const problem of kept.slice(0, 6)) console.log(`       ${problem.slice(0, 220)}`);
  } else {
    console.log(`${path} hydrated cleanly`);
  }
}

ws.close();
process.exit(failures > 0 ? 1 : 0);
