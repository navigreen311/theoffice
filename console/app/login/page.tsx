import { Button, Card, Field, inputClass } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function LoginPage({
  searchParams,
}: {
  searchParams: { error?: string };
}) {
  return (
    <div className="mx-auto max-w-md">
      <Card
        title="Sign in"
        subtitle="Your token is verified against the API and stored in an httpOnly cookie. It is never readable from JavaScript."
      >
        {searchParams.error ? (
          <p className="mb-3 rounded border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            That token was not accepted.
          </p>
        ) : null}
        <form method="post" action="/api/session" className="space-y-3">
          <Field
            label="Operator token"
            hint="Issued by broker.humans.create_human. Returned once and never stored in plaintext."
          >
            <input
              className={inputClass}
              type="password"
              name="token"
              autoComplete="off"
              required
            />
          </Field>
          <Button type="submit">Sign in</Button>
        </form>
      </Card>
      <form method="post" action="/api/session?_method=DELETE" className="mt-4">
        <p className="text-xs text-neutral-500">
          Signing in again replaces the current session.
        </p>
      </form>
    </div>
  );
}
