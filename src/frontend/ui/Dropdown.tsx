/** A heading that slides its content open and closed. The heading itself never moves. */

import { useId, useState, type ReactNode } from "react";

export function Dropdown({ title, className = "", children }: { title: ReactNode; className?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={`dropdown ${className}`}>
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="arrow" aria-hidden="true">&gt;</span>
        {title}
      </button>
      <div id={id} className="dropdown-body" inert={!open}>
        <div>{children}</div>
      </div>
    </div>
  );
}
