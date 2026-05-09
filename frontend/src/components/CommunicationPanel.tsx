"use client";

import { BellRing, MessageSquareText, Mail, Send } from "lucide-react";

export function CommunicationPanel({
  notifications = [],
  messages = []
}: {
  notifications?: any[];
  messages?: any[];
}) {
  return (
    <section className="grid gap-6">
      <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
        <div className="mb-6 flex items-center justify-between">
          <div>
             <h2 className="text-xl font-bold text-ink">Notification Relay</h2>
             <p className="text-[10px] uppercase tracking-widest font-bold text-ink/40">Real-time alerts</p>
          </div>
          <div className="rounded-xl bg-saffron/10 p-2.5 text-saffron">
            <BellRing className="size-5" />
          </div>
        </div>
        <div className="grid gap-4">
          {notifications.length > 0 ? (
            notifications.slice(0, 4).map((notification) => (
              <article key={notification.id} className="group rounded-xl bg-field/50 p-4 transition-colors hover:bg-field">
                <div className="flex items-center justify-between gap-3">
                  <strong className="text-sm text-ink">{notification.title}</strong>
                  <span className="rounded-md bg-white px-2 py-0.5 text-[9px] font-bold uppercase text-ink/50 shadow-sm">
                    {notification.channel}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-ink/60">{notification.body}</p>
              </article>
            ))
          ) : (
             <div className="flex flex-col items-center justify-center py-10 text-center">
                <Mail className="size-8 text-ink/10" />
                <p className="mt-2 text-xs font-medium text-ink/40">No new notifications</p>
             </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-ink">Coordination Threads</h2>
            <p className="text-[10px] uppercase tracking-widest font-bold text-ink/40">Direct messages</p>
          </div>
          <div className="rounded-xl bg-leaf/10 p-2.5 text-leaf">
            <MessageSquareText className="size-5" />
          </div>
        </div>
        <div className="grid gap-4">
          {messages.length > 0 ? (
            messages.slice(-4).map((message) => (
              <article
                key={message.id}
                className={`rounded-xl p-4 ${
                  message.sender_role === "donor" ? "bg-leaf/5" : "bg-civic/5"
                }`}
              >
                <span className={`text-[9px] font-bold uppercase tracking-widest ${
                  message.sender_role === "donor" ? "text-leaf" : "text-civic"
                }`}>
                  {message.sender_role.replace("_", " ")}
                </span>
                <p className="mt-1.5 text-xs leading-relaxed text-ink/80">{message.body}</p>
              </article>
            ))
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <MessageSquareText className="size-8 text-ink/10" />
              <p className="mt-2 text-xs font-medium text-ink/40">Start a coordination thread</p>
            </div>
          )}
        </div>
        <div className="mt-4 flex gap-2">
           <input className="flex-1 rounded-xl border border-ink/10 bg-field px-4 py-2 text-xs outline-none focus:border-leaf" placeholder="Send a message..." />
           <button className="rounded-xl bg-leaf p-2 text-white"><Send className="size-4" /></button>
        </div>
      </div>
    </section>
  );
}
