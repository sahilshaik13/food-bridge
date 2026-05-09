"use client";
import { useState, useEffect } from "react";
import { Bot, Link2, SendHorizontal, ExternalLink, CheckCircle2, Loader2, AlertCircle, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend } from "@/lib/api";

export function TelegramPanel() {
  const { profile, refreshProfile } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [manualLink, setManualLink] = useState<string | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [botUrl, setBotUrl] = useState<string | null>(null);
  
  const isLinked = Boolean(profile?.telegram_enabled || botUsername);

  const loadTelegramStatus = async () => {
    try {
      const status = await apiGet<{ bot_registered?: boolean; bot_username?: string; bot_url?: string }>("/telegram/status");
      if (status.bot_registered && status.bot_username) {
        setBotUsername(status.bot_username);
        setBotUrl(status.bot_url || `https://t.me/${status.bot_username}`);
      }
    } catch {
      // Keep UI usable even when status fetch fails.
    }
  };

  useEffect(() => {
    loadTelegramStatus();
  }, []);

  const handleConnect = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiSend("/telegram/auth/generate-link", {});
      const deepLink: string = String(data.deep_link || "");
      const webLink = deepLink.replace(/^tg:\/\/resolve\?domain=/, "https://t.me/").replace("&start=", "?start=");
      setManualLink(webLink);
      window.open(webLink, "_blank", "noopener,noreferrer");
      setIsPolling(true);
      
      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const status = await apiGet<{ confirmed: boolean; bot_registered?: boolean; bot_username?: string; bot_url?: string }>(`/telegram/auth/status/${data.state_token}`);
          if (status.bot_registered && status.bot_username) {
            clearInterval(pollInterval);
            setIsPolling(false);
            await refreshProfile();
            setBotUsername(status.bot_username);
            setBotUrl(status.bot_url || `https://t.me/${status.bot_username}`);
            setLoading(false);
          } else if (status.confirmed) {
            // Auth is confirmed, but bot token may still be pending in master chat.
            await loadTelegramStatus();
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 3000);

      // Timeout after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setIsPolling(false);
        setLoading(false);
      }, 300000);

    } catch (err: any) {
      setError("Failed to connect to Telegram. Please try again.");
      setLoading(false);
    }
  };

  const handleDeactivate = async () => {
    setLoading(true);
    setError(null);
    try {
      await apiSend("/telegram/deactivate", {});
      setBotUsername(null);
      setBotUrl(null);
      await refreshProfile();
    } catch {
      setError("Failed to deactivate bot. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-2xl bg-ink p-6 text-paper shadow-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Telegram Intake</h2>
          <p className="text-[10px] uppercase tracking-widest font-bold text-paper/40">Master-Slave Architecture</p>
        </div>
        <div className="rounded-xl bg-paper/10 p-2.5 text-saffron">
          <Bot className="size-6" />
        </div>
      </div>

      <div className="mt-6 space-y-4">
        {isLinked ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3 rounded-xl bg-leaf/20 p-4 border border-leaf/30">
              <CheckCircle2 className="size-5 text-leaf" />
              <div>
                <p className="text-sm font-bold text-leaf">Connected</p>
                <p className="text-[10px] text-paper/60">Bot: @{botUsername || profile?.telegram_username || "FoodBridgeBot"}</p>
              </div>
            </div>
            {botUrl && (
              <a
                href={botUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex w-full items-center justify-center gap-3 rounded-xl bg-saffron py-3.5 text-sm font-bold text-ink hover:bg-white transition-all shadow-xl shadow-saffron/20"
              >
                Go to your bot
                <ExternalLink className="size-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </a>
            )}
            <button
              onClick={handleDeactivate}
              disabled={loading || isPolling}
              className="w-full rounded-xl border border-chili/50 bg-chili/20 py-3 text-sm font-bold text-paper hover:bg-chili/30 disabled:opacity-60"
            >
              Delete / Reset Bot Link
            </button>
            
            <div className="flex gap-4 rounded-xl bg-paper/5 p-4 border border-paper/10">
              <ShieldCheck className="mt-1 size-5 shrink-0 text-saffron" />
              <div>
                <p className="text-sm font-bold text-paper">Secure Storage</p>
                <p className="mt-1 text-xs text-paper/60 leading-relaxed">
                  Your bot token is encrypted via Cloud KMS. Donations are processed through your private channel.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-4 rounded-xl bg-paper/5 p-4 border border-paper/10">
              <Link2 className="mt-1 size-5 shrink-0 text-saffron" />
              <div>
                <p className="text-sm font-bold text-paper">Step 1: Link Account</p>
                <p className="mt-1 text-xs text-paper/60 leading-relaxed">
                  Authenticate with @FoodBridgeBot to link your restaurant identity securely.
                </p>
              </div>
            </div>

            <button 
              onClick={handleConnect}
              disabled={loading || isPolling}
              className="group flex w-full items-center justify-center gap-3 rounded-xl bg-saffron py-3.5 text-sm font-bold text-ink hover:bg-white disabled:opacity-70 disabled:cursor-wait transition-all shadow-xl shadow-saffron/20"
            >
              {loading || isPolling ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {isPolling ? "Waiting for Telegram..." : "Connecting..."}
                </>
              ) : (
                <>
                  Connect via Telegram
                  <ExternalLink className="size-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                </>
              )}
            </button>

            {error && (
              <p className="flex items-center gap-1.5 px-1 text-[10px] font-bold text-chili animate-pulse">
                <AlertCircle className="size-3" /> {error}
              </p>
            )}
            {manualLink && (
              <p className="px-1 text-xs text-paper/70">
                If Telegram app does not open automatically, use this link:{" "}
                <a href={manualLink} target="_blank" rel="noopener noreferrer" className="font-bold text-saffron underline">
                  Open FoodBridgeBot
                </a>
              </p>
            )}
          </div>
        )}

        <div className="flex gap-4 rounded-xl bg-paper/5 p-4 border border-paper/10">
          <SendHorizontal className="mt-1 size-5 shrink-0 text-saffron" />
          <div>
            <p className="text-sm font-bold text-paper">How it works</p>
            <p className="mt-1 text-xs text-paper/60 leading-relaxed">
              Once linked, you will create a personal bot via BotFather and provide its token to the master bot.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
