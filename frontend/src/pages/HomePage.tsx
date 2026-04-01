export default function HomePage() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="flex items-center justify-center gap-3">
          <span className="w-3 h-3 rounded-full bg-primary animate-pulse" />
          <h1 className="text-4xl font-bold text-primary">HelpHS</h1>
        </div>
        <p className="text-slate-400 text-lg">
          Help Desk — Saúde &amp; Segurança do Trabalho
        </p>
        <p className="text-slate-500 text-sm">Em construção...</p>
      </div>
    </div>
  );
}
