import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Inspector } from "./Inspector";
import type { EventItem, GraphNode, RunOverview } from "../../types";

function event(extra: Partial<EventItem> = {}): EventItem {
  return {
    id: 7, seq: 1, timestamp: "2026-10-23T10:00:00", step_id: "step-abc", parent_step_id: "parent-xyz", actor: "otlp",
    type: "tool.succeeded", summary: "get_weather finished", status: "succeeded", duration_ms: 120, provider: null,
    model: null, tool_name: "get_weather", artifact_refs: [], error_code: null, payload_hash: null, payload_full: null,
    metadata: {}, ...extra,
  };
}

const decision: GraphNode = {
  id: "decision-eac540a0", type: "decision", label: "Retried lookup", position: { x: 480, y: 60 },
  data: { kind: "retry", summary: "The lookup failed once, so it was tried again", decisionId: 3, evidenceIds: [7], outcome: "retry" },
};

describe("Inspector", () => {
  it("shows what a decision means and hides ids and coordinates until asked", () => {
    render(<Inspector overview={null} selectedEvent={null} selectedGraphNode={decision} events={[event()]} />);

    expect(screen.getByText("Retried lookup")).toBeInTheDocument();
    expect(screen.getByText("The lookup failed once, so it was tried again")).toBeInTheDocument();
    expect(screen.getByText("Retried")).toBeInTheDocument();
    expect(screen.getByText("Tool finished")).toBeInTheDocument();
    // The raw identifiers are folded away.
    expect(screen.getByText("decision-eac540a0")).not.toBeVisible();
  });

  it("opens the event a decision is based on", () => {
    const onSelectEvent = vi.fn();
    render(<Inspector overview={null} selectedEvent={null} selectedGraphNode={decision} events={[event()]} onSelectEvent={onSelectEvent} />);

    fireEvent.click(screen.getByText("Tool finished"));
    expect(onSelectEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it("shows an event by what happened, with its ids folded away", () => {
    render(<Inspector overview={null} selectedEvent={event()} />);

    expect(screen.getByText("Tool finished")).toBeInTheDocument();
    expect(screen.getByText("get_weather finished")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByText("step-abc")).not.toBeVisible();
  });

  it("shows the error of a failed event", () => {
    render(<Inspector overview={null} selectedEvent={event({ type: "tool.failed", status: "failed", error_code: "ValueError" })} />);

    expect(screen.getByText("Error: ValueError")).toBeInTheDocument();
  });

  describe("a model call", () => {
    const call = (payload: unknown) => event({ type: "llm.completed", summary: "Model responded via openai", tool_name: null, payload_full: payload as EventItem["payload_full"] });

    it("shows what the model was asked and what it answered", () => {
      const content = {
        input_messages: [
          { role: "system", parts: [{ type: "text", content: "Eres un analista de planta." }] },
          { role: "user", parts: [{ type: "text", content: "¿Por qué bajó el OEE?" }] },
          { role: "tool", parts: [{ type: "tool_call_response", id: "t1", name: "consultar_oee", result: { disponibilidad: "78 %" } }] },
        ],
        output_messages: [
          { role: "assistant", parts: [{ type: "tool_call", id: "t2", name: "consultar_paradas", arguments: { linea: 2 } }, { type: "text", content: "Reviso las paradas." }] },
        ],
      };

      render(<Inspector overview={null} selectedEvent={call(content)} />);

      expect(screen.getByText("Prompt")).toBeInTheDocument();
      expect(screen.getByText("Eres un analista de planta.")).toBeInTheDocument();
      expect(screen.getByText("¿Por qué bajó el OEE?")).toBeInTheDocument();
      expect(screen.getByText('consultar_oee → {"disponibilidad":"78 %"}')).toBeInTheDocument();
      expect(screen.getByText("Response")).toBeInTheDocument();
      expect(screen.getByText(/consultar_paradas\(linea=2\)/)).toBeInTheDocument();
      expect(screen.getByText("System")).toBeInTheDocument();
      expect(screen.getByText("Tool result")).toBeInTheDocument();
    });

    it("says why there is nothing to show instead of staying silent", () => {
      render(<Inspector overview={null} selectedEvent={call(null)} />);

      expect(screen.getByText("Prompt and response")).toBeInTheDocument();
      expect(screen.getByText(/Not captured/)).toBeInTheDocument();
      expect(screen.getByText("TRACE_AGENT_CAPTURE_FULL_PAYLOADS")).toBeInTheDocument();
    });

    it("says nothing on the started row of a call, which has no content yet", () => {
      render(<Inspector overview={null} selectedEvent={event({ type: "llm.started", summary: "Model request to m", tool_name: null })} />);

      expect(screen.queryByText("Prompt and response")).not.toBeInTheDocument();
    });
  });

  describe("a run", () => {
    const overview = (extra: Record<string, unknown> = {}) =>
      ({
        agent_name: "oee-Q01", goal: "¿Por qué bajó el OEE?", status: "completed", provider: "openai", model: "m", started_at: "2026-10-23T10:00:00",
        tool_count: 3, error_count: 0, retry_count: 0, final_output_summary: "El OEE bajó por…", flags: [],
        execution: { duration_ms: 5000, model_turn_count: 2, command_count: 2, token_usage: { total_tokens: 1500 } },
        ...extra,
      }) as unknown as RunOverview

    it("puts the whole final output first, formatted and copiable", () => {
      const ended = event({ id: 9, type: "run.completed", payload_full: { final_output: { recomendacion: "Revisar la envasadora", paradas: 4 } } })

      render(<Inspector overview={overview()} selectedEvent={null} events={[ended]} />)

      expect(screen.getByText("Final output")).toBeInTheDocument()
      expect(screen.getByText(/Revisar la envasadora/)).toBeInTheDocument()
      expect(screen.getAllByRole("button", { name: "Copy to clipboard" }).length).toBeGreaterThan(0)
    })

    it("falls back to the summary when the whole output was not kept", () => {
      render(<Inspector overview={overview()} selectedEvent={null} events={[]} />)

      expect(screen.getByText("Final output")).toBeInTheDocument()
      expect(screen.getByText("El OEE bajó por…")).toBeInTheDocument()
    })

    it("says why a failed run failed", () => {
      render(<Inspector overview={overview({ status: "failed", final_output_summary: "No activity for 60 minutes" })} selectedEvent={null} events={[]} />)

      expect(screen.getByText("Why it failed")).toBeInTheDocument()
    })

    it("counts tools and commands as steps, with the breakdown one hover away", () => {
      render(<Inspector overview={overview()} selectedEvent={null} events={[]} />)

      expect(screen.getByText("Steps")).toBeInTheDocument()
      expect(screen.getByText("5")).toBeInTheDocument()
      expect(screen.getByText("Steps").closest("div[title]")).toHaveAttribute("title", "3 tool calls, 2 commands")
      expect(screen.queryByText("Commands")).not.toBeInTheDocument()
    })
  })

  describe("the result of a tool", () => {
    it("shows the whole output formatted when it was kept", () => {
      const done = event({ payload_full: { output_summary: "{...}", output: { veredicto: "descartado", ventana: [60, 120] } } })

      render(<Inspector overview={null} selectedEvent={done} />)

      expect(screen.getByText("Result")).toBeInTheDocument()
      expect(screen.getAllByText(/descartado/).length).toBeGreaterThan(0)
    })

    it("formats the summary when it is JSON, and shows it as text when it is not", () => {
      const { unmount } = render(<Inspector overview={null} selectedEvent={event({ payload_full: { output_summary: '{"causa":"avería"}' } })} />)
      // The formatted result is on view; the raw payload under "Technical details" repeats it, folded away.
      expect(screen.getAllByText(/causa/).some((node) => node.checkVisibility?.() ?? true)).toBe(true)
      expect(screen.getByText("Result")).toBeInTheDocument()
      unmount()

      render(<Inspector overview={null} selectedEvent={event({ payload_full: { output_summary: "Sunny in Madrid" } })} />)
      expect(screen.getByText("Sunny in Madrid", { selector: "p" })).toBeInTheDocument()
    })
  })

  describe("the status of a step", () => {
    it("a 'started' event of a step that ended does not say it is still running", () => {
      const started = event({ id: 1, type: "llm.started", status: "running", step_id: "l1", tool_name: null });
      const finished = event({ id: 2, type: "llm.completed", status: "succeeded", step_id: "l1", tool_name: null });

      render(<Inspector overview={null} selectedEvent={started} events={[started, finished]} />);

      expect(screen.getByText("Succeeded")).toBeInTheDocument();
      expect(screen.queryByText("Running")).not.toBeInTheDocument();
    });

    it("a step that has not ended is running", () => {
      const started = event({ id: 1, type: "llm.started", status: "running", step_id: "l1", tool_name: null });

      render(<Inspector overview={null} selectedEvent={started} events={[started]} />);

      expect(screen.getByText("Running")).toBeInTheDocument();
    });
  });

  it("shows what an agent answered when its run ended, formatted", () => {
    const ended = event({ type: "chain.completed", tool_name: null, metadata: { output_summary: '{"hay_defecto": true, "evidencia": "x"}' } });

    render(<Inspector overview={null} selectedEvent={ended} />);

    expect(screen.getByText("Agent output")).toBeInTheDocument();
    expect(screen.getAllByText(/hay_defecto/).length).toBeGreaterThan(0);
  });

  describe("a long message of a model call", () => {
    const long = "Eres un analista de planta. ".repeat(60);
    const call = event({
      type: "llm.completed", summary: "Model responded via openai", tool_name: null,
      payload_full: { input_messages: [{ role: "system", parts: [{ type: "text", content: long }] }], output_messages: [] } as EventItem["payload_full"],
    });

    it("is shortened, with a button to read it whole (no inner scroll box to trap the wheel)", () => {
      render(<Inspector overview={null} selectedEvent={call} />);

      expect(screen.getByText(/^Eres un analista de planta\./).textContent!.length).toBeLessThan(long.length);
      fireEvent.click(screen.getByRole("button", { name: /Show all \(1,680 characters\)/ }));
      expect(screen.getByText(/^Eres un analista de planta\./).textContent).toBe(long);
      fireEvent.click(screen.getByRole("button", { name: "Show less" }));
      expect(screen.getByText(/^Eres un analista de planta\./).textContent!.length).toBeLessThan(long.length);
    });
  });

  describe("technical details", () => {
    it("keeps the ids for debugging, each with a button to copy it", () => {
      render(<Inspector overview={null} selectedEvent={event()} />)

      expect(screen.getByText("step-abc")).not.toBeVisible()
      expect(screen.getByRole("button", { name: "Copy Step ID" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Copy Parent step" })).toBeInTheDocument()
    })

    it("does not repeat the metadata the inspector already shows, only what is left", () => {
      const withMeta = event({ metadata: { prompt_tokens: 10, completion_tokens: 5, requested_tools: [], custom_flag: "x" } })

      render(<Inspector overview={null} selectedEvent={withMeta} />)

      expect(screen.getByText("Other metadata")).toBeInTheDocument()
      expect(screen.getByText(/custom_flag/)).toBeInTheDocument()
      expect(screen.queryByText(/prompt_tokens/)).not.toBeInTheDocument()
    })

    it("has no metadata section when everything in it is already shown", () => {
      render(<Inspector overview={null} selectedEvent={event({ metadata: { prompt_tokens: 10, completion_tokens: 5 } })} />)

      expect(screen.queryByText("Other metadata")).not.toBeInTheDocument()
    })
  })

  it("finds the arguments of a finished tool in the event that started it", () => {
    const started = event({ id: 1, type: "tool.started", payload_full: { args: { parametro: "temp_molde_C" } } });
    const finished = event({ id: 2, type: "tool.succeeded" });

    render(<Inspector overview={null} selectedEvent={finished} events={[started, finished]} />);

    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText(/temp_molde_C/)).toBeInTheDocument();
  });
});
