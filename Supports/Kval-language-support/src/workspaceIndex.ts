import * as fs from "fs";
import * as path from "path";
import { Range } from "vscode-languageserver-types";
import { URI } from "vscode-uri";
import { buildModel, type KvalModel } from "./model";

export type SymKind = "class" | "function" | "method" | "field" | "global";

export interface SymDef {
  uri: string;
  name: string;
  kind: SymKind;
  /** 类内成员时为其所属类名 */
  containerClass?: string;
  range: Range;
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function* walkKvalFiles(root: string): Generator<string> {
  if (!fs.existsSync(root)) return;
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return;
  }
  for (const ent of entries) {
    const full = path.join(root, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === "node_modules" || ent.name === ".git" || ent.name === "out") continue;
      yield* walkKvalFiles(full);
    } else if (ent.isFile() && ent.name.endsWith(".kval")) {
      yield full;
    }
  }
}

function rangeOnLine(line: number, lineText: string, name: string): Range | undefined {
  const ch = lineText.indexOf(name);
  if (ch < 0) return undefined;
  return Range.create(line, ch, line, ch + name.length);
}

/** 从磁盘与内存合并构建符号表 */
export function buildSymbolIndex(
  workspaceRoots: string[],
  openDocuments: Map<string, string>
): { defs: SymDef[]; models: Map<string, KvalModel> } {
  const defs: SymDef[] = [];
  const models = new Map<string, KvalModel>();
  const seen = new Set<string>();

  const ingestFile = (fsPath: string) => {
    const uri = URI.file(fsPath).toString();
    const text =
      openDocuments.get(uri) ??
      (() => {
        try {
          return fs.readFileSync(fsPath, "utf8");
        } catch {
          return "";
        }
      })();
    if (!text) return;
    const model = buildModel(text);
    models.set(uri, model);
    const lines = text.split(/\r?\n/);

    for (const cls of model.classes.values()) {
      const lt = lines[cls.line] ?? "";
      const r = rangeOnLine(cls.line, lt, cls.name);
      if (r) {
        defs.push({ uri, name: cls.name, kind: "class", range: r });
      }
      for (const m of cls.members) {
        const ml = lines[m.line] ?? "";
        const mr = rangeOnLine(m.line, ml, m.name);
        if (mr) {
          const kind: SymKind = m.kind === "field" ? "field" : "method";
          defs.push({
            uri,
            name: m.name,
            kind,
            containerClass: cls.name,
            range: mr,
          });
        }
      }
    }
    for (const f of model.functions) {
      const lt = lines[f.line] ?? "";
      const r = rangeOnLine(f.line, lt, f.name);
      if (r) defs.push({ uri, name: f.name, kind: "function", range: r });
    }
    for (const g of model.globals) {
      const lt = lines[g.line] ?? "";
      const r = rangeOnLine(g.line, lt, g.name);
      if (r) defs.push({ uri, name: g.name, kind: "global", range: r });
    }
  };

  for (const root of workspaceRoots) {
    if (!root) continue;
    for (const fp of walkKvalFiles(root)) {
      if (seen.has(fp)) continue;
      seen.add(fp);
      ingestFile(fp);
    }
  }
  for (const uri of openDocuments.keys()) {
    const fsPath = URI.parse(uri).fsPath;
    if (seen.has(fsPath)) continue;
    if (!fsPath.endsWith(".kval")) continue;
    seen.add(fsPath);
    ingestFile(fsPath);
  }

  return { defs, models };
}

/** 简化：按行分割后逐行匹配（避免 \r\n 偏移错误） */
export function rangesOfWordPerLine(text: string, word: string): Range[] {
  const ranges: Range[] = [];
  if (!word || !/^[A-Za-z_]\w*$/.test(word)) return ranges;
  const re = new RegExp(`\\b${escapeRe(word)}\\b`, "g");
  const lines = text.split(/\r?\n/);
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line))) {
      ranges.push(Range.create(li, m.index, li, m.index + word.length));
    }
  }
  return ranges;
}

export function memberBodyLines(model: KvalModel, className: string): Set<number> {
  const c = model.classes.get(className);
  if (!c) return new Set();
  const s = new Set<number>();
  for (let l = c.line + 1; l < c.endLine; l++) s.add(l);
  return s;
}

/** `obj->member` / `obj.member` 中 member 的范围 */
export function rangesMemberCallStyle(text: string, member: string): Range[] {
  const out: Range[] = [];
  if (!member || !/^[A-Za-z_]\w*$/.test(member)) return out;
  const lines = text.split(/\r?\n/);
  const re = new RegExp(`(?:\\.|->)\\s*(${escapeRe(member)})\\b`, "g");
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line))) {
      const ch = m.index + m[0].length - member.length;
      out.push(Range.create(li, ch, li, ch + member.length));
    }
  }
  return out;
}

export function* eachKvalDocument(
  workspaceRoots: string[],
  openDocuments: Map<string, string>
): Generator<[string, string]> {
  const seen = new Set<string>();
  for (const root of workspaceRoots) {
    if (!root) continue;
    for (const fp of walkKvalFiles(root)) {
      const uri = URI.file(fp).toString();
      seen.add(uri);
      const text =
        openDocuments.get(uri) ??
        (() => {
          try {
            return fs.readFileSync(fp, "utf8");
          } catch {
            return "";
          }
        })();
      if (text) yield [uri, text];
    }
  }
  for (const [uri, text] of openDocuments) {
    if (!uri.endsWith(".kval")) continue;
    if (seen.has(uri)) continue;
    seen.add(uri);
    yield [uri, text];
  }
}

export type RefKind = "class" | "function" | "global" | "method" | "field";

function mergeUniqueRanges(ranges: Range[]): Range[] {
  const key = (r: Range) => `${r.start.line}:${r.start.character}-${r.end.character}`;
  const m = new Map<string, Range>();
  for (const r of ranges) m.set(key(r), r);
  return [...m.values()].sort(
    (a, b) => a.start.line - b.start.line || a.start.character - b.start.character
  );
}

/** 重命名/查找引用共用的出现位置（成员含类体内定义 + 调用写法） */
export function symbolOccurrenceRanges(
  kind: RefKind,
  name: string,
  containerClass: string | undefined,
  workspaceRoots: string[],
  openDocuments: Map<string, string>
): Map<string, Range[]> {
  const result = new Map<string, Range[]>();
  for (const [uri, text] of eachKvalDocument(workspaceRoots, openDocuments)) {
    const model = buildModel(text);
    let ranges: Range[] = [];
    if (kind === "method" || kind === "field") {
      const cn = containerClass ?? "";
      const body = memberBodyLines(model, cn);
      const inBody = rangesOfWordPerLine(text, name).filter((r) => body.has(r.start.line));
      const calls = rangesMemberCallStyle(text, name);
      ranges = mergeUniqueRanges([...inBody, ...calls]);
    } else {
      ranges = rangesOfWordPerLine(text, name);
    }
    if (ranges.length) result.set(uri, ranges);
  }
  return result;
}
