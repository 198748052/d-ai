import type { RewriteJobStatus, RewritePayload, RewriteResponse } from "./types";

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.message === "string") return data.message;
    return JSON.stringify(data);
  } catch {
    return `请求失败（${res.status}）`;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown
): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return undefined as T;
  return res.json();
}

interface StreamHandlers {
  onParagraph: (paragraph: RewriteResponse["paragraphs"][number]) => void;
  onDone: (response: RewriteResponse) => void;
  onError: (message: string) => void;
}

function parseEventChunk(chunk: string): { event: string; data: string } | null {
  const lines = chunk.split("\n");
  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
}

export async function streamRewrite(
  payload: RewritePayload,
  handlers: StreamHandlers
): Promise<void> {
  const res = await fetch("/api/rewrite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    throw new Error(await parseError(res));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const parsed = parseEventChunk(part);
      if (!parsed) continue;
      try {
        const data = JSON.parse(parsed.data);
        if (parsed.event === "paragraph") handlers.onParagraph(data);
        else if (parsed.event === "done") handlers.onDone(data);
        else if (parsed.event === "error") handlers.onError(data.message ?? "改写失败");
      } catch {
        // ignore malformed event
      }
    }
  }
}

export async function startRewriteJob(
  payload: RewritePayload
): Promise<{ job_id: string; db_id: number; total: number }> {
  const res = await fetch("/api/rewrite/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchRewriteJob(jobId: string): Promise<RewriteJobStatus> {
  const res = await fetch(`/api/rewrite/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function exportDocument(
  text: string,
  format: "txt" | "md" | "docx",
  filename = "改写结果"
): Promise<void> {
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, format, filename }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filename}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
