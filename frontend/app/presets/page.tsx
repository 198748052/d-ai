"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { Preset } from "@/lib/types";

export default function PresetsPage() {
  const [preset, setPreset] = useState<Preset | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Preset[]>("/api/presets")
      .then((data) => setPreset(data[0] ?? null))
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">改写预设</h1>
        <p className="mt-1 text-sm text-ink-500">
          系统只维护「学术论文」这一个预设。为保证效果稳定，参数已固定，页面只读。
        </p>
      </section>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ["预设名称", preset?.name ?? "学术论文"],
            ["语体", preset?.style ?? "academic"],
            ["改写方式", "规则 + LLM 混合"],
            ["强度", preset?.strength ?? "medium"],
            ["口语化", String(preset?.colloquial ?? 0)],
            ["最大改写轮次", String(preset?.max_rounds ?? 2)],
            [
              "字数比",
              preset
                ? `${preset.length_ratio_min} – ${preset.length_ratio_max}`
                : "0.9 – 1.1",
            ],
            ["保护词", `${preset?.protect_terms.length ?? 0} 个`],
            ["禁用词", `${preset?.banned_words.length ?? 0} 个`],
            ["深度改写", "关闭"],
            ["候选数量", "1 个"],
            ["结构模式", "保持段落"],
          ].map(([label, value]) => (
            <div key={label}>
              <label className="mb-1 block text-xs font-medium text-ink-500">{label}</label>
              <div className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-sm text-ink-600">
                {value}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-ink-400">
          这些参数在服务启动时自动恢复为默认值。需要调整时修改后端默认配置，不再通过 Web 端修改。
        </p>
      </section>
    </div>
  );
}
