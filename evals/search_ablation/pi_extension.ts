/** Trial-local production Loci tools. Load with pi --extension <this file>.
 * Required trusted environment: LOCI_AGENT_REPO, LOCI_AGENT_STORE,
 * LOCI_AGENT_GRAPH_ENRICHMENT=true|false, LOCI_AGENT_PYTHON (absolute executable).
 * Launch cwd must equal LOCI_AGENT_REPO. Use an independent store per trial.
 * Registration adds tools; it never changes Pi's active native tool selection.
 */
import { execFile, type ChildProcess } from "node:child_process";
import { realpathSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  // Capture operator configuration at load time, before any model tool runs.
  const repo = process.env.LOCI_AGENT_REPO;
  const store = process.env.LOCI_AGENT_STORE;
  const graph = process.env.LOCI_AGENT_GRAPH_ENRICHMENT;
  const python = process.env.LOCI_AGENT_PYTHON;
  if (!repo || !store || !python || ![repo, store, python].every(isAbsolute) ||
      !["true", "false"].includes(graph ?? "")) {
    throw new Error("Loci trial requires absolute LOCI_AGENT_REPO/STORE/PYTHON and GRAPH_ENRICHMENT=true|false");
  }
  const root = realpathSync(repo);
  if (root !== realpathSync(process.cwd())) throw new Error("Loci trial repository must equal Pi cwd");
  const bridge = join(dirname(fileURLToPath(import.meta.url)), "agent_loci.py");
  const environment = { ...process.env, LOCI_AGENT_REPO: root, LOCI_AGENT_STORE: store,
    LOCI_AGENT_GRAPH_ENRICHMENT: graph };
  const children = new Set<ChildProcess>();
  const killChildren = () => { for (const child of children) child.kill("SIGKILL"); };
  pi.on("session_start", async () => { process.on("exit", killChildren); });
  pi.on("session_shutdown", async () => {
    const exited = [...children].map(child => new Promise<void>(resolve => child.once("close", () => resolve())));
    killChildren();
    await Promise.all(exited);
    process.off("exit", killChildren);
  });

  async function call(tool: string, arguments_: unknown, signal?: AbortSignal) {
    const packet = await new Promise<any>((resolve, reject) => {
      const child = execFile(python!, [bridge], {
        cwd: root, env: environment, signal, killSignal: "SIGKILL",
        timeout: 120_000, maxBuffer: 4 * 1024 * 1024,
      }, (error, stdout, stderr) => {
        if (error) return reject(new Error(`Loci bridge failed: ${error.message}\n${stderr}`));
        try { resolve(JSON.parse(stdout)); }
        catch { reject(new Error(`Loci bridge returned invalid JSON: ${stdout}\n${stderr}`)); }
      });
      children.add(child);
      child.once("close", () => children.delete(child));
      child.stdin!.on("error", () => {}); // execFile reports spawn/exit failures.
      child.stdin!.end(JSON.stringify({ tool, arguments: arguments_ }));
    });
    // Throwing is Pi's tool-error path; never present a service error as success.
    if (packet.error) throw new Error(JSON.stringify(packet));
    return { content: [{ type: "text" as const, text: JSON.stringify(packet) }], details: packet };
  }

  pi.registerTool(defineTool({
    name: "loci_retrieve", label: "Loci Retrieve",
    description: "Retrieve deterministic bounded static source context from the current repository. Provide a query or up to five exact seed IDs returned earlier. An exact indexed relative file path in query selects that file; other queries select bounded source candidates. Results include source, relationship proof, ambiguity and omissions. Use an incomplete item's source_ref with loci_read to hydrate exact source, or use a node ID as a seed to re-anchor. Relationships are static and non-exhaustive.",
    parameters: Type.Object({
      query: Type.Optional(Type.String({ description: "Source discovery question or indexed relative file path" })),
      seed_ids: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: 5, uniqueItems: true })),
    }, { additionalProperties: false }),
    executionMode: "sequential",
    execute: async (_id, params, signal) => call("loci_retrieve", params, signal),
  }));
  pi.registerTool(defineTool({
    name: "loci_read", label: "Loci Read",
    description: "Expand one exact source extent named by a returned source_ref in the current repository. Pass the handle unchanged. Follow next_source_ref until null to page an incomplete extent. An unknown, expired or stale reference requires fresh loci_retrieve context.",
    parameters: Type.Object({ source_ref: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
    executionMode: "sequential",
    execute: async (_id, params, signal) => call("loci_read", params, signal),
  }));
}
