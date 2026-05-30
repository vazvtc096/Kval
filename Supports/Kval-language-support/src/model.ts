/**
 * 轻量符号模型：用于补全/悬停/签名/导航（启发式，非完整语义分析）。
 */

export type MemberKind = "method" | "field" | "ctor";
export type TypeDeclKind = "class" | "struct";

export interface MemberDef {
  name: string;
  kind: MemberKind;
  detail: string;
  line: number;
  startChar: number;
}

export interface ClassDef {
  name: string;
  declKind: TypeDeclKind;
  line: number;
  endLine: number;
  startChar: number;
  members: MemberDef[];
}

export interface FuncDef {
  name: string;
  params: string;
  returnType: string;
  line: number;
  startChar: number;
}

export interface GlobalVar {
  name: string;
  typeName: string;
  line: number;
  startChar: number;
}

export interface LocalVar {
  name: string;
  typeName: string;
  line: number;
  startChar: number;
  scopeStartLine: number;
  scopeEndLine: number;
}

export interface ParamVar {
  name: string;
  typeName: string;
  line: number;
  startChar: number;
  scopeStartLine: number;
  scopeEndLine: number;
}

export interface KvalModel {
  /** regex=快速回退；lexer=由 Kval Lexer/token 提取（列号精确） */
  modelSource: "regex" | "lexer";
  classes: Map<string, ClassDef>;
  functions: FuncDef[];
  globals: GlobalVar[];
  locals: LocalVar[];
  params: ParamVar[];
}

export const KW = [
  "int",
  "float",
  "bool",
  "auto",
  "const",
  "static",
  "constexpr",
  "void",
  "string",
  "array",
  "template",
  "typename",
  "class",
  "struct",
  "public",
  "protected",
  "private",
  "code",
  "New",
  "operator",
  "roperator",
  "global",
  "local",
  "builtins",
  "closure",
  "this",
  "base",
  "true",
  "false",
  "if",
  "elif",
  "else",
  "for",
  "while",
  "return",
  "delete",
  "break",
  "continue",
  "switch",
  "case",
  "varScopeOrder",
  "throw",
  "try",
  "catch",
  "finally",
  "import",
  "from",
  "as",
  "export",
  "namespace",
];

const TYPEISH = /^(int|float|bool|string|array|auto|void|\w+)$/;

const TYPE_TOKEN = String.raw`[A-Za-z_][\w]*`;
const IDENT = String.raw`[A-Za-z_][\w]*`;

function stripModifiers(s: string): string {
  return s.replace(/^\s*(?:export|static|const|constexpr)\s+/g, "");
}

function lineWithoutLineComment(line: string): string {
  const idx = line.indexOf("//");
  if (idx < 0) return line;
  return line.slice(0, idx);
}

/** 粗略去掉块注释，保留换行以维持行号 */
function maskBlockComments(text: string): string {
  let out = "";
  let i = 0;
  let inBlock = false;
  while (i < text.length) {
    if (!inBlock && text[i] === "/" && text[i + 1] === "*") {
      inBlock = true;
      out += "  ";
      i += 2;
      continue;
    }
    if (inBlock && text[i] === "*" && text[i + 1] === "/") {
      inBlock = false;
      out += "  ";
      i += 2;
      continue;
    }
    if (inBlock) {
      out += text[i] === "\n" ? "\n" : " ";
      i += 1;
      continue;
    }
    out += text[i];
    i += 1;
  }
  return out;
}

function findMatchingBraceClose(lines: string[], openLine: number, openBraceCol: number): number {
  let depth = 0;
  for (let li = openLine; li < lines.length; li++) {
    const raw = lines[li];
    const line = li === openLine ? raw.slice(openBraceCol) : raw;
    for (let j = 0; j < line.length; j++) {
      const c = line[j];
      if (c === "{") depth++;
      else if (c === "}") {
        depth--;
        if (depth === 0) return li;
      }
    }
  }
  return lines.length - 1;
}

function parseClassBody(className: string, bodyLines: string[], baseLine: number): MemberDef[] {
  const members: MemberDef[] = [];
  for (let k = 0; k < bodyLines.length; k++) {
    const physicalLine = baseLine + k;
    const stripped0 = lineWithoutLineComment(bodyLines[k]).trim();
    const stripped = stripModifiers(stripped0);
    if (!stripped || stripped === "{" || stripped === "}") continue;
    if (/^(public|private|protected|code):$/.test(stripped)) continue;

    // field: `Type name;` or `Type name[sz];` or `Type[sz] name;`
    const fieldM = stripped.match(
      new RegExp(
        String.raw`^(${TYPE_TOKEN})(?:\s*\[[^\]]*\])?\s+(${IDENT})(?:\s*\[[^\]]*\])?\s*;\s*$`
      )
    );
    if (fieldM) {
      const typeName = fieldM[1];
      const name = fieldM[2];
      if (TYPEISH.test(typeName)) {
        members.push({
          name,
          kind: "field",
          detail: `${typeName} ${name}`,
          line: physicalLine,
          startChar: bodyLines[k].indexOf(name),
        });
        continue;
      }
    }

    // method: `Ret name(params) {` or declaration `Ret name(params);`
    const methM = stripped.match(
      new RegExp(String.raw`^(${TYPE_TOKEN})\s+(${IDENT})\s*\(([^)]*)\)\s*(?:\{|;)?\s*$`)
    );
    if (methM) {
      const ret = methM[1];
      const name = methM[2];
      const params = methM[3].trim();
      const kind: MemberKind = name === className ? "ctor" : "method";
      members.push({
        name,
        kind,
        detail: `${ret} ${name}(${params})`,
        line: physicalLine,
        startChar: bodyLines[k].indexOf(name),
      });
    }
  }
  return members;
}

export function buildModel(text: string): KvalModel {
  const masked = maskBlockComments(text);
  const lines = masked.split(/\r?\n/);
  const classes = new Map<string, ClassDef>();
  const functions: FuncDef[] = [];
  const globals: GlobalVar[] = [];

  const classIntervals: { start: number; end: number }[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lineWithoutLineComment(lines[i]);
    const cm = line.match(/\b(class|struct)\s+([A-Za-z_][\w]*)\s*(?:\{|:|\s)/);
    if (!cm) continue;
    const declKind = (cm[1] === "struct" ? "struct" : "class") satisfies TypeDeclKind;
    const name = cm[2];
    const braceIdx = line.indexOf("{");
    if (braceIdx < 0) continue;
    const close = findMatchingBraceClose(lines, i, braceIdx);
    const body = lines.slice(i + 1, close);
    const cls: ClassDef = {
      name,
      declKind,
      line: i,
      endLine: close,
      startChar: line.indexOf(cm[1]),
      members: parseClassBody(name, body, i + 1),
    };
    classes.set(name, cls);
    classIntervals.push({ start: i, end: close });
  }

  const inClass = (ln: number) => classIntervals.some((iv) => ln >= iv.start && ln <= iv.end);

  for (let i = 0; i < lines.length; i++) {
    if (inClass(i)) continue;
    const line0 = lineWithoutLineComment(lines[i]);
    const line = stripModifiers(line0);

    // tolerate `template <...>` line by skipping it
    if (/^\s*template\s*</.test(line.trim())) continue;

    const fm = line.match(
      new RegExp(String.raw`^\s*(${TYPE_TOKEN})\s+(${IDENT})\s*\(([^)]*)\)\s*(?:\{|;)?\s*$`)
    );
    if (fm) {
      const ret = fm[1];
      const name = fm[2];
      const params = fm[3].trim();
      functions.push({
        name,
        params,
        returnType: ret,
        line: i,
        startChar: line.search(/\S/) >= 0 ? line.search(/\S/) : 0,
      });
      continue;
    }

    // globals: `Type name;` / `Type name = ...;` / scoped `global::x = ...;`
    const gv = line.match(
      new RegExp(
        String.raw`^\s*(${TYPE_TOKEN})\s+(?:(?:global|local|builtins|closure(?:\{\d+\})?)::)?(${IDENT})(?:\s*(?:=|;).*)$`
      )
    );
    if (gv && gv[1] !== "return" && TYPEISH.test(gv[1])) {
      globals.push({
        typeName: gv[1],
        name: gv[2],
        line: i,
        startChar: line.indexOf(gv[2]),
      });
    }
  }

  return { modelSource: "regex", classes, functions, globals, locals: [], params: [] };
}

export function classContainingLine(model: KvalModel, line: number): ClassDef | undefined {
  for (const c of model.classes.values()) {
    if (line >= c.line && line <= c.endLine) return c;
  }
  return undefined;
}

export function findWordAt(
  text: string,
  offset: number
): { word: string; start: number; end: number } {
  const isId = (c: string) => /[\w]/.test(c);
  let start = offset;
  while (start > 0 && isId(text[start - 1])) start--;
  let end = offset;
  while (end < text.length && isId(text[end])) end++;
  return { word: text.slice(start, end), start, end };
}
