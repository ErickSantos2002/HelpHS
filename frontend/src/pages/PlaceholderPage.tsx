interface PlaceholderPageProps {
  title: string;
  description?: string;
}

export default function PlaceholderPage({
  title,
  description,
}: PlaceholderPageProps) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-slate-100">{title}</h1>
      <p className="text-slate-400">{description ?? "Em construção..."}</p>
    </div>
  );
}
