import type { TextDocument } from "vscode-languageserver-textdocument";
import { classContainingLine, findWordAt, KW, type KvalModel } from "./model";

export type ResolvedKind = "class" | "function" | "global" | "method" | "field";

export interface ResolvedSymbol {
  kind: ResolvedKind;
  name: string;
  containerClass?: string;
}

function inNameRange(
  posLine: number,
  posChar: number,
  line: number,
  startChar: number,
  len: number
): boolean {
  return posLine === line && posChar >= startChar && posChar <= startChar + len;
}

function resolveMemberFromReceiver(
  model: KvalModel,
  lhs: string,
  word: string,
  posLine: number
): ResolvedSymbol | null {
  if (lhs === "this") {
    const cur = classContainingLine(model, posLine);
    if (!cur) return null;
    const mem = cur.members.find((m) => m.name === word);
    if (!mem) return null;
    return {
      kind: mem.kind === "field" ? "field" : "method",
      name: word,
      containerClass: cur.name,
    };
  }
  // Prefer locals within the current function scope.
  const locals = (model.locals ?? []).filter(
    (v) => v.name === lhs && posLine >= v.scopeStartLine && posLine <= v.scopeEndLine
  );
  if (locals.length) {
    const v = locals[locals.length - 1];
    if (model.classes.has(v.typeName)) {
      const cls = model.classes.get(v.typeName)!;
      const mem = cls.members.find((m) => m.name === word);
      if (!mem) return null;
      return {
        kind: mem.kind === "field" ? "field" : "method",
        name: word,
        containerClass: cls.name,
      };
    }
  }
  const g = model.globals.find((x) => x.name === lhs);
  if (g && model.classes.has(g.typeName)) {
    const cls = model.classes.get(g.typeName)!;
    const mem = cls.members.find((m) => m.name === word);
    if (!mem) return null;
    return {
      kind: mem.kind === "field" ? "field" : "method",
      name: word,
      containerClass: cls.name,
    };
  }
  return null;
}

export function resolveSymbolAt(
  doc: TextDocument,
  pos: { line: number; character: number },
  model: KvalModel
): ResolvedSymbol | null {
  const text = doc.getText();
  const { word } = findWordAt(text, doc.offsetAt(pos));
  if (!word || KW.includes(word)) return null;
  const posLine = pos.line;
  const posChar = pos.character;
  const lines = text.split(/\r?\n/);

  for (const c of model.classes.values()) {
    const lt = lines[c.line] ?? "";
    const nameCol = lt.indexOf(c.name);
    if (
      c.name === word &&
      nameCol >= 0 &&
      inNameRange(posLine, posChar, c.line, nameCol, c.name.length)
    ) {
      return { kind: "class", name: word };
    }
    for (const m of c.members) {
      if (m.name !== word) continue;
      const ml = lines[m.line] ?? "";
      const mc = m.startChar >= 0 ? m.startChar : ml.indexOf(m.name);
      if (mc >= 0 && inNameRange(posLine, posChar, m.line, mc, m.name.length)) {
        return {
          kind: m.kind === "field" ? "field" : "method",
          name: word,
          containerClass: c.name,
        };
      }
    }
  }

  for (const f of model.functions) {
    if (f.name !== word) continue;
    const lt = lines[f.line] ?? "";
    const fc = lt.indexOf(f.name);
    if (fc >= 0 && inNameRange(posLine, posChar, f.line, fc, f.name.length)) {
      return { kind: "function", name: word };
    }
  }

  for (const g of model.globals) {
    if (g.name !== word) continue;
    const lt = lines[g.line] ?? "";
    const gc = g.startChar >= 0 ? g.startChar : lt.indexOf(g.name);
    if (gc >= 0 && inNameRange(posLine, posChar, g.line, gc, g.name.length)) {
      return { kind: "global", name: word };
    }
  }

  const off = doc.offsetAt(pos);
  const before = text.slice(0, off);
  const arrow = before.match(/(\bthis\b|[A-Za-z_][\w]*)\s*->\s*$/);
  if (arrow) {
    const r = resolveMemberFromReceiver(model, arrow[1], word, posLine);
    if (r) return r;
  }
  const dot = before.match(/(\bthis\b|[A-Za-z_][\w]*)\s*\.\s*$/);
  if (dot) {
    const r = resolveMemberFromReceiver(model, dot[1], word, posLine);
    if (r) return r;
  }

  const funcHits = model.functions.filter((f) => f.name === word);
  if (funcHits.length === 1) return { kind: "function", name: word };
  if (model.classes.has(word)) return { kind: "class", name: word };
  const gHits = model.globals.filter((g) => g.name === word);
  if (gHits.length === 1) return { kind: "global", name: word };

  const memberHits: { cls: string }[] = [];
  for (const c of model.classes.values()) {
    if (c.members.some((m) => m.name === word)) memberHits.push({ cls: c.name });
  }
  if (memberHits.length === 1) {
    const cn = memberHits[0].cls;
    const c = model.classes.get(cn);
    const mem = c?.members.find((m) => m.name === word);
    return {
      kind: mem?.kind === "field" ? "field" : "method",
      name: word,
      containerClass: cn,
    };
  }

  return null;
}
