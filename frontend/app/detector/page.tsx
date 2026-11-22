"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type {
  CalibrationResult,
  DetectorCluster,
  DetectorFeedback,
  DetectorImportResult,
  DetectorJob,
} from "@/lib/types";

function formatTime(value: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN");
}

export default function DetectorPage() {
  const { user, loading } = useAuth();
  const [jobs, setJobs] = useState<DetectorJob[]>([]);
  const [feedback, setFeedback] = useState<DetectorFeedback[]>([]);
  const [calibration, setCalibration] = useState<CalibrationResult | null>(null);
  const [clusters, setClusters] = useState<DetectorCluster[]>([]);
  const [jobId, setJobId] = useState("");
  const [detector, setDetector] = useState("知网 AIGC");
  const [version, setVersion] = useState("");
  const [scoreBefore, setScoreBefore] = useState("");
  const [scoreAfter, setScoreAfter] = useState("");
  const [redSentences, setRedSentences] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [importText, setImportText] = useState("");

  const load = useCallback(async () => {
    try {
      const [jobRows, feedbackRows, calibrationResult, clusterRows] = await Promise.all([
        apiGet<DetectorJob[]>("/api/detector/jobs?limit=30"),
        apiGet<DetectorFeedback[]>("/api/detector/feedback?limit=50"),
        apiGet<CalibrationResult>("/api/detector/calibration"),
        apiGet<DetectorCluster[]>("/api/detector/clusters"),
      ]);
      setJobs(jobRows);
      setFeedback(feedbackRows);
      setCalibration(calibrationResult);
      setClusters(clusterRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) {
      load();
    }
  }, [user, load]);

  const submit = useCallback(async () => {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await apiSend<DetectorFeedback>("/api/detector/feedback", "POST", {
        job_id: jobId ? Number(jobId) : undefined,
        detector,
        detector_version: version,
        score_before: Number(scoreBefore || 0),
        score_after: Number(scoreAfter || 0),
        red_sentences: redSentences
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        notes,
      });
      setMessage("反馈已保存");
      setRedSentences("");
      setNotes("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }, [jobId, detector, version, scoreBefore, scoreAfter, redSentences, notes, load]);

  const runCalibration = useCallback(async () => {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await apiSend<CalibrationResult>(
        "/api/detector/calibration",
        "POST"
      );
      setCalibration(result);
      setMessage(
        result.sample_count >= 20
          ? "校准完成，候选选择权重已更新"
          : "样本不足 20 条，本次只计算相关性"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "校准失败");
    } finally {
      setBusy(false);
    }
  }, []);

  const handleImport = useCallback(async () => {
    if (!importText.trim()) {
      setError("请先选择或粘贴 CSV 内容");
      return;
    }
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await apiSend<DetectorImportResult>(
        "/api/detector/feedback/import",
        "POST",
        { csv: importText }
      );
      setMessage(`导入完成：新增 ${result.imported} 条，跳过 ${result.skipped} 条`);
      setImportText("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
    }
  }, [importText, load]);

  const handleExport = useCallback(async () => {
    setError("");
    try {
      const res = await fetch("/api/detector/feedback/export");
      if (!res.ok) throw new Error("导出失败");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "detector-feedback.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  }, []);

  if (loading) return null;
  if (!user?.is_admin) {
    return (
      <div className="rounded-xl border border-ink-200 bg-white p-5 text-sm text-ink-600">
        该页面仅管理员可见。<Link href="/" className="text-accent-700 hover:underline">返回工作台</Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h1 className="text-lg font-semibold tracking-tight text-ink-900">检测器反馈与校准</h1>
        <p className="mt-1 text-sm text-ink-500">
          记录真实送检结果，计算代理指标与检测分的相关性，用反馈校准候选选择权重。
        </p>
        <p className="mt-2 text-xs text-ink-400">
          建议至少积累 20 条同检测器、同版本的反馈，再做权重校准。
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

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">录入反馈</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="text-xs text-ink-600">
            关联任务
            <select
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-200 bg-white px-2 py-2 text-sm"
            >
              <option value="">不关联</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  #{job.id} · {formatTime(job.created_at)} · {job.preview.slice(0, 30)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-ink-600">
            检测器
            <input
              value={detector}
              onChange={(e) => setDetector(e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-2 text-sm"
            />
          </label>
          <label className="text-xs text-ink-600">
            版本/送检批次
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="例如 2026-11"
              className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-2 text-sm"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-ink-600">
              改写前分数
              <input
                value={scoreBefore}
                onChange={(e) => setScoreBefore(e.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-2 text-sm"
              />
            </label>
            <label className="text-xs text-ink-600">
              改写后分数
              <input
                value={scoreAfter}
                onChange={(e) => setScoreAfter(e.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-2 text-sm"
              />
            </label>
          </div>
        </div>
        <label className="mt-3 block text-xs text-ink-600">
          标红句子（每行一句）
          <textarea
            value={redSentences}
            onChange={(e) => setRedSentences(e.target.value)}
            className="mt-1 h-24 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-2 text-sm"
          />
        </label>
        <label className="mt-3 block text-xs text-ink-600">
          备注
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="mt-1 h-16 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-2 text-sm"
          />
        </label>
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="mt-3 rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
        >
          {busy ? "保存中…" : "保存反馈"}
        </button>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">批量导入 / 导出</h2>
            <p className="mt-1 text-xs text-ink-500">
              CSV 表头：job_id, detector, detector_version, checked_at, score_before, score_after, red_sentences, notes。标红句用 | 分隔。
            </p>
          </div>
          <button
            type="button"
            onClick={handleExport}
            className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50"
          >
            导出 CSV
          </button>
        </div>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (file) setImportText(await file.text());
          }}
          className="mt-3 block w-full text-xs text-ink-600"
        />
        <textarea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder="也可以直接粘贴 CSV 内容"
          className="mt-2 h-24 w-full resize-y rounded-lg border border-ink-200 bg-ink-50/40 p-2 font-mono text-xs"
        />
        <button
          type="button"
          onClick={handleImport}
          disabled={busy}
          className="mt-2 rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:opacity-60"
        >
          {busy ? "导入中…" : "导入 CSV"}
        </button>
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-900">校准结果</h2>
            <p className="mt-1 text-xs text-ink-500">
              样本 {calibration?.sample_count ?? 0} 条
            </p>
          </div>
          <button
            type="button"
            onClick={runCalibration}
            disabled={busy}
            className="rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-600 hover:bg-ink-50 disabled:opacity-60"
          >
            重新计算并保存权重
          </button>
        </div>
        {calibration && (
          <>
            <p className="mt-2 text-xs text-ink-600">{calibration.recommendation}</p>
            {calibration.active_group && (
              <p className="mt-1 text-xs text-ink-500">
                当前权重组：{calibration.active_group}
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              {Object.entries(calibration.correlations).map(([key, value]) => (
                <span
                  key={key}
                  className="rounded-md bg-ink-100 px-2 py-1 text-ink-600"
                >
                  {key} <strong className="text-ink-900">{value}</strong>
                </span>
              ))}
            </div>
            {calibration.groups && Object.keys(calibration.groups).length > 0 && (
              <div className="mt-3 space-y-2">
                {Object.entries(calibration.groups).map(([group, report]) => (
                  <div
                    key={group}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-ink-100 px-3 py-2 text-xs"
                  >
                    <span className="text-ink-700">{group}</span>
                    <span className="text-ink-500">
                      样本 {report.sample_count} 条 · 最强相关{" "}
                      {Object.entries(report.correlations).sort(
                        (a, b) => Math.abs(b[1]) - Math.abs(a[1])
                      )[0]?.[0] ?? "-"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">标红句聚类</h2>
        {clusters.length === 0 ? (
          <p className="mt-2 text-sm text-ink-500">还没有标红句。录入反馈时填写标红句后，这里会按句式聚类。</p>
        ) : (
          <div className="mt-3 space-y-2">
            {clusters.map((cluster) => (
              <div key={cluster.label} className="rounded-lg border border-ink-100 px-3 py-2">
                <div className="flex items-center justify-between text-sm text-ink-800">
                  <span>{cluster.label}</span>
                  <span className="text-xs text-ink-500">{cluster.count} 句</span>
                </div>
                <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-ink-500">
                  {cluster.examples.map((example, index) => (
                    <li key={index} className="truncate">{example}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold text-ink-900">反馈记录</h2>
        {feedback.length === 0 ? (
          <p className="mt-2 text-sm text-ink-500">还没有反馈记录。</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="text-ink-500">
                <tr>
                  <th className="py-2">时间</th>
                  <th className="py-2">检测器</th>
                  <th className="py-2">任务</th>
                  <th className="py-2">分数</th>
                  <th className="py-2">代理分</th>
                  <th className="py-2">标红句</th>
                </tr>
              </thead>
              <tbody>
                {feedback.map((row) => (
                  <tr key={row.id} className="border-t border-ink-100 text-ink-700">
                    <td className="py-2">{formatTime(row.created_at)}</td>
                    <td className="py-2">
                      {row.detector} {row.detector_version}
                    </td>
                    <td className="py-2">{row.job_id ? `#${row.job_id}` : "-"}</td>
                    <td className="py-2">
                      {row.score_before} → {row.score_after}
                    </td>
                    <td className="py-2">{row.proxy_total ?? "-"}</td>
                    <td className="py-2">{row.red_sentences.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
