/**
 * Minimal, non-validating XML parser for FHIR XML and C-CDA uploads.
 *
 * Why not DOMParser: it is unavailable inside Web Workers (where parsing runs) and in Node
 * (where tests run). Owning the parser also lets us refuse whole attack classes outright:
 * any DOCTYPE or ENTITY declaration is rejected, so external entities (XXE) and entity
 * expansion ("billion laughs") cannot occur. Only the five predefined entities and numeric
 * character references are decoded. Parsing is iterative with depth and node caps, so hostile
 * nesting cannot overflow the stack.
 */

export interface XmlElement {
  /** Qualified name as written, e.g. "sdtc:raceCode". */
  name: string;
  /** Name without prefix. */
  local: string;
  /** Resolved namespace URI ("" if none). */
  ns: string;
  /** Attributes keyed by qualified name. */
  attrs: Record<string, string>;
  children: XmlElement[];
  /** Concatenated character data directly inside this element. */
  text: string;
}

export class XmlError extends Error {}

export const MAX_DEPTH = 256;
export const MAX_NODES = 5_000_000;

const PREDEFINED: Record<string, string> = { lt: "<", gt: ">", amp: "&", quot: '"', apos: "'" };
const NAME = /^[A-Za-z_][\w.\-:]*/;

export function decodeEntities(raw: string): string {
  if (!raw.includes("&")) return raw;
  return raw.replace(/&([^;&\s<]{0,10})(;?)/g, (whole, ref: string, semi: string) => {
    if (!semi) throw new XmlError("Bare '&' in text");
    if (Object.hasOwn(PREDEFINED, ref)) return PREDEFINED[ref]!;
    const code = /^#x[0-9a-f]+$/i.test(ref)
      ? parseInt(ref.slice(2), 16)
      : /^#\d+$/.test(ref)
        ? parseInt(ref.slice(1), 10)
        : NaN;
    if (!Number.isInteger(code) || code < 1 || code > 0x10ffff) {
      throw new XmlError(`Unsupported entity ${whole}`);
    }
    return String.fromCodePoint(code);
  });
}

function localOf(name: string): string {
  const i = name.indexOf(":");
  return i < 0 ? name : name.slice(i + 1);
}

function prefixOf(name: string): string {
  const i = name.indexOf(":");
  return i < 0 ? "" : name.slice(0, i);
}

export function parseXml(source: string): XmlElement {
  let pos = 0;
  let nodes = 0;
  let root: XmlElement | undefined;
  const stack: { el: XmlElement; scope: Map<string, string> }[] = [];

  const fail = (msg: string): never => {
    throw new XmlError(`${msg} (at character ${pos})`);
  };
  const skipPast = (token: string, what: string) => {
    const end = source.indexOf(token, pos);
    if (end < 0) fail(`Unterminated ${what}`);
    const body = source.slice(pos, end);
    pos = end + token.length;
    return body;
  };

  while (pos < source.length) {
    const lt = source.indexOf("<", pos);
    const textEnd = lt < 0 ? source.length : lt;
    if (textEnd > pos) {
      const text = source.slice(pos, textEnd);
      const top = stack.at(-1);
      if (top) top.el.text += decodeEntities(text);
      else if (text.trim()) fail("Text outside the root element");
      pos = textEnd;
      continue;
    }

    if (source.startsWith("<!--", pos)) {
      pos += 4;
      skipPast("-->", "comment");
    } else if (source.startsWith("<![CDATA[", pos)) {
      pos += 9;
      const data = skipPast("]]>", "CDATA section");
      const top = stack.at(-1) ?? fail("CDATA outside the root element");
      top.el.text += data;
    } else if (source.startsWith("<!", pos)) {
      // DOCTYPE, ENTITY, ELEMENT, ATTLIST... none are legitimate in FHIR or C-CDA uploads.
      fail("Document type and entity declarations are not allowed");
    } else if (source.startsWith("<?", pos)) {
      pos += 2;
      skipPast("?>", "processing instruction");
    } else if (source.startsWith("</", pos)) {
      pos += 2;
      const name = NAME.exec(source.slice(pos, pos + 256))?.[0] ?? fail("Bad closing tag");
      pos += name.length;
      while (/\s/.test(source[pos] ?? "")) pos++;
      if (source[pos] !== ">") fail("Bad closing tag");
      pos++;
      const open = stack.pop() ?? fail(`Unexpected </${name}>`);
      if (open.el.name !== name) fail(`Expected </${open.el.name}> but found </${name}>`);
    } else {
      pos++;
      const name = NAME.exec(source.slice(pos, pos + 256))?.[0] ?? fail("Bad tag name");
      pos += name.length;
      const attrs: Record<string, string> = Object.create(null);
      let selfClosing = false;
      for (;;) {
        while (/\s/.test(source[pos] ?? "")) pos++;
        const c = source[pos];
        if (c === undefined) fail("Unterminated tag");
        if (c === ">") { pos++; break; }
        if (c === "/" && source[pos + 1] === ">") { pos += 2; selfClosing = true; break; }
        const attr = NAME.exec(source.slice(pos, pos + 256))?.[0] ?? fail("Bad attribute");
        pos += attr.length;
        while (/\s/.test(source[pos] ?? "")) pos++;
        if (source[pos] !== "=") fail("Attribute without value");
        pos++;
        while (/\s/.test(source[pos] ?? "")) pos++;
        const quote = source[pos] === "'" ? "'" : source[pos] === '"' ? '"' : fail("Unquoted attribute value");
        pos++;
        const value = skipPast(quote, "attribute value");
        if (value.includes("<")) fail("'<' in attribute value");
        if (Object.hasOwn(attrs, attr)) fail(`Duplicate attribute ${attr}`);
        attrs[attr] = decodeEntities(value);
      }

      if (stack.length >= MAX_DEPTH) fail("Document is nested too deeply");
      if (++nodes > MAX_NODES) fail("Document has too many elements");
      const parentScope = stack.at(-1)?.scope ?? new Map<string, string>();
      let scope = parentScope;
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "xmlns" || k.startsWith("xmlns:")) {
          if (scope === parentScope) scope = new Map(parentScope);
          scope.set(k === "xmlns" ? "" : k.slice(6), v);
        }
      }
      const el: XmlElement = {
        name,
        local: localOf(name),
        ns: scope.get(prefixOf(name)) ?? "",
        attrs,
        children: [],
        text: "",
      };
      const parent = stack.at(-1);
      if (parent) parent.el.children.push(el);
      else if (root) fail("More than one root element");
      else root = el;
      if (!selfClosing) stack.push({ el, scope });
    }
  }
  if (stack.length) fail(`Unclosed <${stack.at(-1)!.el.name}>`);
  return root ?? fail("No root element");
}

/** Attribute by local name, ignoring any prefix (e.g. "xsi:type" via "type"). */
export function attr(el: XmlElement, local: string): string | undefined {
  if (local in el.attrs) return el.attrs[local];
  for (const [k, v] of Object.entries(el.attrs)) if (localOf(k) === local) return v;
  return undefined;
}

export function child(el: XmlElement, local: string): XmlElement | undefined {
  return el.children.find((c) => c.local === local);
}

export function children(el: XmlElement, local: string): XmlElement[] {
  return el.children.filter((c) => c.local === local);
}

/** All descendants with the given local name, depth-first, iteratively. */
export function descendants(el: XmlElement, local: string): XmlElement[] {
  const out: XmlElement[] = [];
  const todo = [...el.children].reverse();
  while (todo.length) {
    const next = todo.pop()!;
    if (next.local === local) out.push(next);
    for (let i = next.children.length - 1; i >= 0; i--) todo.push(next.children[i]!);
  }
  return out;
}
