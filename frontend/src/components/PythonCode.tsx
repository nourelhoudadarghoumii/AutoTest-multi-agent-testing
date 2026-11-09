import { useMemo } from 'react';

/**
 * Lightweight Python syntax highlighter — no external dependency.
 * Produces spans with tok-* classes styled in index.css.
 */

const KEYWORDS = new Set([
  'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
  'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
  'import', 'in', 'is', 'lambda', 'None', 'nonlocal', 'not', 'or', 'pass',
  'raise', 'return', 'True', 'False', 'try', 'while', 'with', 'yield', 'self',
]);

const BUILTINS = new Set([
  'print', 'len', 'range', 'int', 'str', 'float', 'bool', 'list', 'dict',
  'set', 'tuple', 'type', 'isinstance', 'super', 'object', 'Exception',
  'ValueError', 'TypeError', 'KeyError', 'IndexError', 'ZeroDivisionError',
  'open', 'enumerate', 'zip', 'sorted', 'abs', 'min', 'max', 'sum', 'any',
  'all', 'map', 'filter', 'hasattr', 'getattr', 'setattr', 'staticmethod',
  'classmethod', 'property', 'dataclass',
]);

type Token = { text: string; cls: string | null };

function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < line.length) {
    const rest = line.slice(i);

    // Comments
    if (rest.startsWith('#')) {
      tokens.push({ text: rest, cls: 'tok-com' });
      break;
    }

    // Strings (triple-quote and single-line, incl. f-strings)
    const strMatch = rest.match(/^(?:[rbuf]{0,2})("""|'''|"|')((?:\\.|(?!\1)[^\\])*)\1?/);
    if (strMatch && strMatch[0]) {
      tokens.push({ text: strMatch[0], cls: 'tok-str' });
      i += strMatch[0].length;
      continue;
    }

    // Decorators
    if (rest.startsWith('@')) {
      const dec = rest.match(/^@[\w\.]+/);
      if (dec) {
        tokens.push({ text: dec[0], cls: 'tok-dec' });
        i += dec[0].length;
        continue;
      }
    }

    // Numbers
    const numMatch = rest.match(/^(0x[\da-fA-F]+|\d+\.?\d*(?:e[+-]?\d+)?)/);
    if (numMatch) {
      tokens.push({ text: numMatch[0], cls: 'tok-num' });
      i += numMatch[0].length;
      continue;
    }

    // Identifiers
    const idMatch = rest.match(/^[A-Za-z_]\w*/);
    if (idMatch) {
      const word = idMatch[0];
      // Look ahead for a call
      const after = line.slice(i + word.length).match(/^\s*\(/);
      let cls: string | null = null;
      if (KEYWORDS.has(word)) cls = 'tok-kw';
      else if (BUILTINS.has(word)) cls = 'tok-builtin';
      else if (after && /^[A-Z]/.test(word)) cls = 'tok-cls';
      else if (after) cls = 'tok-fn';
      tokens.push({ text: word, cls });
      i += word.length;
      continue;
    }

    // Operators / punctuation
    const opMatch = rest.match(/^[+\-*/%=<>!&|^~:;,.()\[\]{}]+/);
    if (opMatch) {
      tokens.push({ text: opMatch[0], cls: 'tok-op' });
      i += opMatch[0].length;
      continue;
    }

    // Whitespace & anything else
    const ws = rest.match(/^\s+/);
    if (ws) {
      tokens.push({ text: ws[0], cls: null });
      i += ws[0].length;
    } else {
      tokens.push({ text: line[i], cls: null });
      i += 1;
    }
  }

  return tokens;
}

interface PythonCodeProps {
  code: string;
  showLineNumbers?: boolean;
  maxHeight?: string;
}

export default function PythonCode({ code, showLineNumbers = true, maxHeight }: PythonCodeProps) {
  const lines = useMemo(() => code.split('\n'), [code]);

  return (
    <div
      className="panel dark-scrollbar overflow-auto font-mono text-[12.5px] leading-[1.65]"
      style={{ maxHeight: maxHeight ?? '70vh' }}
    >
      <pre className="p-4 min-w-max">
        {lines.map((line, idx) => (
          <div key={idx} className="flex">
            {showLineNumbers && (
              <span className="select-none text-slate2-600 pr-4 text-right w-10 shrink-0">
                {idx + 1}
              </span>
            )}
            <code className="whitespace-pre">
              {tokenizeLine(line).map((tok, tIdx) =>
                tok.cls ? (
                  <span key={tIdx} className={tok.cls}>{tok.text}</span>
                ) : (
                  <span key={tIdx}>{tok.text}</span>
                )
              )}
            </code>
          </div>
        ))}
      </pre>
    </div>
  );
}
