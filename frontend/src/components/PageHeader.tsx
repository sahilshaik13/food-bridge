import { AppNav } from "@/components/AppNav";

export function PageHeader({
  eyebrow,
  title,
  description
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <>
      <AppNav />
      <header className="border-b border-ink/10 bg-paper/85">
        <div className="mx-auto max-w-7xl px-5 py-8">
          <p className="mb-2 inline-flex rounded-full bg-saffron/25 px-3 py-1 text-xs font-bold uppercase tracking-wide text-ink">
            {eyebrow}
          </p>
          <h1 className="font-display text-5xl font-normal leading-tight text-ink md:text-7xl">{title}</h1>
          <p className="mt-3 max-w-3xl text-base leading-7 text-ink/70">{description}</p>
        </div>
      </header>
    </>
  );
}
