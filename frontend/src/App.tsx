import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import {
  emptyState,
  fetchHotkeys,
  fetchState,
  mergePoints,
  setThreshold,
  startBot,
  stopBot,
  type AppState,
} from "./api";
import { FeeChart } from "./FeeChart";

const mono =
  'ui-monospace, "SFMono-Regular", "Cascadia Mono", "Roboto Mono", Menlo, Consolas, monospace';
const DAY_MS = 24 * 60 * 60 * 1000;
const X_RIGHT_PAD_MS = 2 * 60 * 60 * 1000;
const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
const X_TICK_MS = 3 * 60 * 60 * 1000;

function formatTao(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `τ${value.toFixed(4)}`;
}

function formatTooltipTime(timestamp: number): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date(timestamp));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")} JST`;
}

export default function App() {
  const [state, setState] = useState<AppState>(emptyState);
  const [lineDraft, setLineDraft] = useState("");
  const [wallet, setWallet] = useState("PoWallet");
  const [hotkey, setHotkey] = useState("");
  const [hotkeys, setHotkeys] = useState<string[]>([]);
  const [password, setPassword] = useState(() => {
    try {
      return localStorage.getItem("reg_bot_coldkey_password") ?? "";
    } catch {
      return "";
    }
  });
  const [openrouterKey, setOpenrouterKey] = useState(() => {
    try {
      return localStorage.getItem("reg_bot_openrouter_key") ?? "";
    } catch {
      return "";
    }
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [hover, setHover] = useState<{
    t: number;
    tao: number;
    left: number;
    top: number;
    gridTop: number;
    gridLeft: number;
    gridWidth: number;
    gridHeight: number;
  } | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const chartBox = useRef<HTMLDivElement | null>(null);
  const lastSeriesT = useRef(0);
  const hoverRaf = useRef(0);

  const apply = useCallback((next: AppState) => {
    setState((prev) => {
      const incoming = next.series ?? [];
      const incomingRegs = next.regs ?? [];
      const series = next.delta
        ? incoming.length
          ? mergePoints(prev.series, incoming)
          : prev.series
        : incoming;
      const regs = next.delta
        ? incomingRegs.length
          ? mergePoints(prev.regs, incomingRegs)
          : prev.regs
        : incomingRegs;
      if (series.length) {
        lastSeriesT.current = series[series.length - 1].t;
      }
      return { ...next, series, regs, delta: undefined };
    });
    setWallet((current) => (current ? current : next.bot.wallet));
    setHotkey((current) => (current ? current : next.bot.hotkey));
    if (next.threshold_tao != null) {
      setLineDraft((current) => (current === "" ? next.threshold_tao!.toFixed(4) : current));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    let retry = 0;
    const open = () => {
      if (cancelled) {
        return;
      }
      source = new EventSource("/api/events");
      source.onmessage = (event) => {
        try {
          apply(JSON.parse(event.data) as AppState);
        } catch {
          /* ignore */
        }
      };
      source.onerror = () => {
        const current = source;
        current?.close();
        if (source === current) {
          source = null;
        }
        window.clearTimeout(retry);
        if (!cancelled) {
          retry = window.setTimeout(open, 5000);
        }
      };
    };
    fetchState()
      .then((next) => {
        if (!cancelled) {
          apply(next);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setFormError(err.message);
        }
      });
    open();
    return () => {
      cancelled = true;
      source?.close();
      window.clearTimeout(retry);
    };
  }, [apply]);

  const refreshHotkeys = useCallback((fresh = false) => {
    fetchHotkeys(wallet, fresh)
      .then((names) => {
        setHotkeys(names);
        setHotkey((current) => (names.includes(current) ? current : names[0] ?? current));
      })
      .catch(() => setHotkeys([]));
  }, [wallet]);

  useEffect(() => {
    refreshHotkeys();
  }, [refreshHotkeys]);

  const orStatus = state.bot.openrouter?.status ?? null;
  useEffect(() => {
    if (orStatus !== "pending") {
      return;
    }
    setNowMs(Date.now());
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [orStatus]);

  const nowBucket = Math.floor(Date.now() / 60_000);
  const xDomain = useMemo(() => {
    const now = nowBucket * 60_000;
    return [now - DAY_MS, now + X_RIGHT_PAD_MS] as [number, number];
  }, [nowBucket]);

  const xTicks = useMemo(() => {
    const now = Date.now();
    const [start] = xDomain;
    const first = Math.ceil((start + JST_OFFSET_MS) / X_TICK_MS) * X_TICK_MS - JST_OFFSET_MS;
    const ticks: number[] = [];
    for (let t = first; t <= now; t += X_TICK_MS) {
      ticks.push(t);
    }
    return ticks;
  }, [xDomain]);

  const displaySeries = useMemo(() => {
    const start = xDomain[0];
    const kept = state.series.filter((point) => point.t >= start);
    const max = 480;
    if (kept.length <= max) {
      return kept;
    }
    const last = kept[kept.length - 1];
    const span = max - 1;
    const sampled = Array.from({ length: max }, (_, i) => kept[Math.round((i * (kept.length - 1)) / span)]);
    sampled[max - 1] = last;
    return sampled;
  }, [state.series, xDomain]);
  const feeDot = useMemo(() => {
    if (state.fee_tao == null) {
      return null;
    }
    return { t: xDomain[1] - X_RIGHT_PAD_MS, tao: state.fee_tao };
  }, [state.fee_tao, xDomain]);
  const standardTao = useMemo(() => {
    const typed = Number(lineDraft);
    if (lineDraft.trim() !== "" && Number.isFinite(typed) && typed >= 0) {
      return typed;
    }
    return state.threshold_tao;
  }, [lineDraft, state.threshold_tao]);
  const yDomain = useMemo(() => {
    const values = [
      ...displaySeries.map((p) => p.tao),
      state.fee_tao == null ? 0 : Math.round(state.fee_tao * 1000) / 1000,
      standardTao ?? 0,
    ].filter((v) => v != null && !Number.isNaN(v));
    if (!values.length) {
      return [0, 1] as [number, number];
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max((max - min) * 0.08, 0.002);
    return [Math.max(0, min - pad), max + pad] as [number, number];
  }, [displaySeries, state.fee_tao, standardTao]);

  const commitLine = async (tao: number) => {
    if (!Number.isFinite(tao) || tao < 0) {
      return;
    }
    setFormError(null);
    setLineDraft(tao.toFixed(4));
    apply(await setThreshold(tao));
  };

  const pointFromClient = (clientX: number, clientY: number) => {
    const grid = chartBox.current?.querySelector(".recharts-cartesian-grid");
    if (!grid || !chartBox.current) {
      return null;
    }
    const rect = grid.getBoundingClientRect();
    const origin = chartBox.current.getBoundingClientRect();
    const [x0, x1] = xDomain;
    const [y0, y1] = yDomain;
    const px = (clientX - rect.left) / rect.width;
    const py = (clientY - rect.top) / rect.height;
    if (px < 0 || px > 1 || py < 0 || py > 1) {
      return null;
    }
    return {
      t: x0 + px * (x1 - x0),
      tao: y1 - py * (y1 - y0),
      left: rect.left - origin.left + px * rect.width,
      top: rect.top - origin.top + py * rect.height,
      gridTop: rect.top - origin.top,
      gridLeft: rect.left - origin.left,
      gridWidth: rect.width,
      gridHeight: rect.height,
    };
  };

  const onChartClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const box = chartBox.current?.querySelector(".recharts-cartesian-grid");
    if (!box) {
      return;
    }
    const rect = box.getBoundingClientRect();
    const ratio = (event.clientY - rect.top) / rect.height;
    if (ratio < 0 || ratio > 1) {
      return;
    }
    const [lo, hi] = yDomain;
    void commitLine(hi - ratio * (hi - lo));
  };

  const onStart = async () => {
    setFormError(null);
    const tao = Number(lineDraft);
    if (!Number.isFinite(tao)) {
      setFormError("Set a standard fee first");
      return;
    }
    if (!password.trim() && !state.bot.has_password) {
      setFormError("Type the coldkey password, then click Start");
      return;
    }
    try {
      if (state.threshold_tao == null || Math.abs((state.threshold_tao ?? 0) - tao) > 1e-9) {
        await setThreshold(tao);
      }
      apply(
        await startBot({
          wallet,
          hotkey,
          password,
          openrouter_key: openrouterKey,
          dry_run: false,
        }),
      );
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  };

  const onStop = async () => {
    setFormError(null);
    apply(await stopBot());
  };

  const status = state.bot.registered
    ? "registered"
    : state.bot.busy
      ? "registering"
      : state.bot.armed
        ? "armed"
        : "idle";
  const statusColor = status === "registered" ? "success" : "warning";
  const registerAlert = useMemo(() => {
    const key = `${wallet}/${hotkey || "—"}`;
    const line = standardTao == null ? "—" : formatTao(standardTao);
    const trigger = state.bot.last_trigger;
    if (formError || state.bot.error) {
      return {
        severity: "error" as const,
        text: formError || state.bot.error || "Registration error",
      };
    }
    if (status === "registering") {
      return {
        severity: "warning" as const,
        text: `Registering ${key} on subnet 15…`,
      };
    }
    if (status === "armed") {
      return {
        severity: "warning" as const,
        text: `Watching ${key}. Will register on subnet 15 when fee ≤ ${line}.`,
      };
    }
    if (status === "registered" || trigger?.ok) {
      const or = state.bot.openrouter;
      const orKey = or?.hotkey ? `${or.wallet || wallet}/${or.hotkey}` : key;
      if (or?.status === "pending") {
        const remain = Math.max(0, Math.ceil((Number(or.due_at ?? 0) * 1000 - nowMs) / 1000));
        const mins = Math.floor(remain / 60);
        const secs = String(remain % 60).padStart(2, "0");
        return {
          severity: "warning" as const,
          text: `Registered ${orKey} on subnet 15. Connecting OpenRouter in ${mins}m ${secs}s.`,
        };
      }
      if (or?.status === "connecting") {
        return {
          severity: "warning" as const,
          text: `Registered ${orKey} on subnet 15. Connecting OpenRouter now…`,
        };
      }
      if (or?.status === "error") {
        return {
          severity: "error" as const,
          text: `Registered ${orKey} on subnet 15. ${or.message || "OpenRouter connect failed."}`,
        };
      }
      const detail = trigger?.message ? ` ${trigger.message}` : "";
      return {
        severity: "success" as const,
        text: or?.status === "connected"
          ? `Registered ${orKey} on subnet 15 and connected OpenRouter.`
          : `Registered ${key} on subnet 15.${detail}`,
      };
    }
    if (trigger && trigger.ok === false) {
      return {
        severity: "error" as const,
        text: trigger.message || `Failed to register ${key}.`,
      };
    }
    return {
      severity: "info" as const,
      text: `New hotkey ${key} is idle. Start the bot to register when the fee reaches ${line}.`,
    };
  }, [wallet, hotkey, standardTao, status, formError, state.bot.error, state.bot.last_trigger, state.bot.openrouter, nowMs]);

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <AppBar position="static">
        <Toolbar sx={{ minHeight: 56, gap: 2, px: 2 }}>
          <Box
            component="img"
            src="/logo.png"
            alt="SN15 Auto Register"
            sx={{ width: 32, height: 32, borderRadius: "6px", objectFit: "cover", flexShrink: 0 }}
          />
          <Typography sx={{ fontWeight: 700, fontSize: "1.05rem", mr: 1 }}>SN15 Auto Register</Typography>
          <Typography sx={{ color: "#8a8f98", fontSize: "0.85rem" }}>netuid {state.netuid}</Typography>
          <Box sx={{ flex: 1 }} />
          <Typography sx={{ color: "#8a8f98", fontSize: "0.8rem" }}>Reg fee</Typography>
          <Typography sx={{ color: "#4ea1ff", fontFamily: mono, fontWeight: 700, fontSize: "1.2rem" }}>
            {formatTao(state.fee_tao)}
          </Typography>
          {(status === "registering" || status === "registered") && (
            <Chip size="small" label={status} color={statusColor} variant="filled" />
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ flex: 1, overflow: "auto", p: { xs: 1.5, md: 2 } }}>
        <Alert
          severity={registerAlert.severity}
          sx={{
            mb: 1.5,
            backgroundColor: "#12171d",
            border: "1px solid #2a3038",
            color: "#e89b25",
            "& .MuiAlert-icon": { color: "#e89b25" },
            "& .MuiAlert-message": { fontFamily: mono, fontSize: "1.1rem", fontWeight: 600, color: "#e89b25" },
          }}
        >
          {registerAlert.text}
        </Alert>
        <Box sx={{ backgroundColor: "#12171d", border: "1px solid #2a3038", borderRadius: "10px", p: { xs: 1.5, md: 2 } }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, flexWrap: "wrap", mb: 1.5 }}>
            <Typography sx={{ color: "#f3f4f6", fontWeight: 600, fontSize: "1.1rem" }}>Registration fee</Typography>
            <Typography sx={{ color: "#8a8f98", fontSize: "0.95rem", fontFamily: mono }}>
              line {standardTao == null ? "—" : formatTao(standardTao)} · click chart to set
            </Typography>
          </Box>
          <Box
            ref={chartBox}
            onClick={onChartClick}
            onMouseMove={(event) => {
              if (hoverRaf.current) {
                return;
              }
              const { clientX, clientY } = event;
              hoverRaf.current = window.requestAnimationFrame(() => {
                hoverRaf.current = 0;
                setHover(pointFromClient(clientX, clientY));
              });
            }}
            onMouseLeave={() => {
              if (hoverRaf.current) {
                window.cancelAnimationFrame(hoverRaf.current);
                hoverRaf.current = 0;
              }
              setHover(null);
            }}
            sx={{ height: { xs: 320, md: 420 }, cursor: "crosshair", position: "relative" }}
          >
            {state.series.length === 0 ? (
              <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "#8a8f98" }}>
                {state.error ?? "Waiting for fee data…"}
              </Box>
            ) : (
              <>
                <FeeChart
                  data={displaySeries}
                  xDomain={xDomain}
                  xTicks={xTicks}
                  yDomain={yDomain}
                  feeTao={state.fee_tao}
                  standardTao={standardTao}
                  feeDot={feeDot}
                />
                {hover ? (
                  <Box sx={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                    <Box
                      sx={{
                        position: "absolute",
                        left: hover.left,
                        top: hover.gridTop,
                        width: 0,
                        height: hover.gridHeight,
                        borderLeft: "1px dashed #8a8f98",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        left: hover.gridLeft,
                        top: hover.top,
                        width: hover.gridWidth,
                        height: 0,
                        borderTop: "1px dashed #8a8f98",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        left: hover.left - 4,
                        top: hover.top - 4,
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        backgroundColor: "#8a8f98",
                        border: "1.5px solid #c5c8ce",
                      }}
                    />
                    <Box
                      sx={{
                        position: "absolute",
                        left: hover.left,
                        top: hover.gridTop + hover.gridHeight + 6,
                        transform: "translateX(-50%)",
                        px: 0.75,
                        py: 0.15,
                        borderRadius: "3px",
                        border: "1px solid #8a8f98",
                        backgroundColor: "#0b0e12",
                        color: "#c5c8ce",
                        fontSize: 11,
                        fontFamily: mono,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {formatTooltipTime(hover.t)}
                    </Box>
                    <Box
                      sx={{
                        position: "absolute",
                        left: hover.gridLeft + hover.gridWidth + 8,
                        top: hover.top,
                        transform: "translateY(-50%)",
                        px: 0.75,
                        py: 0.15,
                        borderRadius: "3px",
                        border: "1px solid #8a8f98",
                        backgroundColor: "#0b0e12",
                        color: "#c5c8ce",
                        fontSize: 11,
                        fontFamily: mono,
                        whiteSpace: "nowrap",
                      }}
                    >
                      τ{hover.tao.toFixed(3)}
                    </Box>
                  </Box>
                ) : null}
              </>
            )}
          </Box>
          <Typography sx={{ mt: 1, color: "#6b717a", fontSize: "0.9rem" }}>
            Blue line is live recycle fee. Times in JST.
          </Typography>
        </Box>

        <Box
          sx={{
            mt: 2,
            backgroundColor: "#12171d",
            border: "1px solid #2a3038",
            borderRadius: "10px",
            p: { xs: 1.5, md: 2 },
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" },
            gap: 2,
          }}
        >
          <TextField
            label="Standard fee (τ)"
            value={lineDraft}
            onChange={(e) => setLineDraft(e.target.value)}
            onBlur={() => {
              const tao = Number(lineDraft);
              if (Number.isFinite(tao) && tao >= 0) {
                void commitLine(tao);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                (e.target as HTMLInputElement).blur();
              }
            }}
            size="small"
          />
          <TextField label="Wallet" value={wallet} onChange={(e) => setWallet(e.target.value)} size="small" />
          <TextField
            select
            label="Hotkey"
            value={hotkeys.includes(hotkey) ? hotkey : (hotkeys[0] ?? "")}
            onChange={(e) => setHotkey(e.target.value)}
            onClick={() => refreshHotkeys(true)}
            slotProps={{
              select: {
                onOpen: () => refreshHotkeys(true),
              },
            }}
            size="small"
          >
            {hotkeys.map((name) => (
              <MenuItem key={name} value={name}>
                {name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label={state.bot.has_password ? "Coldkey password (saved on server)" : "Coldkey password"}
            type="password"
            placeholder={state.bot.has_password ? "Leave blank to reuse the saved password" : undefined}
            value={password}
            onChange={(e) => {
              const next = e.target.value;
              setPassword(next);
              try {
                localStorage.setItem("reg_bot_coldkey_password", next);
              } catch {
                /* ignore */
              }
            }}
            size="small"
            autoComplete="current-password"
          />
          <TextField
            label="OpenRouter key"
            type="password"
            value={openrouterKey}
            onChange={(e) => {
              const next = e.target.value;
              setOpenrouterKey(next);
              try {
                localStorage.setItem("reg_bot_openrouter_key", next);
              } catch {
                /* ignore */
              }
            }}
            size="small"
            autoComplete="off"
            sx={{ gridColumn: { md: "1 / -1" } }}
          />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button variant="contained" onClick={() => void onStart()} disabled={state.bot.armed || state.bot.busy}>
              Start bot
            </Button>
            <Button variant="outlined" onClick={() => void onStop()} disabled={!state.bot.armed && !state.bot.busy}>
              Stop
            </Button>
          </Box>
          <Box sx={{ gridColumn: { md: "1 / -1" } }}>
            {(formError || state.error || state.bot.error) && (
              <Typography sx={{ color: "#f07178", fontSize: "1rem", mb: 0.5 }}>
                {formError || state.bot.error || state.error}
              </Typography>
            )}
            {state.bot.last_trigger && (
              <Typography sx={{ color: "#8a8f98", fontSize: "0.95rem", fontFamily: mono }}>
                Last: {state.bot.last_trigger.message ?? "—"} at {state.bot.last_trigger.at ?? "—"}
                {state.bot.last_trigger.fee_tao != null ? ` · ${formatTao(state.bot.last_trigger.fee_tao)}` : ""}
              </Typography>
            )}
            {state.bot.armed && !state.bot.has_password && (
              <Typography sx={{ color: "#f07178", fontSize: "1rem", mb: 0.5 }}>
                The running bot has no coldkey password. Stop, type the password, then Start again.
              </Typography>
            )}
            <Typography sx={{ color: "#6b717a", fontSize: "0.95rem", mt: 0.75 }}>
              When the live fee is at or below the standard line, the bot registers {wallet}/{hotkey} on subnet 15.
              After a real register, OpenRouter is connected to that hotkey 5 minutes later.
              A verified password is saved on the server and reused after Stop or a backend restart. Leave the box blank to keep the saved one.
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
