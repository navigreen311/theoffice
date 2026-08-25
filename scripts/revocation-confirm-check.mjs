// Prove the kill switch asks twice, and asks harder at the wide scopes.
//
// The confirmation step is client state: it exists only once the operator asks to review,
// so the served HTML never contains it and a `grep` of the page asserts something that
// cannot be true. This drives the real form in a real browser.
//
// What it checks, in order:
//   1. selecting a scope shows only the fields that scope uses, not all four;
//   2. blast radius appears once a target is chosen, before anything is submitted;
//   3. the first control opens a review rather than revoking;
//   4. at venture scope the review will not proceed until the target name is typed.
//
// Usage: node revocation-confirm-check.mjs <base-url> <session-cookie>

const [base, cookie] = process.argv.slice(2);
const endpoint = `http://127.0.0.1:${process.env.CDP_PORT ?? "9222"}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const targets = await (await fetch(`${endpoint}/json/list`)).json();
const page = targets.find((t) => t.type === "page");
if (!page) {
  console.log("FAIL no browser page target");
  process.exit(2);
}

const ws = new WebSocket(page.webSocketDebuggerUrl);
let next = 0;
const pending = new Map();
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id !== undefined) {
    pending.get(d.id)?.(d);
    pending.delete(d.id);
  }
});
await new Promise((res, rej) => {
  ws.addEventListener("open", res);
  ws.addEventListener("error", rej);
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const id = ++next;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

for (const domain of ["Runtime", "Page", "Network"]) await send(`${domain}.enable`);
await send("Network.setCookie", {
  name: "office_session",
  value: cookie,
  domain: new URL(base).hostname,
  path: "/",
  httpOnly: true,
});

const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result?.result?.value;
};

await send("Page.navigate", { url: `${base}/revocations` });
await sleep(4000);

let failures = 0;
const check = (ok, good, bad) => {
  if (ok) console.log(good);
  else {
    console.log(`FAIL ${bad}`);
    failures += 1;
  }
};

// React does not react to a programmatic `.value =`; it listens for the input event on
// its own tracked setter. This is the standard way to drive a controlled input.
const SET_VALUE = `
  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }
`;

// 1. Only the fields the scope uses.
//
// Click and read are separate round trips with a wait between them. Doing both inside one
// `evaluate` reads the DOM before React has re-rendered, so every scope reports the
// fields of the one before it - which is how the first version of this check reported
// venture scope showing Agent, Forge and Module.
const pickScope = (label) => evaluate(`
  (() => {
    const button = [...document.querySelectorAll('button')]
      .find((b) => b.textContent.trim() === ${JSON.stringify(label)});
    if (!button) return false;
    button.click();
    return true;
  })()
`);

const visibleFields = () => evaluate(`
  [...new Set([...document.querySelectorAll('form span')]
    .map((s) => s.textContent.trim())
    .filter((t) => ['Agent', 'Forge', 'Module', 'Venture'].includes(t)))]
`);

const fieldsPerScope = {};
for (const label of ["One grant", "One agent", "A venture", "A whole Forge"]) {
  const clicked = await pickScope(label);
  if (!clicked) {
    check(false, "", `missing scope button ${label}`);
    continue;
  }
  await sleep(700);
  fieldsPerScope[label] = await visibleFields();
}

check(
  JSON.stringify(fieldsPerScope["A venture"]) === JSON.stringify(["Venture"]),
  "venture scope shows one field, not four",
  `venture scope showed ${JSON.stringify(fieldsPerScope["A venture"])}`,
);
check(
  (fieldsPerScope["One grant"] ?? []).length === 3,
  "one-grant scope shows its three fields",
  `one-grant scope showed ${JSON.stringify(fieldsPerScope["One grant"])}`,
);
check(
  JSON.stringify(fieldsPerScope["A whole Forge"]) === JSON.stringify(["Forge"]),
  "Forge scope shows one field",
  `Forge scope showed ${JSON.stringify(fieldsPerScope["A whole Forge"])}`,
);

// 2. Choose a venture, and expect a blast radius before anything is submitted.
await pickScope("A venture");
await sleep(700);
const chose = await evaluate(`
  (() => {
    const option = [...document.querySelectorAll('form ul button')][0];
    if (!option) return 'no venture to choose';
    option.click();
    return 'chose ' + option.textContent.trim().slice(0, 40);
  })()
`);
// The radius is fetched from the server after the selection, so this waits for a round
// trip rather than for a render.
await sleep(3000);

if (typeof chose === "string" && chose.startsWith("no ")) {
  console.log(`NOT EXERCISED ${chose}`);
} else {
  const radius = await evaluate(
    `document.body.innerText.includes('What this stops')`,
  );
  check(
    radius,
    "blast radius is shown before the act",
    "no blast radius appeared after choosing a target",
  );

  const forward = await evaluate(
    `document.body.innerText.includes('after the revocation')`,
  );
  check(
    forward,
    "the forward-looking effect is stated",
    "a venture revocation does not say it blocks later grants",
  );

  // 3. The first control opens a review; it does not revoke.
  await evaluate(`
    ${SET_VALUE}
    (() => {
      const box = document.querySelector('textarea[name="reason"]');
      setValue(box, 'Smoke: verifying the confirmation step.');
      return true;
    })()
  `);
  await sleep(800);

  const opened = await evaluate(`
    (() => {
      const button = [...document.querySelectorAll('button')]
        .find((b) => b.textContent.trim().startsWith('Review and revoke'));
      if (!button) return 'no review control';
      if (button.disabled) return 'review control is disabled';
      button.click();
      return 'opened';
    })()
  `);
  await sleep(1200);

  check(opened === "opened", "the first control opens a review", `${opened}`);

  // 4. At venture scope the review will not proceed until the name is typed.
  const gated = await evaluate(`
    (() => {
      const text = document.body.innerText;
      if (!text.includes('to confirm')) return 'no typed confirmation is required';
      const revoke = [...document.querySelectorAll('button')]
        .find((b) => b.textContent.trim() === 'Revoke now');
      if (!revoke) return 'no revoke control in the review';
      return revoke.disabled ? 'gated' : 'ungated';
    })()
  `);
  check(
    gated === "gated",
    "a venture revocation will not proceed until the name is typed",
    `the typed confirmation is not enforced: ${gated}`,
  );

  // And typing the wrong name keeps it shut.
  const wrong = await evaluate(`
    ${SET_VALUE}
    (() => {
      const input = [...document.querySelectorAll('input')]
        .find((i) => i.closest('label')?.textContent.includes('to confirm'));
      if (!input) return 'no confirmation input';
      setValue(input, 'not-the-target');
      return 'typed';
    })()
  `);
  await sleep(600);
  if (wrong === "typed") {
    const stillShut = await evaluate(`
      (() => {
        const revoke = [...document.querySelectorAll('button')]
          .find((b) => b.textContent.trim() === 'Revoke now');
        return revoke ? revoke.disabled : null;
      })()
    `);
    check(
      stillShut === true,
      "the wrong name does not open it either",
      "a wrong confirmation name was accepted",
    );
  }
}

ws.close();
process.exit(failures > 0 ? 1 : 0);
