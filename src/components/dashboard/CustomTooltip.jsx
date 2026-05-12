// FIXED: Used parameter store language for tooltip number locale.
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useParametres } from "@/store/useParametres";

export function CustomTooltip({ active, payload, label }) {
  const { locale } = useParametres();

  if (!active || !payload?.length) return null;
  return _jsxs("div", {
    className:
      "bg-popover border border-border/80 rounded-2xl px-4 py-3.5 text-[12px] shadow-2xl shadow-black/35 backdrop-blur-sm min-w-[140px]",
    children: [
      label &&
        _jsx("p", {
          className: "text-foreground font-semibold mb-2 pb-1.5 border-b border-border/50",
          children: label,
        }),
      _jsx("div", {
        className: "space-y-1",
        children: payload.map((p, i) =>
          _jsxs(
            "div",
            {
              className: "flex items-center justify-between gap-4",
              children: [
                _jsxs("div", {
                  className: "flex items-center gap-1.5",
                  children: [
                    _jsx("span", {
                      className: "w-2 h-2 rounded-full flex-shrink-0",
                      style: { backgroundColor: p.color },
                    }),
                    _jsx("span", { className: "text-muted-foreground", children: p.name }),
                  ],
                }),
                _jsx("span", {
                  className: "text-foreground font-medium tabular-nums",
                  children: typeof p.value === "number" ? p.value.toLocaleString(locale()) : p.value,
                }),
              ],
            },
            i,
          ),
        ),
      }),
    ],
  });
}
