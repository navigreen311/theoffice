"use client";

import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Badge, Button, Field, inputClass } from "@/components/ui";
import { RUBBER_STAMP_SECONDS } from "@/lib/severity";

import { decideAction } from "./actions";

function Submit({ label, decision }: { label: string; decision: string }) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      name="decision"
      value={decision}
      variant={decision === "approve" ? "default" : "danger"}
      disabled={pending}
    >
      {pending ? "Recording…" : label}
    </Button>
  );
}

export function DecideForm({ proposalId }: { proposalId: string }) {
  const [state, action] = useFormState(decideAction, null);
  const [seconds, setSeconds] = useState(0);

  // A visible timer, not a disabled button. Blocking the control for five seconds
  // trains people to wait five seconds; showing the number they are about to be
  // measured against gives them a reason to read. The API measures it either way,
  // from created_at in the database, so this cannot be gamed by the client.
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const tooFast = seconds < RUBBER_STAMP_SECONDS;

  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="proposal_id" value={proposalId} />

      <Field label="Decision reason" hint="Required to reject. Recorded either way.">
        <textarea className={inputClass} name="reason" rows={2} />
      </Field>

      <div className="flex flex-wrap items-center gap-3">
        <Submit label="Approve" decision="approve" />
        <Submit label="Reject" decision="reject" />
        <span className={`text-xs ${tooFast ? "text-warn" : "text-neutral-500"}`}>
          {tooFast
            ? `${seconds}s on screen — approving now flags as a rubber stamp`
            : `${seconds}s on screen`}
        </span>
      </div>

      {state?.error ? (
        <p>
          <Badge severity="bad">{state.error}</Badge>
        </p>
      ) : null}
      {state?.ok ? (
        <p>
          <Badge severity="ok">{state.ok}</Badge>
        </p>
      ) : null}
    </form>
  );
}
