// The SWE-bench Verified outcome data, as packed by studies/swe-bench-verified/fetch.py.
import raw from "../../studies/swe-bench-verified/data/outcomes.json";

export interface Submission {
  id: string;
  name: string;
  date: string;
  /** 0 or 1 per task, in the order of `instances`. */
  resolved: Uint8Array;
  score: number;
  checked: boolean | null;
}

/** Same rule as the study: a per-task file that contradicts the stated score is not evidence. */
const REPORTED_TOLERANCE = 0.5;

export const commit: string = raw.source.commit;
export const instances: readonly string[] = raw.instances;

export function repositoryOf(instance: string): string {
  return instance.slice(0, instance.lastIndexOf("-")).replace("__", "/");
}

/** Repositories, largest first, and each task's repository as an index into them. */
export const repositories: readonly string[] = (() => {
  const counts = new Map<string, number>();
  for (const instance of instances) {
    const repo = repositoryOf(instance);
    counts.set(repo, (counts.get(repo) ?? 0) + 1);
  }
  return [...counts.entries()].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).map(([repo]) => repo);
})();

export const repositoryIndex: Int32Array = Int32Array.from(instances, (instance) =>
  repositories.indexOf(repositoryOf(instance)),
);

export function unpack(hex: string, length: number): Uint8Array {
  const bits = new Uint8Array(length);
  // The string is the outcomes as one big-endian number, left-padded to whole hex digits.
  const offset = hex.length * 4 - length;
  for (let i = 0; i < length; i++) {
    const position = i + offset;
    const digit = Number.parseInt(hex[position >> 2]!, 16);
    bits[i] = (digit >> (3 - (position & 3))) & 1;
  }
  return bits;
}

export const submissions: readonly Submission[] = raw.submissions
  .filter((s) => {
    const computed = (100 * s.n_resolved) / instances.length;
    return s.reported === null || Math.abs(s.reported - computed) <= REPORTED_TOLERANCE;
  })
  .map((s) => ({
    id: s.id,
    name: s.name,
    date: s.date,
    resolved: unpack(s.resolved, instances.length),
    score: s.n_resolved / instances.length,
    checked: s.checked,
  }))
  .sort((x, y) => y.score - x.score || x.id.localeCompare(y.id));
