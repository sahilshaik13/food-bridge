type Entity = {
  id: string;
  name: string;
  area?: string;
  status?: string;
  trust_score?: number | null;
  trust_tier?: string | null;
};

function EntityTable({
  title,
  items,
  showStatus = false,
  showScore = false,
}: {
  title: string;
  items: Entity[];
  showStatus?: boolean;
  showScore?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-ink/10 bg-white p-5 shadow-lift">
      <h3 className="mb-3 text-base font-bold text-ink">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-ink/10 text-[10px] font-bold uppercase tracking-widest text-ink/50">
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">ID</th>
              <th className="py-2 pr-3">Area</th>
              {showScore && <th className="py-2 pr-3">Score</th>}
              {showStatus && <th className="py-2 pr-3">Status</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/5">
            {items.length === 0 ? (
              <tr>
                <td className="py-3 text-ink/50" colSpan={(showStatus ? 1 : 0) + (showScore ? 1 : 0) + 3}>
                  No records.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id}>
                  <td className="py-2 pr-3 font-bold text-ink">{item.name}</td>
                  <td className="py-2 pr-3 text-xs text-ink/60">{item.id}</td>
                  <td className="py-2 pr-3 text-ink/70">{item.area || "-"}</td>
                  {showScore && (
                    <td className="py-2 pr-3 text-ink/70">
                      {item.trust_score ?? "-"}
                      {item.trust_tier ? ` (${item.trust_tier})` : ""}
                    </td>
                  )}
                  {showStatus && <td className="py-2 pr-3 text-ink/70">{item.status || "-"}</td>}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function EntityNameTables({
  donors,
  ngos,
  volunteers,
}: {
  donors: Entity[];
  ngos: Entity[];
  volunteers: Entity[];
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <EntityTable title="Donors" items={donors} showScore />
      <EntityTable title="NGOs" items={ngos} />
      <EntityTable title="Volunteers" items={volunteers} showStatus />
    </div>
  );
}
