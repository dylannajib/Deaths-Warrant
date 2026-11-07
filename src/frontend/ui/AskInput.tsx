/** Asks the user for a required input the record lacks, e.g. "Enter age:". */

import { useId, useState, type FormEvent } from "react";
import type { Input, Value } from "../engine/spec";
import { formatValue, lowerFirst } from "./format";

interface Props {
  input: Input;
  disabled: boolean;
  onSubmit: (value: Value) => void;
}

function Chevron({ up }: { up: boolean }) {
  return (
    <svg viewBox="0 0 10 6" width="10" height="6">
      <path d={up ? "M1 5 5 1 9 5" : "M1 1 5 5 9 1"} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function AskInput({ input, disabled, onSubmit }: Props) {
  const [text, setText] = useState("");
  const id = useId();
  // The browser checks required, min and max before this runs, so the value is in range.
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (input.type === "number") onSubmit(Number(text));
    else if (input.type === "boolean") onSubmit(text === "true");
    else onSubmit(text);
  };
  const options = input.type === "enum" ? input.values : ["true", "false"];
  // Our own up and down buttons: the browser's spinner cannot be recoloured.
  const step = (by: number) => {
    if (input.type !== "number") return;
    const next = (text === "" ? input.min : Number(text)) + (text === "" ? 0 : by);
    setText(String(Math.min(Math.max(next, input.min), input.max)));
  };
  return (
    <form className="ask" onSubmit={submit}>
      <label htmlFor={id}>Enter {lowerFirst(input.label)}:</label>
      {input.type === "number" ? (
        <span className="number">
          <input id={id} type="number" required step="any" min={input.min} max={input.max} value={text} onChange={(e) => setText(e.target.value)} />
          {/* Hidden from screen readers and the tab order: the arrow keys do the same. */}
          <span className="steps" aria-hidden="true">
            <button type="button" tabIndex={-1} onClick={() => step(1)}>
              <Chevron up />
            </button>
            <button type="button" tabIndex={-1} onClick={() => step(-1)}>
              <Chevron up={false} />
            </button>
          </span>
        </span>
      ) : (
        <select id={id} required value={text} onChange={(e) => setText(e.target.value)}>
          <option value="" disabled>
            Choose
          </option>
          {options.map((o) => (
            <option key={o} value={o}>
              {input.type === "boolean" ? formatValue(o === "true") : formatValue(o)}
            </option>
          ))}
        </select>
      )}
      {input.type === "number" && input.unit && <span>{input.unit}</span>}
      <button type="submit" disabled={disabled}>
        Continue
      </button>
    </form>
  );
}
