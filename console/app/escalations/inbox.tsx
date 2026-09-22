"use client";

import { useFormState, useFormStatus } from "react-dom";

import { Ago } from "@/components/local-time";
import type { RoutedEscalation } from "@/lib/api";

import { answerAction, receiveAction, type EscalationState } from "./actions";

/**
 * The two acts, on the `/proposals` pattern.
 *
 * **Receipt and answer are separate buttons because they are separate facts.** A single
 * "answer" that also recorded receipt would collapse the gap between them, and that gap
 * is the number a drill exists to produce: an escalation raised at nine and picked up at
 * four is a path that works badly, and one picked up and answered in the same second is
 * a path nobody can tell from a function call (decisions entry 149).
 *
 * Neither form carries who acted. The session does.
 */

function Submitting({ label, busy }: { label: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className="act">
      {pending ? busy : label}
    </button>
  );
}

function Said({ state }: { state: EscalationState | null }) {
  if (!state) return null;
  if (state.error) return <p className="failing">{state.error}</p>;
  if (state.ok) return <p className="ok">{state.ok}</p>;
  return null;
}

/** Who raised it, and in what capacity. An agent and a person are not the same news. */
function Raiser({ item }: { item: RoutedEscalation }) {
  return (
    <span>
      {item.raised_by}{" "}
      <span className="muted">
        ({item.raised_by_kind === "agent" ? "an agent" : "a person"})
      </span>
    </span>
  );
}

export function Waiting({ item }: { item: RoutedEscalation }) {
  const [state, action] = useFormState(receiveAction, null);
  return (
    <article className="card">
      <header>
        <h3>
          {item.department ?? item.venture_id}: {item.kind}
        </h3>
        <p className="muted">
          Raised <Ago iso={item.raised_at} /> by <Raiser item={item} />, on the{" "}
          {item.path} path.
        </p>
      </header>

      {/* WHAT IT ASKS, in the raiser's own words and not summarised. An escalation
          whose text a reader cannot see is a notification. */}
      <blockquote>{item.reason}</blockquote>

      <p className="muted">
        Recording receipt says you have this. It does not answer it, and it is the step
        that tells a later reader the path reached a person.
      </p>
      <form action={action}>
        <input type="hidden" name="escalation_id" value={item.escalation_id} />
        <Submitting label="I have this" busy="Recording…" />
      </form>
      <Said state={state} />
    </article>
  );
}

export function Received({ item }: { item: RoutedEscalation }) {
  const [state, action] = useFormState(answerAction, null);
  return (
    <article className="card">
      <header>
        <h3>
          {item.department ?? item.venture_id}: {item.kind}
        </h3>
        <p className="muted">
          Raised <Ago iso={item.raised_at} /> by <Raiser item={item} />, received{" "}
          <Ago iso={item.received_at ?? item.raised_at} />.
        </p>
      </header>

      <blockquote>{item.reason}</blockquote>

      <form action={action}>
        <input type="hidden" name="escalation_id" value={item.escalation_id} />
        <label htmlFor={`answer-${item.escalation_id}`}>
          Your answer. It is recorded in your words and read by whoever raised this.
        </label>
        <textarea
          id={`answer-${item.escalation_id}`}
          name="answer"
          rows={4}
          required
        />
        <Submitting label="Answer" busy="Recording…" />
      </form>
      <Said state={state} />
    </article>
  );
}

export function Answered({ items }: { items: RoutedEscalation[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h2>Answered</h2>
      <table>
        <thead>
          <tr>
            <th>Raised</th>
            <th>Department</th>
            <th>Asked</th>
            <th>Answered</th>
            <th>Your answer</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.escalation_id}>
              <td>
                <Ago iso={item.raised_at} />
              </td>
              <td>{item.department ?? "the venture"}</td>
              <td>{item.reason}</td>
              <td>
                <Ago iso={item.answered_at ?? item.raised_at} />
              </td>
              <td>{item.answer}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
