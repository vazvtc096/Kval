import type { SemanticTokens } from "vscode-languageserver-protocol";
import { SemanticTokensBuilder } from "vscode-languageserver/node";
import type { TextDocument } from "vscode-languageserver-textdocument";
import type { KvalModel } from "./model";

/** 与 server onInitialize legend.tokenTypes 顺序一致 */
export const SEMANTIC_TOKEN_TYPES = [
  "class",
  "function",
  "method",
  "property",
  "parameter",
  "variable",
] as const;

export const SEMANTIC_TOKEN_MODIFIERS = ["declaration"] as const;

const T = {
  class: 0,
  function: 1,
  method: 2,
  property: 3,
  parameter: 4,
  variable: 5,
} as const;

const ModDeclaration = 1 << 0;

export function buildSemanticTokens(doc: TextDocument, model: KvalModel): SemanticTokens {
  const builder = new SemanticTokensBuilder();
  const text = doc.getText();
  const lines = text.split(/\r?\n/);

  // Avoid wrong coloring from regex fallback (e.g. `array arr` matches `arr` inside `array`).
  // Only emit semantic tokens when we have lexer-accurate columns.
  if (model.modelSource !== "lexer") {
    return builder.build();
  }

  const declKeys = new Set<string>();
  const k = (line: number, ch: number, len: number) => `${line}:${ch}:${len}`;
  const pushDecl = (line: number, ch: number, len: number, tokenType: number) => {
    declKeys.add(k(line, ch, len));
    builder.push(line, ch, len, tokenType, ModDeclaration);
  };

  const pushNameAt = (
    line: number,
    lineText: string,
    name: string,
    startChar: number | undefined,
    tokenType: number,
    modifiers: number,
    markDecl = true
  ) => {
    // Token-based only: require lexer-provided startChar, no substring search.
    if (typeof startChar !== "number" || startChar < 0) return;
    if (markDecl) {
      pushDecl(line, startChar, name.length, tokenType);
      return;
    }
    builder.push(line, startChar, name.length, tokenType, modifiers);
  };

  for (const cls of model.classes.values()) {
    const lt = lines[cls.line] ?? "";
    pushNameAt(cls.line, lt, cls.name, cls.startChar, T.class, ModDeclaration);
    for (const m of cls.members) {
      const ml = lines[m.line] ?? "";
      const tok = m.kind === "field" ? T.property : m.kind === "ctor" ? T.method : T.method;
      pushNameAt(m.line, ml, m.name, m.startChar, tok, ModDeclaration);
    }
  }

  for (const f of model.functions) {
    const lt = lines[f.line] ?? "";
    pushNameAt(f.line, lt, f.name, f.startChar, T.function, ModDeclaration);
  }

  for (const g of model.globals) {
    const lt = lines[g.line] ?? "";
    pushNameAt(g.line, lt, g.name, g.startChar, T.variable, ModDeclaration);
  }
  for (const v of model.locals ?? []) {
    const lt = lines[v.line] ?? "";
    pushNameAt(v.line, lt, v.name, v.startChar, T.variable, ModDeclaration);
  }
  for (const p of model.params ?? []) {
    const lt = lines[p.line] ?? "";
    pushNameAt(p.line, lt, p.name, p.startChar, T.parameter, ModDeclaration);
  }

  // ===== Usage coloring =====
  const maskedLines = maskLinesPreserveColumns(text);
  const emittedKeys = new Set<string>(declKeys);

  const pushUsageAt = (line: number, ch: number, len: number, tokenType: number) => {
    const key = k(line, ch, len);
    if (emittedKeys.has(key)) return;
    emittedKeys.add(key);
    builder.push(line, ch, len, tokenType, 0);
  };

  const pushWordUsages = (name: string, tokenType: number) => {
    if (!name) return;
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`\\b${esc}\\b`, "g");
    for (let li = 0; li < maskedLines.length; li++) {
      const line = maskedLines[li];
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(line))) {
        const ch = m.index;
        pushUsageAt(li, ch, name.length, tokenType);
      }
    }
  };

  // class/function/global symbol usages
  for (const c of model.classes.values()) pushWordUsages(c.name, T.class);
  for (const f of model.functions) pushWordUsages(f.name, T.function);
  for (const g of model.globals) pushWordUsages(g.name, T.variable);

  type Scoped = {
    name: string;
    tokenType: number;
    scopeStartLine: number;
    scopeEndLine: number;
    declLine: number;
  };
  const scopedByName = new Map<string, Scoped[]>();
  const addScoped = (s: Scoped) => {
    const arr = scopedByName.get(s.name) ?? [];
    arr.push(s);
    scopedByName.set(s.name, arr);
  };
  for (const v of model.locals ?? []) {
    addScoped({
      name: v.name,
      tokenType: T.variable,
      scopeStartLine: v.scopeStartLine,
      scopeEndLine: v.scopeEndLine,
      declLine: v.line,
    });
  }
  for (const p of model.params ?? []) {
    addScoped({
      name: p.name,
      tokenType: T.parameter,
      scopeStartLine: p.scopeStartLine,
      scopeEndLine: p.scopeEndLine,
      declLine: p.line,
    });
  }
  for (const arr of scopedByName.values()) {
    arr.sort((a, b) => {
      const aLen = a.scopeEndLine - a.scopeStartLine;
      const bLen = b.scopeEndLine - b.scopeStartLine;
      if (aLen !== bLen) return aLen - bLen;
      return b.declLine - a.declLine;
    });
  }

  // 局部变量/参数 usage：按最近作用域优先（遮蔽规则）
  const idRe = /\b[A-Za-z_]\w*\b/g;
  for (let li = 0; li < maskedLines.length; li++) {
    const line = maskedLines[li];
    idRe.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = idRe.exec(line))) {
      const name = m[0];
      const ch = m.index;
      const cands = scopedByName.get(name);
      if (!cands || cands.length === 0) continue;
      const chosen = cands.find((s) => li >= s.scopeStartLine && li <= s.scopeEndLine);
      if (!chosen) continue;
      pushUsageAt(li, ch, name.length, chosen.tokenType);
    }
  }

  // member usages in call/access style: obj.member / obj->member
  const memberKinds = new Map<string, number>();
  for (const c of model.classes.values()) {
    for (const m of c.members) {
      const t = m.kind === "field" ? T.property : T.method;
      memberKinds.set(m.name, t);
    }
  }
  for (const [name, tokenType] of memberKinds) {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(?:\\.|->)\\s*(${esc})\\b`, "g");
    for (let li = 0; li < maskedLines.length; li++) {
      const line = maskedLines[li];
      re.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(line))) {
        const ch = m.index + m[0].length - name.length;
        pushUsageAt(li, ch, name.length, tokenType);
      }
    }
  }

  return builder.build();
}

function maskLinesPreserveColumns(text: string): string[] {
  // mask comments/strings with spaces so regex usage scan avoids false positives.
  let inBlock = false;
  const srcLines = text.split(/\r?\n/);
  const out: string[] = [];
  for (const src of srcLines) {
    let i = 0;
    let outLine = "";
    let inString: '"' | "'" | "" = "";
    while (i < src.length) {
      const c = src[i];
      const n = i + 1 < src.length ? src[i + 1] : "";
      if (inBlock) {
        if (c === "*" && n === "/") {
          outLine += "  ";
          i += 2;
          inBlock = false;
        } else {
          outLine += " ";
          i += 1;
        }
        continue;
      }
      if (inString) {
        if (c === "\\") {
          outLine += " ";
          i += 1;
          if (i < src.length) {
            outLine += " ";
            i += 1;
          }
          continue;
        }
        outLine += " ";
        if (c === inString) inString = "";
        i += 1;
        continue;
      }
      if (c === "/" && n === "/") {
        outLine += " ".repeat(src.length - i);
        i = src.length;
        continue;
      }
      if (c === "/" && n === "*") {
        outLine += "  ";
        i += 2;
        inBlock = true;
        continue;
      }
      if (c === '"' || c === "'") {
        inString = c as '"' | "'";
        outLine += " ";
        i += 1;
        continue;
      }
      outLine += c;
      i += 1;
    }
    out.push(outLine);
  }
  return out;
}
