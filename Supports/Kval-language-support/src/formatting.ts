/**
 * 轻量格式化：按花括号调整缩进，整行 trim；不解析字符串内括号。
 */

import type { Range } from "vscode-languageserver-types";

export interface FormatOptions {
  tabSize: number;
  insertSpaces: boolean;
}

function countChar(s: string, c: string): number {
  let n = 0;
  for (let i = 0; i < s.length; i++) if (s[i] === c) n++;
  return n;
}

function depthBeforeLine(lines: string[], beforeLine: number): number {
  let d = 0;
  for (let i = 0; i < beforeLine && i < lines.length; i++) {
    const t = lines[i].trim();
    d += countChar(t, "{") - countChar(t, "}");
    if (d < 0) d = 0;
  }
  return d;
}

export function formatKvalDocument(text: string, opts: FormatOptions): string {
  const eol = text.includes("\r\n") ? "\r\n" : text.includes("\r") ? "\r" : "\n";
  const lines = text.split(/\r\n|\n|\r/);
  const unit = opts.insertSpaces ? " ".repeat(Math.max(1, opts.tabSize)) : "\t";
  let depth = 0;
  const out: string[] = [];

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    let lineDepth = depth;
    if (trimmed.startsWith("}") || trimmed.startsWith("};")) {
      lineDepth = Math.max(0, depth - 1);
    }
    const opens = countChar(trimmed, "{");
    const closes = countChar(trimmed, "}");
    out.push(unit.repeat(lineDepth) + trimmed);
    depth = lineDepth + opens - closes;
    if (depth < 0) depth = 0;
  }

  const hadTrailing = /\r?\n$|\n$|\r$/.test(text);
  const result = out.join(eol);
  return hadTrailing ? result + eol : result;
}

export function formatRange(text: string, range: Range, opts: FormatOptions): string {
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  const lines = text.split(/\r\n|\n|\r/);
  const start = Math.max(0, range.start.line);
  const end = Math.min(lines.length - 1, range.end.line);
  if (start > end) return text;

  const unit = opts.insertSpaces ? " ".repeat(Math.max(1, opts.tabSize)) : "\t";
  let depth = depthBeforeLine(lines, start);
  const out: string[] = [];
  out.push(...lines.slice(0, start));

  for (let li = start; li <= end; li++) {
    const rawLine = lines[li];
    const trimmed = rawLine.trim();
    let lineDepth = depth;
    if (trimmed.startsWith("}") || trimmed.startsWith("};")) {
      lineDepth = Math.max(0, depth - 1);
    }
    const opens = countChar(trimmed, "{");
    const closes = countChar(trimmed, "}");
    out.push(unit.repeat(lineDepth) + trimmed);
    depth = lineDepth + opens - closes;
    if (depth < 0) depth = 0;
  }

  out.push(...lines.slice(end + 1));
  const hadTrailing = /\r?\n$|\n$|\r$/.test(text);
  const result = out.join(eol);
  return hadTrailing ? result + eol : result;
}
