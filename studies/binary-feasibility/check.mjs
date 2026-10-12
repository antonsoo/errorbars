// Native TypeScript execution with Node 24. Inputs come from the independent
// Decimal/table study; this runner only calls the production API.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const api = await import(pathToFileURL(process.argv[2]).href);
const rows = JSON.parse(readFileSync(0, 'utf8'));
const output = rows.map(({ p, rho, delta, n }) => {
  const inputs = { baselineAccuracy: p, rho };
  try {
    if (n !== undefined) return { mde: api.minimumDetectableEffect(n, inputs) };
    return { n: api.questionsNeeded(delta, inputs).nQuestions };
  } catch (error) {
    if (!(error instanceof api.BinaryFeasibilityError)) throw error;
    return { unavailable: true };
  }
});
process.stdout.write(JSON.stringify(output));
