export type FeePoint = { t: number; tao: number };

export type BotState = {
  armed: boolean;
  dry_run: boolean;
  wallet: string;
  hotkey: string;
  busy: boolean;
  registered: boolean;
  has_password?: boolean;
  last_trigger: {
    at?: string;
    fee_tao?: number;
    ok?: boolean;
    dry_run?: boolean;
    already?: boolean;
    openrouter_ok?: boolean;
    message?: string;
  } | null;
  error: string | null;
  openrouter?: {
    status?: string | null;
    due_at?: number | null;
    wallet?: string | null;
    hotkey?: string | null;
    message?: string | null;
  } | null;
};

export type AppState = {
  netuid: number;
  network: string;
  fee_tao: number | null;
  threshold_tao: number | null;
  series: FeePoint[];
  regs: FeePoint[];
  updated_at: string | null;
  error: string | null;
  delta?: boolean;
  bot: BotState;
};

export const emptyState: AppState = {
  netuid: 15,
  network: "finney",
  fee_tao: null,
  threshold_tao: null,
  series: [],
  regs: [],
  updated_at: null,
  error: null,
  bot: {
    armed: false,
    dry_run: false,
    wallet: "PoWallet",
    hotkey: "hotkey1",
    busy: false,
    registered: false,
    last_trigger: null,
    error: null,
    openrouter: null,
  },
};

async function parse(res: Response): Promise<AppState> {
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) {
        throw new Error(body.detail);
      }
    } catch (err) {
      if (err instanceof SyntaxError) {
        throw new Error(text || res.statusText);
      }
      throw err;
    }
    throw new Error(text || res.statusText);
  }
  return (await res.json()) as AppState;
}

const MAX_SERIES_POINTS = 480;

export function mergePoints(base: FeePoint[], extra: FeePoint[]): FeePoint[] {
  if (!extra.length && base.length && base.length <= MAX_SERIES_POINTS) {
    return base;
  }
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const byTime = new Map<number, FeePoint>();
  for (const point of base) {
    if (point.t >= cutoff) {
      byTime.set(point.t, point);
    }
  }
  for (const point of extra) {
    if (point.t >= cutoff) {
      byTime.set(point.t, point);
    }
  }
  const merged = [...byTime.values()].sort((a, b) => a.t - b.t);
  if (merged.length <= MAX_SERIES_POINTS) {
    return merged;
  }
  const last = merged[merged.length - 1];
  const span = MAX_SERIES_POINTS - 1;
  const sampled = Array.from({ length: MAX_SERIES_POINTS }, (_, i) => {
    return merged[Math.round((i * (merged.length - 1)) / span)];
  });
  sampled[sampled.length - 1] = last;
  return sampled;
}

export function fetchState(since?: number): Promise<AppState> {
  const query = since != null ? `?since=${since}` : "";
  return fetch(`/api/state${query}`).then(parse);
}

export async function fetchHotkeys(wallet: string, refresh = false): Promise<string[]> {
  const params = new URLSearchParams();
  if (wallet) {
    params.set("wallet", wallet);
  }
  if (refresh) {
    params.set("refresh", "true");
  }
  const query = params.toString() ? `?${params}` : "";
  const res = await fetch(`/api/hotkeys${query}`);
  if (!res.ok) {
    return [];
  }
  const data = (await res.json()) as { hotkeys?: string[] };
  return data.hotkeys ?? [];
}

export function setThreshold(tao: number): Promise<AppState> {
  return fetch("/api/threshold", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tao }),
  }).then(parse);
}

export function startBot(body: {
  wallet: string;
  hotkey: string;
  password: string;
  openrouter_key: string;
  dry_run: boolean;
}): Promise<AppState> {
  return fetch("/api/bot/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(parse);
}

export function stopBot(): Promise<AppState> {
  return fetch("/api/bot/stop", { method: "POST" }).then(parse);
}
