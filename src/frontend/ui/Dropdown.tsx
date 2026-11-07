/** A heading that slides its content open and closed. The heading itself never moves. */

import { useId, useState, type ReactNode } from "react";

interface Props {
  title: ReactNode;
  /** Shown after the title, without the hover underline (e.g. a dataset's period). */
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Dropdown({ title, aside, className = "", children }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={`dropdown ${className}`}>
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="arrow" aria-hidden="true">&gt;</span>
        <span className="dropdown-title">{title}</span>
        {aside && <> {aside}</>}
      </button>
      <div id={id} className="dropdown-body" inert={!open}>
        <div>{children}</div>
      </div>
    </div>
  );
}
