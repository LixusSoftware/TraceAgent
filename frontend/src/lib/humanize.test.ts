import { describe, expect, it } from "vitest";
import {
  argsSummary,
  commandTitle,
  decisionKindLabel,
  describeMessages,
  eventNodeLabel,
  eventTitle,
  groupTitle,
  outcomeLabel,
  resultFull,
  resultSummary,
  statusLabel,
  stepCounts,
  stepNodeLabel,
  tokensLabel,
  truncate,
} from "./humanize";
import type { EventItem, TimelineGroup } from "../types";

function event(type: string, extra: Partial<EventItem> = {}): EventItem {
  return {
    id: 1, seq: 1, timestamp: "2026-10-23T10:00:00", step_id: "s", parent_step_id: null, actor: "otlp", type,
    summary: "", status: null, duration_ms: null, provider: null, model: null, tool_name: null, artifact_refs: [],
    error_code: null, payload_hash: null, payload_full: null, metadata: {}, ...extra,
  };
}

function group(label: string, events: EventItem[], toolName: string | null = null): TimelineGroup {
  return {
    step_id: "s", label, status: "succeeded", step_type: "run", tool_name: toolName, call_id: null, parent_step_id: null,
    event_count: events.length, started_at: "", ended_at: "", duration_ms: null, events,
  };
}

describe("eventTitle", () => {
  it("uses plain names for known events", () => {
    expect(eventTitle("llm.completed")).toBe("Model response");
    expect(eventTitle("tool.failed")).toBe("Tool failed");
    expect(eventTitle("chain.started")).toBe("Agent started");
    expect(eventTitle("run.completed")).toBe("Run finished");
  });

  it("makes an unknown type readable instead of showing it raw", () => {
    expect(eventTitle("guardrail.blocked")).toBe("Guardrail blocked");
    expect(eventTitle("custom_thing")).toBe("Custom thing");
  });
});

describe("labels", () => {
  it("names decision kinds and outcomes", () => {
    expect(decisionKindLabel("tool_choice")).toBe("Tool choice");
    expect(decisionKindLabel("retry")).toBe("Retry");
    expect(outcomeLabel("requested")).toBe("Requested");
    expect(outcomeLabel("retry")).toBe("Retried");
    expect(outcomeLabel(null)).toBe("—");
  });

  it("names statuses", () => {
    expect(statusLabel("succeeded")).toBe("Succeeded");
    expect(statusLabel("failed")).toBe("Failed");
    expect(statusLabel(null)).toBe("—");
  });
});

describe("groupTitle", () => {
  it("keeps the tool name for tools", () => {
    expect(groupTitle(group("get_weather", [event("tool.started"), event("tool.succeeded")], "get_weather"))).toBe("get_weather");
  });

  it("calls an agent group an agent run, with the agent's name", () => {
    const events = [event("chain.started", { metadata: { agent_name: "weather-agent" } }), event("chain.completed")];
    expect(groupTitle(group("chain.completed", events))).toBe("Agent run · weather-agent");
    expect(groupTitle(group("chain.completed", [event("chain.started")]))).toBe("Agent run");
  });

  it("calls a model group a model call, with the model", () => {
    const events = [event("llm.started", { model: "gpt-4o" }), event("llm.completed")];
    expect(groupTitle(group("llm.completed", events))).toBe("Model call · gpt-4o");
  });

  it("describes the start and end of a run", () => {
    expect(groupTitle(group("run.started", [event("run.started")]))).toBe("Run started");
    expect(groupTitle(group("run.completed", [event("run.completed")]))).toBe("Run finished");
  });

  it("keeps the server label for commands and files, which are already readable", () => {
    expect(groupTitle(group("src/app.py", [event("file.written")]))).toBe("src/app.py");
  });
});

describe("commandTitle / truncate", () => {
  it("uses the first comment of a script, which says what the step does", () => {
    const script = "python -c \n# Leer las paradas de la línea 2\nimport json\nlineas = leer()\nprint(lineas)";

    expect(commandTitle(script)).toBe("Leer las paradas de la línea 2");
  });

  it("without a comment, uses the first line that is not an import", () => {
    expect(commandTitle("python -c \nimport json\nfrom os import path\nlineas = leer()\nprint(lineas)")).toBe("lineas = leer()");
  });

  it("falls back to the first line when everything is an import", () => {
    expect(commandTitle("python -c import json")).toBe("import json");
  });

  it("leaves an ordinary command as it is and cuts a long one", () => {
    expect(commandTitle("pytest -q packages/sdk")).toBe("pytest -q packages/sdk");
    const long = commandTitle(`python3 -c ${"x = 1; ".repeat(40)}`);
    expect(long.length).toBe(72);
    expect(long.endsWith("…")).toBe(true);
  });

  it("collapses whitespace when it truncates", () => {
    expect(truncate("a   b\n\n c", 20)).toBe("a b c");
    expect(truncate("abcdefghij", 5)).toBe("abcd…");
  });

  it("titles a command group with its short title", () => {
    const events = [event("command.started"), event("command.failed")];

    expect(groupTitle(group("python -c \nvalor = 1\nprint(valor)", events))).toBe("valor = 1");
    expect(groupTitle(group("python -c # Sumar\nvalor = 1", events))).toBe("Sumar");
  });
});

describe("argsSummary", () => {
  const toolGroup = (started: EventItem) => group("search", [started, event("tool.succeeded")], "search");

  it("lists the arguments as name=value", () => {
    const started = event("tool.started", { payload_full: { args: { parametro: "temp_molde_C", limite: 80, activo: true } } });

    expect(argsSummary(toolGroup(started))).toBe("parametro=temp_molde_C, limite=80, activo=true");
  });

  it("falls back to the stored summary when the full arguments were not kept", () => {
    const started = event("tool.started", { metadata: { args_summary: '{"q": "pasta", "n": 2}' } });

    expect(argsSummary(toolGroup(started))).toBe("q=pasta, n=2");
  });

  it("reads a summary that was cut in the middle", () => {
    const started = event("tool.started", { metadata: { args_summary: '{"q": "pasta fresca de la ca...' } });

    expect(argsSummary(toolGroup(started))).toContain("pasta fresca");
  });

  it("is empty for a tool without arguments or a group that is not a tool", () => {
    expect(argsSummary(toolGroup(event("tool.started", { payload_full: { args: {} } })))).toBeNull();
    expect(argsSummary(group("run.started", [event("run.started")]))).toBeNull();
  });

  it("cuts a long list of arguments", () => {
    const started = event("tool.started", { payload_full: { args: { texto: "x".repeat(300) } } });

    expect(argsSummary(toolGroup(started), 40)?.length).toBe(40);
  });
});

describe("stepCounts", () => {
  const tool = (id: string) => event("tool.succeeded", { step_id: id })
  const command = (id: string, parent: string | null) => event("command.succeeded", { step_id: id, parent_step_id: parent })

  it("does not count again a command that a tool records from inside itself", () => {
    const events = [tool("t1"), tool("t2"), command("c1", "t1"), command("c2", "t2")]

    expect(stepCounts(events, 2, 2)).toEqual({ steps: 2, nested: 2 })
  })

  it("counts a command of its own as a step", () => {
    const events = [tool("t1"), command("c1", "t1"), command("c2", null), command("c3", "run")]

    expect(stepCounts(events, 1, 3)).toEqual({ steps: 3, nested: 1 })
  })

  it("counts a command once, however many events it has", () => {
    const events = [tool("t1"), event("command.started", { step_id: "c1", parent_step_id: "t1" }), command("c1", "t1")]

    expect(stepCounts(events, 1, 1)).toEqual({ steps: 1, nested: 1 })
  })

  it("falls back to the plain total while the events are not there yet", () => {
    expect(stepCounts([], 3, 2)).toEqual({ steps: 5, nested: 0 })
  })
})

describe("stepNodeLabel", () => {
  it("names a tool by the tool, a model call and an agent by what they are", () => {
    expect(stepNodeLabel("tool.succeeded", { stepKind: "tool", toolName: "comprobar" })).toBe("comprobar")
    expect(stepNodeLabel("llm.completed", { stepKind: "llm" })).toBe("Model call")
    expect(stepNodeLabel("chain.completed", { stepKind: "chain" })).toBe("Agent run")
  })

  it("titles a command by its first comment", () => {
    expect(stepNodeLabel("command.succeeded", { stepKind: "command", command: "python -c \n# Leer las paradas\nprint(1)" })).toBe("Leer las paradas")
  })

  it("keeps the event title for anything else", () => {
    expect(stepNodeLabel("run.completed", { stepKind: "run" })).toBe("Run finished")
    expect(stepNodeLabel("tool.succeeded", {})).toBe("Tool finished")
  })
})

describe("resultSummary", () => {
  const toolGroup = (...events: EventItem[]) => group("lookup", events, "lookup");

  it("is the summary of what the tool returned", () => {
    expect(resultSummary(toolGroup(event("tool.started"), event("tool.succeeded", { summary: "causa: avería" })))).toBe("causa: avería");
  });

  it("says why a tool failed", () => {
    expect(resultSummary(toolGroup(event("tool.started"), event("tool.failed", { summary: "tag no encontrado" })))).toBe("failed: tag no encontrado");
  });

  it("has nothing to say when the tool returned no output, or has not finished", () => {
    expect(resultSummary(toolGroup(event("tool.started"), event("tool.succeeded", { summary: "lookup completed." })))).toBeNull();
    expect(resultSummary(toolGroup(event("tool.started")))).toBeNull();
  });

  it("writes the whole output as key=value pairs in the order the tool gave them", () => {
    const output = { parametro: "temp_molde_C", fuera_de_ventana_pct: 100, veredicto: "causa" }

    expect(resultSummary(toolGroup(event("tool.succeeded", { payload_full: { output } })))).toBe("parametro=temp_molde_C, fuera_de_ventana_pct=100, veredicto=causa")
  })

  it("shortens each value, so a long list does not push the decisive key out of the line", () => {
    const output = { ventana: Array.from({ length: 50 }, (_, i) => i + 0.25), veredicto: "causa" }

    const summary = resultSummary(toolGroup(event("tool.succeeded", { payload_full: { output } })))

    expect(summary).toContain("veredicto=causa")
    expect(summary!.length).toBeLessThan(80)
  })

  it("writes a plain output as it is, and the whole result in full for the hover", () => {
    const group = toolGroup(event("tool.succeeded", { payload_full: { output: "Sunny in Madrid" } }))
    expect(resultSummary(group)).toBe("Sunny in Madrid")

    const whole = toolGroup(event("tool.succeeded", { payload_full: { output: { a: 1, b: [1, 2] } } }))
    expect(resultFull(whole)).toBe(JSON.stringify({ a: 1, b: [1, 2] }, null, 2))
  })

  it("falls back to the summary for the hover when the whole output was not kept", () => {
    expect(resultFull(toolGroup(event("tool.succeeded", { summary: "3 results" })))).toBe("3 results")
  })

  it("cuts a long result", () => {
    expect(resultSummary(toolGroup(event("tool.succeeded", { summary: "x".repeat(300) })), 40)?.length).toBe(40);
  });
});

describe("describeMessages", () => {
  it("reads text, tool calls and tool results of the GenAI shape", () => {
    const messages = describeMessages([
      { role: "user", parts: [{ type: "text", content: "hola" }] },
      { role: "assistant", parts: [{ type: "tool_call", name: "buscar", arguments: { q: "pasta", n: 2 } }] },
      { role: "tool", parts: [{ type: "tool_call_response", name: "buscar", result: "dos resultados" }] },
    ]);

    expect(messages).toEqual([
      { role: "user", label: "User", text: "hola" },
      { role: "assistant", label: "Assistant", text: "buscar(q=pasta, n=2)" },
      { role: "tool", label: "Tool result", text: "buscar → dos resultados" },
    ]);
  });

  it("accepts plain content messages and ignores what it cannot read", () => {
    expect(describeMessages([{ role: "user", content: "hola" }, null, { role: "user" }, 3])).toEqual([{ role: "user", label: "User", text: "hola" }]);
    expect(describeMessages(undefined)).toEqual([]);
    expect(describeMessages({ role: "user" })).toEqual([]);
  });

  it("names a part it does not know instead of dropping the message", () => {
    expect(describeMessages([{ role: "user", parts: [{ type: "image" }] }])[0].text).toBe("[image]");
  });
});

describe("eventNodeLabel / tokensLabel", () => {
  it("adds the tool to a graph node", () => {
    expect(eventNodeLabel("tool.succeeded", "get_weather")).toBe("Tool finished · get_weather");
    expect(eventNodeLabel("llm.completed", null)).toBe("Model response");
  });

  it("formats tokens only when the event has them", () => {
    expect(tokensLabel(event("llm.completed", { metadata: { prompt_tokens: 242, completion_tokens: 41 } }))).toBe("242 in · 41 out");
    expect(tokensLabel(event("tool.succeeded"))).toBeNull();
  });
});
