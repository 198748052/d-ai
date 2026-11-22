"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { MiningCandidate, MiningResponse } from "@/lib/types";

const GROUPS: { key: "lexicon" | "regex" | "structure"; label: string }[] = [
  { key: "lexicon", label: "词汇候选" },
  { key: "regex", label: "句式候选" },
  { key: "structure", label: "结构差异" },
];

function candidateKey(candidate: MiningCandidate): string {
  return `${candidate.kind}:${candidate.pattern}`;
}

export default function MiningPage() {
  const { user, loading } = useAuth();
  const [highTexts, setHighTexts] = useState<string[]>([]);
  const [lowTexts, setLowTexts] = useState<string[]>([]);
  const [highDraft, setHighDraft] = useState("");
  const [lowDraft, setLowDraft] = useState("");
  const [result, setResult] = useState<MiningResponse | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const allCandidates = useMemo(
    () =>
      result
        ? [...result.lexicon, ...result.regex, ...result.structure]
        : [],
    [result]
  );

  const analyze = useCallback(async () => {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const highs = [...highTexts, highDraft].filter((item) => item.trim());
      const lows = [...lowTexts, lowDraft].filter((item) => item.trim());
      if (!highs.length || !lows.length) {
        setError("请同时提供高 AI 率和低 AI 率文章");
        return;
      }
      const data = await apiSend<MiningResponse>("/api/mining/analyze", "POST", {
        high_texts: highs,
        low_texts: lows,
        top_n: 30,
      });
      setResult(data);
      setSelected({});
      setMessage("分析完成，勾选候选后可以加入规则库");
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析失败");
    } finally {
      setBusy(false);
    }
  }, [highTexts, lowTexts, highDraft, lowDraft]);

  const applySelected = useCallback(async () => {
    if (!result) return;
    const candidates = allCandidates.filter((item) => selected[candidateKey(item)]);
    if (!candidates.length) {
      setError("请先勾选要加入规则库的候选");
      return;
    }
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const data = await apiSend<{ imported: number; skipped: number }>(
        "/api/mining/apply",
        "POST",
        { candidates }
      );
      setMessage(`已加入规则库：新增 ${data.imported} 条，跳过 ${data.skipped} 条`);
      setSelected({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入失败");
    } finally {
      setBusy(false);
    }
  }, [result, allCandidates, selected]);

  const addFiles = async (
    files: FileList | null,
    setter: (updater: (prev: string[]) => string[]) => void
  ) => {
    if (!files) return;
    const texts = await Promise.all(Array.from(files).map((file) => file.text()));
    setter((prev) => [...prev, ...texts.filter((text) => text.trim())]);
  };

  if (loading) return null;
  if (!user?.is_admin) {
    return (
      <div className="rounded-xl border border-ink-200 bg-white p-5 text-sm text-ink-600">
        该页面仅管理员可见。
        <Link href="/" className="ml-2 text-accent-700 hover:underline">
          返回工作台
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">规则挖掘</h1>
        <p className="mt-1 text-sm text-ink-500">
          用高 AI 率文章和低 AI 率文章做对比，统计高频表达、句式和结构差异，生成候选规则。候选需要人工确认后再加入规则库。
        </p>
      </section>

      {message && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {message}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        {[
          {
            title: "高 AI 率文章",
            texts: highTexts,
            setTexts: setHighTexts,
            draft: highDraft,
            setDraft: setHighDraft,
          },
          {
            title: "低 AI 率文章",
            texts: lowTexts,
            setTexts: setLowTexts,
            draft: lowDraft,
            setDraft: setLowDraft,
          },
        ].map((group) => (
          <div
            key={group.title}
            className="rounded-xl border border-ink-200 bg-white p-5 shadow-card"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink-900">{group.title}</h2>
              <span className="text-xs text-ink-400">{group.texts.length} 篇</span>
            </div>
            <input
              type="file"
              accept=".txt,.md,text/plain"
              multiple
              onChange={(e) => addFiles(e.target.files, group.setTexts)}
              className="mt-2 block w-full text-xs text-ink-600"
            />
            <textarea
              value={group.draft}
              onChange={(e) => group.setDraft(e.target.value)}
              placeholder="也可以直接粘贴一篇文本"
              className="mt-2 h-40 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-2 text-sm leading-6"
            />
            {group.texts.length > 0 && (
              <button
                type="button"
                onClick={() => group.setTexts(() => [])}
                className="mt-1 text-xs text-ink-400 hover:text-ink-700"
              >
                清空已上传文件
              </button>
            )}
          </div>
        ))}
      </section>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={analyze}
          disabled={busy}
          className="rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
        >
          {busy ? "分析中…" : "开始分析"}
        </button>
        {result && (
          <button
            type="button"
            onClick={applySelected}
            disabled={busy}
            className="rounded-lg border border-accent-200 px-4 py-2 text-sm text-accent-700 hover:bg-accent-50 disabled:opacity-60"
          >
            加入规则库
          </button>
        )}
      </div>

      {result && (
        <section className="space-y-4">
          <div className="rounded-xl border border-ink-200 bg-white p-4 text-xs text-ink-600 shadow-card">
            <div className="flex flex-wrap gap-4">
              <span>高 AI 篇数 <strong className="text-ink-900">{String(result.summary.high_count ?? "-")}</strong></span>
              <span>低 AI 篇数 <strong className="text-ink-900">{String(result.summary.low_count ?? "-")}</strong></span>
              <span>高 AI 字数 <strong className="text-ink-900">{String(result.summary.high_chars ?? "-")}</strong></span>
              <span>低 AI 字数 <strong className="text-ink-900">{String(result.summary.low_chars ?? "-")}</strong></span>
            </div>
            <p className="mt-2 text-ink-400">{String(result.summary.message ?? "")}</p>
          </div>

          {GROUPS.map((group) => {
            const items = result[group.key];
            if (!items.length) return null;
            return (
              <div key={group.key} className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
                <h2 className="text-sm font-semibold text-ink-900">{group.label}</h2>
                <div className="mt-3 space-y-2">
                  {items.map((candidate) => {
                    const key = candidateKey(candidate);
                    return (
                      <label
                        key={key}
                        className="flex cursor-pointer items-start gap-3 rounded-lg border border-ink-100 px-3 py-2 text-xs hover:bg-ink-50"
                      >
                        <input
                          type="checkbox"
                          checked={!!selected[key]}
                          onChange={(e) =>
                            setSelected((prev) => ({ ...prev, [key]: e.target.checked }))
                          }
                          className="mt-0.5 accent-accent-600"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="rounded bg-ink-100 px-1.5 py-0.5 text-ink-800">
                              {candidate.pattern}
                            </code>
                            <span className="text-ink-400">
                              高 {candidate.high_per_1000}/千字 · 低 {candidate.low_per_1000}/千字 · lift{" "}
                              {candidate.lift}
                            </span>
                          </div>
                          <p className="mt-1 text-ink-600">{candidate.note}</p>
                          {candidate.examples.length > 0 && (
                            <ul className="mt-1 list-inside list-disc text-ink-400">
                              {candidate.examples.map((example, index) => (
                                <li key={index} className="truncate">
                                  {example}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
