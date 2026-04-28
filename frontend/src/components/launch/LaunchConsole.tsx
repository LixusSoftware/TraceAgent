import { useState } from "react";
import { Play, ChevronDown, ChevronRight, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "../../api";

interface LaunchConsoleProps {
  onLaunch?: () => void;
}

export function LaunchConsole({ onLaunch }: LaunchConsoleProps) {
  const [agentName, setAgentName] = useState("");
  const [goal, setGoal] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentName.trim() || !goal.trim()) return;

    setLoading(true);
    setNotice(null);
    try {
      const metadata: Record<string, unknown> = {};
      if (provider.trim()) metadata.provider = provider.trim();
      if (model.trim()) metadata.model = model.trim();
      if (systemPrompt.trim()) metadata.system_prompt = systemPrompt.trim();

      await api.createRun({
        agent_name: agentName.trim(),
        goal: goal.trim(),
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      });

      setNotice({ type: "success", message: `Run started for agent "${agentName}"` });
      setAgentName("");
      setGoal("");
      setProvider("");
      setModel("");
      setSystemPrompt("");
      onLaunch?.();
    } catch {
      setNotice({ type: "error", message: "Failed to start run. Check backend connection." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <form onSubmit={handleSubmit} className="space-y-2">
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted block mb-1">
              Agent Name
            </label>
            <input
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="e.g. coding-agent"
              className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent placeholder:text-muted"
              required
            />
          </div>
          <div className="flex-1">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted block mb-1">
              Provider
            </label>
            <input
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              placeholder="e.g. openai"
              className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent placeholder:text-muted"
            />
          </div>
          <div className="flex-1">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted block mb-1">
              Model
            </label>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o"
              className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent placeholder:text-muted"
            />
          </div>
        </div>

        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted block mb-1">
            User Prompt / Goal
          </label>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Describe the task..."
            rows={2}
            className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent placeholder:text-muted resize-none"
            required
          />
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowSystemPrompt((v) => !v)}
            className="flex items-center gap-1 text-[10px] text-muted hover:text-text transition-colors"
          >
            {showSystemPrompt ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            System Prompt
          </button>
          {showSystemPrompt && (
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Optional system prompt..."
              rows={2}
              className="w-full text-xs bg-bg border border-line rounded-md px-2 py-1.5 focus:outline-none focus:border-accent placeholder:text-muted resize-none mt-1"
            />
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-md bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            {loading ? "Launching..." : "EXEC"}
          </button>
        </div>
      </form>

      {notice && (
        <div
          className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${
            notice.type === "success"
              ? "bg-accent/10 text-accent border-accent/20"
              : "bg-danger/10 text-danger border-danger/20"
          }`}
        >
          {notice.type === "success" ? (
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          ) : (
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          )}
          {notice.message}
        </div>
      )}
    </div>
  );
}
