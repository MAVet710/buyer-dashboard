import { ArrowDown, ArrowUp, ChevronDown, Filter, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { DateTableFilter, NumberTableFilter, TableFilter, TableSortDirection } from "../lib/tableFilters";

export type TableFilterKind = "text" | "number" | "values" | "date";

type Props = {
  column: string;
  kind: TableFilterKind;
  options?: string[];
  filter?: TableFilter;
  sortDirection?: TableSortDirection | null;
  onFilterChange: (filter: TableFilter | null) => void;
  onSort: (direction: TableSortDirection | null) => void;
};

type Position = { top: number; left: number; maxHeight: number };

export function TableHeaderFilter({ column, kind, options = [], filter, sortDirection, onFilterChange, onSort }: Props) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<Position>({ top: 0, left: 0, maxHeight: 440 });
  const [optionSearch, setOptionSearch] = useState("");
  const [textMode, setTextMode] = useState<"contains" | "equals">("contains");
  const [numberMode, setNumberMode] = useState<NumberTableFilter["mode"]>("gt");
  const [numberValue, setNumberValue] = useState("0");
  const [numberMax, setNumberMax] = useState("");
  const [dateMode, setDateMode] = useState<DateTableFilter["mode"]>("on");
  const [dateValue, setDateValue] = useState("");
  const [dateMax, setDateMax] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const active = Boolean(filter) || Boolean(sortDirection);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(320, Math.max(260, window.innerWidth - 24));
    const anticipatedHeight = 440;
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const belowTop = rect.bottom + 6;
    const top = belowTop + anticipatedHeight <= window.innerHeight ? belowTop : Math.max(12, rect.top - anticipatedHeight - 6);
    setPosition({ top, left, maxHeight: Math.max(180, window.innerHeight - top - 12) });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    const closeOnPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const reposition = () => updatePosition();
    document.addEventListener("pointerdown", closeOnPointer);
    document.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", closeOnPointer);
      document.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (filter?.type === "text") setTextMode(filter.mode);
    if (filter?.type === "number") {
      setNumberMode(filter.mode);
      setNumberValue(String(filter.value));
      setNumberMax(filter.max === undefined ? "" : String(filter.max));
    }
    if (filter?.type === "date") {
      setDateMode(filter.mode);
      setDateValue(filter.value);
      setDateMax(filter.max ?? "");
    }
  }, [filter]);

  const filteredOptions = useMemo(() => {
    const needle = optionSearch.trim().toLocaleLowerCase();
    return needle ? options.filter(option => option.toLocaleLowerCase().includes(needle)) : options;
  }, [optionSearch, options]);

  const selectedValues = filter?.type === "values" ? filter.values : options;
  const selectedSet = useMemo(() => new Set(selectedValues.map(value => value.toLocaleLowerCase())), [selectedValues]);

  const toggleValue = (value: string) => {
    const optionMap = new Map<string, string>(options.map(option => [option.toLocaleLowerCase(), option] as const));
    const selected = new Set(selectedValues.map(option => option.toLocaleLowerCase()));
    const key = value.toLocaleLowerCase();
    if (selected.has(key)) selected.delete(key); else selected.add(key);
    const values = [...selected].map(item => optionMap.get(item)).filter((item): item is string => Boolean(item));
    onFilterChange(values.length === options.length ? null : { type: "values", values });
  };

  const applyNumber = () => {
    const value = Number(numberValue);
    if (!Number.isFinite(value)) return;
    if (numberMode === "between" && !numberMax.trim()) return;
    const max = Number(numberMax);
    onFilterChange({ type: "number", mode: numberMode, value, ...(numberMode === "between" && Number.isFinite(max) ? { max } : {}) });
  };

  const applyDate = () => {
    if (!dateValue || dateMode === "between" && !dateMax) return;
    onFilterChange({ type: "date", mode: dateMode, value: dateValue, ...(dateMode === "between" ? { max: dateMax } : {}) });
  };

  return <>
    <button
      ref={triggerRef}
      type="button"
      className={`table-filter-trigger${active ? " active" : ""}`}
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-label={`Filter and sort ${column}`}
      onClick={() => { if (!open) updatePosition(); setOpen(value => !value); }}
    >
      <span>{column}</span>
      <span className="table-filter-indicators" aria-hidden="true">
        {filter ? <Filter size={12} /> : null}
        {sortDirection === "asc" ? <ArrowUp size={12} /> : sortDirection === "desc" ? <ArrowDown size={12} /> : <ChevronDown size={12} />}
      </span>
    </button>
    {open && typeof document !== "undefined" ? createPortal(
      <div
        ref={menuRef}
        className="table-filter-menu"
        role="dialog"
        aria-label={`${column} filter and sort`}
        style={{ top: position.top, left: position.left, maxHeight: position.maxHeight }}
      >
        <div className="table-filter-menu-heading"><strong>{column}</strong><button type="button" className="table-filter-close" aria-label="Close filter menu" onClick={() => setOpen(false)}><X size={16}/></button></div>
        <div className="table-filter-section">
          <span className="table-filter-section-label">Sort</span>
          <div className="table-filter-actions">
            <button type="button" className={sortDirection === "asc" ? "active" : ""} onClick={() => onSort("asc")}><ArrowUp size={14}/>{kind === "number" ? "Low to high" : kind === "date" ? "Oldest to newest" : "A to Z"}</button>
            <button type="button" className={sortDirection === "desc" ? "active" : ""} onClick={() => onSort("desc")}><ArrowDown size={14}/>{kind === "number" ? "High to low" : kind === "date" ? "Newest to oldest" : "Z to A"}</button>
          </div>
          {sortDirection ? <button type="button" className="table-filter-link" onClick={() => onSort(null)}>Clear sort</button> : null}
        </div>

        {kind === "values" ? <div className="table-filter-section">
          <span className="table-filter-section-label">Filter values</span>
          <input className="table-filter-search" value={optionSearch} onChange={event => setOptionSearch(event.target.value)} placeholder="Search values…" aria-label={`Search ${column} values`}/>
          <div className="table-filter-value-actions"><button type="button" onClick={() => onFilterChange(null)}>Select all</button><button type="button" onClick={() => onFilterChange({ type: "values", values: [] })}>Clear selection</button></div>
          <div className="table-filter-options">
            {filteredOptions.map(option => <label key={option} className="table-filter-option"><input type="checkbox" checked={selectedSet.has(option.toLocaleLowerCase())} onChange={() => toggleValue(option)}/><span>{option}</span></label>)}
            {!filteredOptions.length ? <span className="table-filter-empty">No matching values.</span> : null}
          </div>
        </div> : null}

        {kind === "text" ? <div className="table-filter-section">
          <span className="table-filter-section-label">Text filter</span>
          <select aria-label={`${column} text filter mode`} value={textMode} onChange={event => {
            const mode = event.target.value as "contains" | "equals";
            setTextMode(mode);
            if (filter?.type === "text" && filter.value) onFilterChange({ type: "text", mode, value: filter.value });
          }}><option value="contains">Contains</option><option value="equals">Equals</option></select>
          <input className="table-filter-search" value={filter?.type === "text" ? filter.value : ""} onChange={event => {
            const value = event.target.value;
            onFilterChange(value ? { type: "text", mode: textMode, value } : null);
          }} placeholder="Type to filter…" aria-label={`${column} filter value`}/>
        </div> : null}

        {kind === "number" ? <div className="table-filter-section">
          <span className="table-filter-section-label">Number filter</span>
          <select aria-label={`${column} number filter mode`} value={numberMode} onChange={event => setNumberMode(event.target.value as NumberTableFilter["mode"])}>
            <option value="eq">Equals</option><option value="gt">Greater than</option><option value="gte">Greater than or equal</option><option value="lt">Less than</option><option value="lte">Less than or equal</option><option value="between">Between</option>
          </select>
          <div className="table-filter-number-inputs"><input type="number" value={numberValue} onChange={event => setNumberValue(event.target.value)} aria-label={`${column} numeric value`}/>{numberMode === "between" ? <input type="number" value={numberMax} onChange={event => setNumberMax(event.target.value)} aria-label={`${column} maximum numeric value`}/> : null}</div>
          <div className="table-filter-value-actions"><button type="button" onClick={() => { setNumberMode("eq"); setNumberValue("0"); onFilterChange({ type: "number", mode: "eq", value: 0 }); }}>= 0</button><button type="button" onClick={() => { setNumberMode("gt"); setNumberValue("0"); onFilterChange({ type: "number", mode: "gt", value: 0 }); }}>&gt; 0</button><button type="button" onClick={applyNumber}>Apply</button></div>
        </div> : null}

        {kind === "date" ? <div className="table-filter-section">
          <span className="table-filter-section-label">Date filter</span>
          <select aria-label={`${column} date filter mode`} value={dateMode} onChange={event => setDateMode(event.target.value as DateTableFilter["mode"])}><option value="on">On</option><option value="before">Before</option><option value="after">After</option><option value="between">Between</option></select>
          <div className="table-filter-number-inputs"><input type="date" aria-label={`${column} date value`} value={dateValue} onChange={event => setDateValue(event.target.value)}/>{dateMode === "between" ? <input type="date" aria-label={`${column} maximum date value`} value={dateMax} onChange={event => setDateMax(event.target.value)}/> : null}</div>
          <button type="button" className="table-filter-apply" onClick={applyDate}>Apply date filter</button>
        </div> : null}

        {filter ? <div className="table-filter-footer"><button type="button" onClick={() => onFilterChange(null)}>Clear {column} filter</button></div> : null}
      </div>,
      document.body,
    ) : null}
  </>;
}
