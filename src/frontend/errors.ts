/**
 * Two kinds of failure, kept apart so a bug is never reported as a problem with the file.
 *
 * RecordError (and its subclasses) means the uploaded file or its contents cannot be used.
 * Its message is written for the user and shown as is. Anything else thrown is a bug in
 * Death's Warrant: describeFailure() turns it into a message that says so and names where it
 * happened, and the full stack trace goes to the browser console.
 */

export const ISSUES_URL = "https://github.com/dylannajib/Deaths-Warrant/issues";

export class RecordError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name; // e.g. "XmlError", so the console shows which stage failed
  }
}

/** The first stack frame, e.g. "readFhir (fhir.ts:142:7)", or null when none is available. */
function whereThrown(e: Error): string | null {
  const frame = e.stack?.split("\n").find((line) => /\.(ts|tsx|js)(\?[^:)]*)?:\d+/.test(line));
  return frame ? frame.trim().replace(/^at /, "") : null;
}

/** The message shown to the user for any failure during a run. */
export function describeFailure(e: unknown): string {
  if (e instanceof RecordError) return e.message;
  const error = e instanceof Error ? e : new Error(String(e));
  console.error("Death's Warrant internal error:", error);
  const where = whereThrown(error);
  return (
    "Something went wrong inside Death's Warrant (a bug, not a problem with your file). " +
    `Please report it at ${ISSUES_URL} with this reference: ${error.name}: ${error.message}` +
    (where ? ` at ${where}` : "") +
    "."
  );
}
