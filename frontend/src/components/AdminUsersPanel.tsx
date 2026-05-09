"use client";

import { useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import { CheckCircle, XCircle, AlertTriangle, ShieldCheck, Search, Loader2 } from "lucide-react";

type User = {
  id: string;
  role: string;
  display_name: string;
  status: string;
  duplicate_flag: boolean;
};

export function AdminUsersPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, []);

  const refresh = () => {
    setLoading(true);
    apiGet<User[]>("/admin/users", []).then(u => {
      setUsers(u);
      setLoading(false);
    });
  };

  const handleVerify = async (userId: string, status: "verified" | "rejected") => {
    setActionLoading(userId);
    try {
      await apiSend(`/admin/users/${userId}/verify`, { status });
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status } : u));
    } catch (err) {
      alert("Failed to update user status");
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) return <div className="flex justify-center p-10"><Loader2 className="animate-spin text-leaf" /></div>;

  return (
    <section className="rounded-xl border border-ink/10 bg-white shadow-lift">
      <div className="flex items-center justify-between border-b border-ink/5 p-6">
        <div>
          <h2 className="text-xl font-bold text-ink">Entity Verification Queue</h2>
          <p className="text-sm text-ink/50">Approve or flag restaurants and NGOs entering the network.</p>
        </div>
        <div className="flex gap-2">
           <div className="relative">
             <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink/40" />
             <input className="rounded-lg border border-ink/10 bg-field py-2 pl-9 pr-4 text-sm outline-none focus:border-leaf" placeholder="Search entities..." />
           </div>
           <button onClick={refresh} className="rounded-lg bg-ink px-4 py-2 text-sm font-bold text-paper">Refresh</button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-field/50 text-[10px] font-bold uppercase tracking-widest text-ink/40">
              <th className="px-6 py-4">Entity Name</th>
              <th className="px-6 py-4">Role</th>
              <th className="px-6 py-4">Security Scan</th>
              <th className="px-6 py-4">Current Status</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-field/30 transition-colors">
                <td className="px-6 py-4">
                  <div className="font-bold text-ink">{user.display_name}</div>
                  <div className="text-[10px] text-ink/40">ID: {user.id}</div>
                </td>
                <td className="px-6 py-4">
                   <span className="rounded-md bg-ink/5 px-2 py-1 text-[10px] font-bold uppercase text-ink/60">
                    {user.role.replace('_', ' ')}
                   </span>
                </td>
                <td className="px-6 py-4">
                  {user.duplicate_flag ? (
                    <div className="flex items-center gap-1.5 text-chili font-bold">
                      <AlertTriangle className="size-4" />
                      Potential Duplicate
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-leaf font-bold">
                      <ShieldCheck className="size-4" />
                      Clean Scan
                    </div>
                  )}
                </td>
                <td className="px-6 py-4">
                   <span className={`rounded-full px-3 py-1 text-[10px] font-bold uppercase ${
                     user.status === 'verified' ? 'bg-leaf/10 text-leaf' : 
                     user.status === 'pending' ? 'bg-saffron/20 text-ink' : 'bg-chili/10 text-chili'
                   }`}>
                     {user.status}
                   </span>
                </td>
                <td className="px-6 py-4 text-right">
                  {user.status === "pending" && (
                    <div className="flex justify-end gap-2">
                       <button 
                        disabled={actionLoading === user.id}
                        onClick={() => handleVerify(user.id, "verified")}
                        className="rounded-lg bg-leaf/10 p-2 text-leaf hover:bg-leaf hover:text-white transition-colors"
                       >
                         {actionLoading === user.id ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle className="size-4" />}
                       </button>
                       <button 
                        disabled={actionLoading === user.id}
                        onClick={() => handleVerify(user.id, "rejected")}
                        className="rounded-lg bg-chili/10 p-2 text-chili hover:bg-chili hover:text-white transition-colors"
                       >
                         <XCircle className="size-4" />
                       </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
