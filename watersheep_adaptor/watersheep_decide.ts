import { tool } from "@opencode-ai/plugin"

export default tool({
  description: "Ask WaterSheep for an advisory decision. This never executes suggestions and does not replace your generative model.",
  args: {
    state: tool.schema.string().max(32768).describe("Context for the decision"),
    question: tool.schema.string().min(1).max(4096).describe("Decision question"),
    type: tool.schema.enum(["binary", "choice", "score", "multi"]).describe("WaterSheep decision type"),
    options: tool.schema.array(tool.schema.string()).max(255).optional().describe("Ordered labels or score levels; omit for binary"),
  },
  async execute(args) {
    try {
      const child = Bun.spawn(["watersheep-decide"], { stdin: "pipe", stdout: "pipe", stderr: "pipe" })
      child.stdin.write(JSON.stringify(args))
      child.stdin.end()
      const timer = setTimeout(() => child.kill(), 125000)
      try {
        const [output, error, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited])
        if (code !== 0) throw new Error(`decision process failed (${code}): ${error.slice(0, 1000)}`)
        JSON.parse(output)
        return output.trim()
      } finally {
        clearTimeout(timer)
      }
    } catch (error) {
      return JSON.stringify({ ok: false, notice: "Advisory decision only; no execution authority.", error: { code: "bridge_error", message: String(error) } })
    }
  },
})
