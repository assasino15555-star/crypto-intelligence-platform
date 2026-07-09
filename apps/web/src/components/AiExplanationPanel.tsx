import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface Props {
  walletId: string;
}

export default function AiExplanationPanel({ walletId }: Props) {
  const explain = useMutation({
    mutationFn: () => api.explain(walletId, null),
  });

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">AI explanation</div>
          <div className="text-xs text-text-muted">
            Bounded, structured input · output sanitized · no financial advice
          </div>
        </div>
        <button
          className="btn"
          onClick={() => explain.mutate()}
          disabled={explain.isPending}
        >
          {explain.isPending ? "Analyzing…" : "Generate"}
        </button>
      </div>
      {explain.isError && (
        <div className="text-sm text-red-400">
          {(explain.error as Error).message}
        </div>
      )}
      {explain.data && (
        <div className="space-y-2">
          <div className="text-xs text-text-dim flex items-center gap-2">
            <span>model: {explain.data.model}</span>
            <span>·</span>
            <span>{explain.data.is_cached ? "cached" : "fresh"}</span>
          </div>
          <p className="text-sm whitespace-pre-wrap leading-relaxed">
            {explain.data.explanation}
          </p>
          <div className="text-xs text-text-dim border-t border-border-subtle pt-2">
            Factual on-chain data is distinguished from model interpretation.
            This output is not financial, legal, or security advice.
          </div>
        </div>
      )}
    </div>
  );
}
