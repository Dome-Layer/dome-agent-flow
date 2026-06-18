"use client";

import { useCallback, useEffect, useState } from "react";
import { getRun, listRuns } from "@/lib/api";
import type { RunRecord } from "@/types/runs";

export function usePendingRuns() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRuns("pending_approval");
      setRuns(data.runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { runs, loading, error, reload: load };
}

export function useRun(workflowRunId: string) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRun(await getRun(workflowRunId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run");
    } finally {
      setLoading(false);
    }
  }, [workflowRunId]);

  useEffect(() => {
    load();
  }, [load]);

  return { run, loading, error, reload: load };
}
