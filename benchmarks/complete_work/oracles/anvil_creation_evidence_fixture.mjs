/* Evaluator-owned fixture.  It is intentionally not placed in the candidate. */
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) args.set(process.argv[index], process.argv[index + 1]);
const candidate = resolve(required("--repo"));
const output = resolve(required("--output"));

function required(name) {
  const value = args.get(name);
  if (!value) throw new Error("missing " + name);
  return value;
}

function check(id, passed, detail) {
  return { id, passed: Boolean(passed), detail };
}

const ids = {
  objective: "obj_11111111111111111111111111111111",
  first: "ws_22222222222222222222222222222222",
  second: "ws_33333333333333333333333333333333",
  baseline: "task_44444444444444444444444444444444",
  history: "task_55555555555555555555555555555555",
  unknown: "task_66666666666666666666666666666666",
  explicit: "task_77777777777777777777777777777777",
  fenced: "task_88888888888888888888888888888888",
  quoted: "task_99999999999999999999999999999999",
  conflict: "task_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  parent: "task_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  child: "task_cccccccccccccccccccccccccccccccc",
};

function task(id, title, details = "") {
  return { id, title, outcome: title + " outcome.", details, completionCriteria: [], dependencies: [], externalBlocker: null, completion: null, discontinued: null, tasks: [] };
}

function graph(phase, tasks, second = false) {
  const workstreams = [{ id: ids.first, title: "First workstream", outcome: "First workstream outcome.", details: "", tasks }];
  if (second) workstreams.push({ id: ids.second, title: "Second workstream", outcome: "Second workstream outcome.", details: "", tasks: [] });
  return { id: ids.objective, title: "Creation evidence fixture", outcome: "Creation evidence is public view metadata.", details: "", phase, workstreams };
}

function nodeFor(view, id) {
  const node = view.graph.nodes.find((candidateNode) => candidateNode.id === id);
  if (!node) throw new Error("fixture task is absent from the human view");
  return node;
}

function values(view, taskIds) {
  return Object.fromEntries(taskIds.map((id) => {
    const node = nodeFor(view, id);
    return [id, { phase: node.data["Creation phase"], evidence: node.data["Creation evidence"], marker: node.planningSublabel }];
  }));
}

function evidenceIsSafe(value) {
  return typeof value === "string" && !/(?:\/(?:Users|tmp|home)\/|[a-f0-9]{40}|\bfatal:|\berror:)/i.test(value);
}

function derivedState(value) {
  const clone = structuredClone(value);
  for (const node of clone.graph.nodes) {
    if (node.data) {
      delete node.data["Creation evidence"];
      delete node.data["Creation phase"];
    }
    delete node.creationPhase;
    delete node.planningSublabel;
    delete node.sublabel;
  }
  return clone;
}

function runGit(repository, command) {
  execFileSync("git", command, { cwd: repository, stdio: "ignore" });
}

async function commitGraph(repository, value, message) {
  const file = join(repository, ".manifest", "objectives", ids.objective + ".json");
  await mkdir(join(repository, ".manifest", "objectives"), { recursive: true });
  await writeFile(file, JSON.stringify(value), "utf8");
  runGit(repository, ["add", "--", ".manifest/objectives/" + ids.objective + ".json"]);
  runGit(repository, ["commit", "-q", "-m", message]);
}

async function gitRepository() {
  const repository = await mkdtemp(join(tmpdir(), "anvil-creation-evaluator-"));
  runGit(repository, ["init", "-q"]);
  runGit(repository, ["config", "user.name", "Anvil evaluator"]);
  runGit(repository, ["config", "user.email", "anvil-evaluator@example.invalid"]);
  return repository;
}

async function embeddedHuman(html) {
  const match = html.match(/<script id="manifest-human-view" type="application\/json">([\s\S]*?)<\/script>/);
  if (!match) throw new Error("page did not embed a human view");
  return JSON.parse(match[1]);
}

async function main() {
  const taskCreationModule = await import(pathToFileURL(join(candidate, "src/manifest/task-creation.ts")).href);
  const { deriveTaskCreation } = taskCreationModule;
  const deriveEvidence = taskCreationModule.deriveTaskCreationEvidence ?? deriveTaskCreation;
  const manifest = await import(pathToFileURL(join(candidate, "src/manifest/index.ts")).href);
  const { buildManifestHumanView, startManifestViewServer, validateObjective } = manifest;
  const checks = [];
  const roots = [];
  try {
    const repository = await gitRepository();
    roots.push(repository);
    const baseline = task(ids.baseline, "Baseline");
    const transitionUnknown = task(ids.unknown, "Transition task");
    await commitGraph(repository, graph("planning", [baseline]), "planning baseline");
    await commitGraph(repository, graph("implementation", [baseline, transitionUnknown]), "implementation transition");
    const current = graph("implementation", [
      baseline,
      transitionUnknown,
      task(ids.history, "Later history task"),
      task(ids.explicit, "Explicit task", "Creation phase: Planning."),
    ]);
    await writeFile(join(repository, ".manifest", "objectives", ids.objective + ".json"), JSON.stringify(current), "utf8");
    const creation = await deriveEvidence(repository, current);
    const human = buildManifestHumanView(current, undefined, creation);
    const observed = values(human, [ids.history, ids.unknown, ids.explicit]);
    checks.push(check("evidence_categories", observed[ids.explicit].evidence === "Task details" && observed[ids.history].evidence === "Git history" && observed[ids.unknown].evidence === "Unproven", "explicit, committed-history, and unproven tasks expose the three fixed evidence values"));
    checks.push(check("phase_and_card_invariants", observed[ids.explicit].phase.startsWith("Planning") && observed[ids.history].phase.startsWith("Added during Implementation") && observed[ids.unknown].phase.startsWith("Unknown") && observed[ids.history].marker.includes("Added during Implementation"), "existing phase labels and the Implementation-added card marker remain compatible"));
    const baselineHuman = buildManifestHumanView(current);
    const sameDerivedState = JSON.stringify(derivedState(baselineHuman)) === JSON.stringify(derivedState(human));
    checks.push(check("advisory_graph_invariants", sameDerivedState && JSON.stringify(current) === JSON.stringify(graph("implementation", [baseline, transitionUnknown, task(ids.history, "Later history task"), task(ids.explicit, "Explicit task", "Creation phase: Planning.")])), "creation evidence changes no serialized graph input or derived view state beyond its task detail field"));

    const noHistory = await mkdtemp(join(tmpdir(), "anvil-creation-no-history-"));
    roots.push(noHistory);
    const controls = graph("implementation", [
      task(ids.explicit, "Explicit marker", "Creation phase: Implementation."),
      task(ids.fenced, "Fenced marker", "```md\nCreation phase: Implementation.\n```"),
      task(ids.quoted, "Quoted marker", 'Quoted example: "Creation phase: Implementation."'),
      task(ids.conflict, "Conflicting markers", "Creation phase: Planning.\nCreation phase: Implementation."),
    ]);
    const controlCreation = await deriveEvidence(noHistory, controls);
    const controlHuman = buildManifestHumanView(controls, undefined, controlCreation);
    const controlObserved = values(controlHuman, [ids.explicit, ids.fenced, ids.quoted, ids.conflict]);
    checks.push(check("explicit_marker_controls", controlObserved[ids.explicit].evidence === "Task details" && [ids.fenced, ids.quoted, ids.conflict].every((id) => controlObserved[id].evidence === "Unproven" && controlObserved[id].phase.startsWith("Unknown")), "standalone-marker precedence holds while fenced, quoted, and conflicting markers remain unproven"));

    const malformed = await gitRepository();
    roots.push(malformed);
    await commitGraph(malformed, graph("planning", [baseline]), "planning baseline");
    const historyFile = join(malformed, ".manifest", "objectives", ids.objective + ".json");
    await writeFile(historyFile, "{ malformed historical graph", "utf8");
    runGit(malformed, ["add", "--", ".manifest/objectives/" + ids.objective + ".json"]);
    runGit(malformed, ["commit", "-q", "-m", "malformed history"]);
    const malformedCurrent = graph("implementation", [baseline, task(ids.history, "Unproven after malformed history")]);
    const malformedHuman = buildManifestHumanView(malformedCurrent, undefined, await deriveEvidence(malformed, malformedCurrent));
    checks.push(check("history_controls", nodeFor(malformedHuman, ids.history).data["Creation evidence"] === "Unproven", "transition and malformed Git history cannot be reported as Git history evidence"));

    const recursiveParent = task(ids.parent, "Moved parent", "Creation phase: Implementation.");
    recursiveParent.tasks.push(task(ids.child, "Moved child", "Creation phase: Implementation."));
    const recursive = graph("implementation", [baseline], true);
    recursive.workstreams[1].tasks.push(recursiveParent);
    const recursiveHuman = buildManifestHumanView(recursive, undefined, await deriveEvidence(noHistory, recursive));
    checks.push(check("recursive_reparent_controls", [ids.parent, ids.child].every((id) => nodeFor(recursiveHuman, id).data["Creation evidence"] === "Task details"), "recursive tasks retain task-details evidence after reparenting"));

    const valid = validateObjective(current);
    if (!valid.valid) throw new Error("fixture objective did not validate");
    const server = await startManifestViewServer({ repository, host: "127.0.0.1", port: 0 });
    try {
      const api = await fetch(server.url + "/api/objectives/" + ids.objective).then((response) => response.json());
      const page = await fetch(server.url + "/objectives/" + ids.objective).then((response) => response.text());
      const embedded = await embeddedHuman(page);
      const apiValues = values(api, [ids.explicit, ids.history, ids.unknown]);
      const pageValues = values(embedded, [ids.explicit, ids.history, ids.unknown]);
      checks.push(check("api_page_parity", JSON.stringify(apiValues) === JSON.stringify(pageValues), "API and embedded page data agree for task-details, Git-history, and unproven fixtures"));
      const allEvidence = Object.values(apiValues).map((item) => item.evidence);
      checks.push(check("safe_public_output", allEvidence.every(evidenceIsSafe), "public creation evidence contains only safe category labels"));
    } finally {
      await server.close();
    }
  } catch {
    checks.push(check("fixture_runtime", false, "the independent TypeScript fixture could not exercise the candidate"));
  } finally {
    await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
  }
  await writeFile(output, JSON.stringify({ checks, errors: [] }, null, 2));
}

await main();
