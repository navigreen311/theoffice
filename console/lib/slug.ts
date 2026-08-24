/**
 * The slug a display name will produce.
 *
 * **A preview, not the decision.** `broker.ventures.slugify` is authoritative: the
 * server re-derives the slug from the name and validates it against the database's own
 * regex, so this agreeing is a convenience and this disagreeing is a cosmetic bug
 * rather than a wrong key. Kept in step by `slug.test.ts`, which uses the same cases as
 * the Python side.
 *
 * It lives here rather than in `ventures/actions.ts` because a `"use server"` module may
 * only export async functions - exporting this from there fails the build, which is how
 * it ended up in its own file.
 */
export function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
