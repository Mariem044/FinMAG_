import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useMemo, Fragment } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getExpandedRowModel,
  getPaginationRowModel,
  flexRender,
} from "@tanstack/react-table";
import {
  ChevronDown,
  ChevronRight,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight as ChevRight,
  Search,
  Download,
} from "lucide-react";

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\n\r;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function getExportValue(row, column) {
  if (typeof column.accessorFn === "function") return column.accessorFn(row);
  if (column.accessorKey) return row[column.accessorKey];
  return "";
}

export function DataTable({ data, columns, expandable, renderSubRow, exportFilename = "export.csv" }) {
  const [sorting, setSorting] = useState([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [expanded, setExpanded] = useState({});
  const allColumns = useMemo(() => {
    if (!expandable) return columns;
    return [
      {
        id: "expander",
        header: () => null,
        cell: ({ row }) =>
          _jsx("button", {
            onClick: row.getToggleExpandedHandler(),
            className: "text-text-dim hover:text-foreground p-1 rounded transition-colors",
            children: row.getIsExpanded()
              ? _jsx(ChevronDown, { size: 13 })
              : _jsx(ChevronRight, { size: 13 }),
          }),
        size: 36,
      },
      ...columns,
    ];
  }, [columns, expandable]);
  const table = useReactTable({
    data,
    columns: allColumns,
    state: { sorting, globalFilter, expanded },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowCanExpand: () => !!expandable,
    initialState: { pagination: { pageSize: 10 } },
  });
  const { pageIndex, pageSize } = table.getState().pagination;
  const totalRows = table.getFilteredRowModel().rows.length;
  const from = pageIndex * pageSize + 1;
  const to = Math.min((pageIndex + 1) * pageSize, totalRows);
  const exportCsv = () => {
    const exportColumns = columns.filter((c) => c.accessorKey || c.accessorFn);
    const headers = exportColumns.map((c) =>
      typeof c.header === "string" ? c.header : c.accessorKey || c.id || "",
    );
    const rows = table.getFilteredRowModel().rows.map((row) =>
      exportColumns.map((column) => csvEscape(getExportValue(row.original, column))).join(";"),
    );
    const csv = [headers.map(csvEscape).join(";"), ...rows].join("\n");
    const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = exportFilename;
    link.click();
    URL.revokeObjectURL(url);
  };
  return _jsxs("div", {
    className: "bg-card border border-border rounded-xl overflow-hidden",
    children: [
      _jsxs("div", {
        className: "p-4 border-b border-border flex items-center justify-between gap-3 flex-wrap",
        children: [
          _jsxs("div", {
            className: "relative",
            children: [
              _jsx(Search, {
                size: 13,
                className: "absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground",
              }),
              _jsx("input", {
                value: globalFilter,
                onChange: (e) => setGlobalFilter(e.target.value),
                placeholder: "Rechercher...",
                className:
                  "\r\n              bg-secondary border border-border rounded-lg pl-8 pr-3 py-1.5\r\n              text-[13px] text-secondary-foreground outline-none\r\n              focus:border-primary hover:border-primary/50 w-56 transition-colors\r\n            ",
              }),
            ],
          }),
          _jsxs("button", {
            onClick: exportCsv,
            disabled: totalRows === 0,
            className:
              "inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40",
            children: [_jsx(Download, { size: 13 }), "Exporter CSV"],
          }),
          _jsx("p", {
            className: "text-[12px] text-muted-foreground",
            children: totalRows > 0 ? `${from}–${to} sur ${totalRows} entrées` : "Aucune entrée",
          }),
        ],
      }),
      _jsx("div", {
        className: "overflow-x-auto",
        children: _jsxs("table", {
          className: "w-full min-w-[600px]",
          children: [
            _jsx("thead", {
              children: table.getHeaderGroups().map((hg) =>
                _jsx(
                  "tr",
                  {
                    className: "bg-secondary/70 border-b border-border",
                    children: hg.headers.map((h) =>
                      _jsx(
                        "th",
                        {
                          className:
                            "text-left text-[11px] text-muted-foreground uppercase tracking-wider px-4 py-3 font-semibold cursor-pointer select-none hover:text-foreground transition-colors",
                          onClick: h.column.getToggleSortingHandler(),
                          style: { width: h.getSize() !== 150 ? h.getSize() : undefined },
                          children: _jsxs("div", {
                            className: "flex items-center gap-1.5",
                            children: [
                              flexRender(h.column.columnDef.header, h.getContext()),
                              h.column.getCanSort() &&
                                _jsx(ArrowUpDown, {
                                  size: 10,
                                  className: "text-muted-foreground/50",
                                }),
                            ],
                          }),
                        },
                        h.id,
                      ),
                    ),
                  },
                  hg.id,
                ),
              ),
            }),
            _jsxs("tbody", {
              children: [
                table.getRowModel().rows.map((row, idx) =>
                  _jsxs(
                    Fragment,
                    {
                      children: [
                        _jsx("tr", {
                          className: `
                  border-b border-border/50 hover:bg-surface-hover/80 transition-colors duration-150
                  ${idx % 2 === 1 ? "bg-secondary/20" : "bg-card"}
                `,
                          children: row.getVisibleCells().map((cell) =>
                            _jsx(
                              "td",
                              {
                                className: "px-4 py-3 text-[13px] text-secondary-foreground",
                                children: flexRender(cell.column.columnDef.cell, cell.getContext()),
                              },
                              cell.id,
                            ),
                          ),
                        }),
                        row.getIsExpanded() &&
                          renderSubRow &&
                          _jsx("tr", {
                            className: "bg-secondary/30",
                            children: _jsx("td", {
                              colSpan: allColumns.length,
                              className: "px-6 py-4 border-l-2 border-l-primary/50",
                              children: renderSubRow(row.original),
                            }),
                          }),
                      ],
                    },
                    row.id,
                  ),
                ),
                table.getRowModel().rows.length === 0 &&
                  _jsx("tr", {
                    children: _jsx("td", {
                      colSpan: allColumns.length,
                      className: "px-4 py-8 text-center text-[13px] text-muted-foreground",
                      children: "Aucun r\u00E9sultat trouv\u00E9.",
                    }),
                  }),
              ],
            }),
          ],
        }),
      }),
      table.getPageCount() > 1 &&
        _jsxs("div", {
          className:
            "px-4 py-3 border-t border-border flex items-center justify-between gap-3 flex-wrap",
          children: [
            _jsxs("div", {
              className: "flex items-center gap-1",
              children: [
                _jsx("button", {
                  onClick: () => table.previousPage(),
                  disabled: !table.getCanPreviousPage(),
                  className:
                    "w-8 h-8 flex items-center justify-center rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors",
                  children: _jsx(ChevronLeft, { size: 14 }),
                }),
                Array.from({ length: Math.min(table.getPageCount(), 7) }, (_, i) => {
                  const pc = table.getPageCount();
                  let p = i;
                  if (pc > 7) {
                    const half = 3;
                    const start = Math.max(0, Math.min(pageIndex - half, pc - 7));
                    p = start + i;
                  }
                  return _jsx(
                    "button",
                    {
                      onClick: () => table.setPageIndex(p),
                      className: `w-8 h-8 flex items-center justify-center rounded-lg text-[12px] font-medium transition-colors ${
                        pageIndex === p
                          ? "bg-primary text-primary-foreground"
                          : "border border-border text-muted-foreground hover:text-foreground hover:border-primary/50"
                      }`,
                      children: p + 1,
                    },
                    p,
                  );
                }),
                _jsx("button", {
                  onClick: () => table.nextPage(),
                  disabled: !table.getCanNextPage(),
                  className:
                    "w-8 h-8 flex items-center justify-center rounded-lg border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors",
                  children: _jsx(ChevRight, { size: 14 }),
                }),
              ],
            }),
            _jsx("select", {
              value: pageSize,
              onChange: (e) => table.setPageSize(+e.target.value),
              className:
                "bg-secondary border border-border text-secondary-foreground rounded-lg px-2 py-1.5 text-[12px] outline-none focus:border-primary",
              children: [10, 20, 50].map((s) =>
                _jsxs("option", { value: s, children: [s, " / page"] }, s),
              ),
            }),
          ],
        }),
    ],
  });
}
