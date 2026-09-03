import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";

type Order = {
  id: string;
  customer_id: string | null;
  order_number: string;
  work_type: string;
  product_name: string;
  product_format: string;
  requested_units: number;
  due_at: string | null;
  sku: string;
  priority: string;
  status: string;
  source_lot_reference: string;
  material_owner: string;
  packaging_owner: string;
  notes: string;
};
type Customer = {
  id: string;
  name: string;
  license_or_registration: string;
  contact_name: string;
  contact_email: string;
};
type MachineModel = {
  id: string;
  manufacturer: string;
  model: string;
  category: string;
  published_max_rate: number;
  rate_unit: string;
  planning_utilization_pct: number;
  published_min_operators: number;
  source_url: string;
};
type Machine = {
  id: string;
  machine_model_id: string;
  asset_code: string;
  display_name: string;
  effective_rate: number;
  rate_unit: string;
  preferred_crew_size: number;
  setup_minutes: number;
  cleanup_minutes: number;
};
type Hand = {
  id: string;
  default_crew_size: number;
  sticker_units_per_person_hour: number;
  case_pack_units_per_person_hour: number;
  final_cases_per_person_hour: number;
  setup_minutes: number;
  cleanup_minutes: number;
};
type Product = {
  id: string;
  sku: string;
  name: string;
  item_type: string;
  base_unit: string;
  unit_cost: number;
};
type Lot = {
  id: string;
  product_id: string;
  lot_code: string;
  compliance_package_id: string;
  location_code: string;
  status: string;
  on_hand: number;
};
type Transaction = {
  id: string;
  occurred_at: string;
  lot_id: string;
  transaction_type: string;
  quantity_delta: number;
  unit: string;
  reason: string;
  reference: string;
  actor: string;
};
type Reservation = {
  id: string;
  production_order_id: string;
  lot_id: string;
  quantity: number;
  unit: string;
  status: string;
};
type Crew = {
  id: string;
  work_date: string;
  shift_name: string;
  available_people: number;
  shift_hours: number;
  notes: string;
};
type Actual = {
  id: string;
  production_order_id: string;
  actual_units: number;
  scrap_units: number;
  rework_units: number;
  actual_machine_hours: number;
  actual_labor_hours: number;
  completed_at: string;
  notes: string;
};
type Workspace = {
  metrics: {
    open_orders: number;
    units_planned: number;
    external_jobs: number;
    customers: number;
  };
  readiness: Record<string, unknown>[];
  orders: Order[];
  customers: Customer[];
  machine_models: MachineModel[];
  machines: Machine[];
  hand_labor: Hand;
  products: Product[];
  lots: Lot[];
  transactions: Transaction[];
  reservations: Reservation[];
  crew: Crew[];
  actuals: Actual[];
};
type OptimizerRow = {
  eligible: boolean;
  product: string;
  format: string;
  unit_size_g: number;
  revenue_per_unit: number;
  bulk_cost_per_g: number;
  packaging_cost_per_unit: number;
  other_cost_per_unit: number;
  machine_units_per_hour: number;
  machine_crew: number;
  machine_cost_per_hour: number;
  units_per_case: number;
  max_allocation_pct: number;
};
type Recommendation = {
  product: string;
  format: string;
  units: number;
  allocated_g: number;
  cases: number;
  revenue: number;
  total_cost: number;
  profit: number;
  margin_pct: number;
  profit_per_input_lb: number;
  profit_per_labor_hour: number;
  machine_hours: number;
  hand_labor_hours: number;
  total_labor_hours: number;
};
type ProductionQueueRow = {
  order_id: string;
  Order: string;
  Product: string;
  Status: string;
  Planned: number;
  Actual: number;
  "Attainment %": number;
  COGS: number;
  "Cost / Unit": number;
  Reservations: number;
  QA: string;
  Attention: string;
};
type ProductionDetail = {
  order: Order & { due_at: string | null };
  requirements: Record<string, unknown>[];
  reservations: Reservation[];
  outputs: {
    id: string;
    product_id: string;
    position: number;
    label: string;
    planned_quantity: number;
    actual_quantity: number;
    unit: string;
    status: string;
    lot_id: string | null;
  }[];
  events: Record<string, unknown>[];
  qa_events: Record<string, unknown>[];
  cogs: Record<string, number>;
  attainment_pct: number;
};

const FORMATS = [
  "Pouched flower — 3.5 g",
  "Pouched flower — 7 g",
  "Pouched flower — 14 g",
  "Pouched flower — 1 oz (28 g)",
  "Jarred flower",
  "Pre-roll",
  "Pre-roll pack",
  "Infused pre-roll",
  "Infused pre-roll pack",
  "Other",
];
const optimizerRow = (
  product: string,
  format: string,
  size: number,
  revenue: number,
  packaging: number,
  other: number,
  rate: number,
  crew: number,
  machineCost: number,
  cases: number,
): OptimizerRow => ({
  eligible: true,
  product,
  format,
  unit_size_g: size,
  revenue_per_unit: revenue,
  bulk_cost_per_g: 1.5,
  packaging_cost_per_unit: packaging,
  other_cost_per_unit: other,
  machine_units_per_hour: rate,
  machine_crew: crew,
  machine_cost_per_hour: machineCost,
  units_per_case: cases,
  max_allocation_pct: 100,
});
const OPTIMIZER_DEFAULTS = [
  optimizerRow(
    "3.5 g flower pouch",
    FORMATS[0],
    3.5,
    18,
    0.75,
    0.1,
    900,
    3,
    35,
    50,
  ),
  optimizerRow(
    "7 g flower pouch",
    FORMATS[1],
    7,
    32,
    0.85,
    0.12,
    750,
    3,
    35,
    30,
  ),
  optimizerRow(
    "14 g flower pouch",
    FORMATS[2],
    14,
    58,
    0.95,
    0.15,
    600,
    3,
    35,
    20,
  ),
  optimizerRow(
    "1 oz flower pouch",
    FORMATS[3],
    28,
    105,
    1.1,
    0.18,
    450,
    3,
    35,
    12,
  ),
  optimizerRow(
    "3.5 g flower jar",
    FORMATS[4],
    3.5,
    20,
    1.15,
    0.1,
    500,
    4,
    25,
    48,
  ),
  optimizerRow("1 g pre-roll", FORMATS[5], 1, 6, 0.35, 0.08, 1200, 4, 45, 100),
  optimizerRow(
    "5-pack pre-roll",
    FORMATS[6],
    2.5,
    16,
    0.9,
    0.12,
    350,
    5,
    45,
    40,
  ),
];
const OPTIMIZER_LABELS: Record<keyof OptimizerRow, string> = {
  eligible: "Use",
  product: "Product / SKU",
  format: "Format",
  unit_size_g: "Grams/Unit",
  revenue_per_unit: "Revenue/Unit",
  bulk_cost_per_g: "Bulk Cost $/g",
  packaging_cost_per_unit: "Packaging/Unit",
  other_cost_per_unit: "Other Cost/Unit",
  machine_units_per_hour: "Machine Units/Hr",
  machine_crew: "Machine Crew",
  machine_cost_per_hour: "Machine $/Hr",
  units_per_case: "Units/Case",
  max_allocation_pct: "Max Allocation %",
};
const TABS = [
  "Dashboard",
  "New Job",
  "Schedule",
  "Resources",
  "Inventory & BOM",
  "Customers",
  "Performance",
] as const;
const today = () => {
  const value = new Date(),
    offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
};
const blankOrder = () => ({
  order_number: "",
  work_type: "Internal",
  requested_units: 1,
  product_name: "",
  product_format: FORMATS[0],
  sku: "",
  customer_id: "",
  due_date: today(),
  priority: "Normal",
  source_lot_reference: "",
  material_owner: "Internal",
  packaging_owner: "Internal",
  notes: "",
});

export function ProductionPage() {
  const client = useQueryClient();
  const data = useQuery({
    queryKey: ["coman-parity"],
    queryFn: ({ signal }) =>
      apiGet<Workspace>("/api/v1/coman-parity/workspace", signal),
  });
  const [tab, setTab] = useState<(typeof TABS)[number]>("Dashboard");
  const [controlOpen, setControlOpen] = useState(false);
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["coman-parity"] });
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Production Ops</div>
          <h1>Co-Man Production</h1>
          <p>
            Track internal production and customer-owned contract packaging in
            one durable queue.
          </p>
        </div>
        <div className="heading-actions">
          <button className="secondary" onClick={() => setControlOpen(true)}>
            Production Control
          </button>
        </div>
      </div>
      {data.isLoading ? (
        <div className="state">Loading Co-Man Production…</div>
      ) : null}
      {data.isError ? (
        <div className="form-error">{data.error.message}</div>
      ) : null}
      {data.data ? (
        <>
          <div className="metrics four">
            <Metric l="Open Orders" v={String(data.data.metrics.open_orders)} />
            <Metric
              l="Units Planned"
              v={data.data.metrics.units_planned.toLocaleString()}
            />
            <Metric
              l="External Jobs"
              v={String(data.data.metrics.external_jobs)}
            />
            <Metric l="Customers" v={String(data.data.metrics.customers)} />
          </div>
          <div className="view-tabs coman-tabs">
            {TABS.map((value) => (
              <button
                key={value}
                className={tab === value ? "active" : ""}
                onClick={() => setTab(value)}
              >
                {value}
              </button>
            ))}
          </div>
          {tab === "Dashboard" ? (
            <Dashboard value={data.data} onSaved={refresh} />
          ) : tab === "New Job" ? (
            <NewJob value={data.data} onSaved={refresh} />
          ) : tab === "Schedule" ? (
            <Schedule value={data.data} onSaved={refresh} />
          ) : tab === "Resources" ? (
            <Resources value={data.data} onSaved={refresh} />
          ) : tab === "Inventory & BOM" ? (
            <InventoryBom value={data.data} onSaved={refresh} />
          ) : tab === "Customers" ? (
            <Customers value={data.data} onSaved={refresh} />
          ) : (
            <Performance value={data.data} onSaved={refresh} />
          )}
        </>
      ) : null}
      {controlOpen && data.data ? (
        <ProductionControlDrawer
          products={data.data.products}
          close={() => setControlOpen(false)}
        />
      ) : null}
    </div>
  );
}

function Dashboard({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState("All"),
    [priority, setPriority] = useState("All"),
    [format, setFormat] = useState("All"),
    [orderId, setOrderId] = useState(value.orders[0]?.id ?? ""),
    [newStatus, setNewStatus] = useState("Draft"),
    [duplicate, setDuplicate] = useState("");
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object }) =>
      apiPost(path, body),
    onSuccess: onSaved,
  });
  const rows = value.orders
    .filter(
      (row) =>
        (status === "All" || title(row.status) === status) &&
        (priority === "All" || title(row.priority) === priority) &&
        (format === "All" || title(row.product_format) === format),
    )
    .map((row) => orderFrame(row, value.customers));
  return (
    <section className="coman-workspace">
      <h4>Setup readiness</h4>
      <DataTable rows={value.readiness} />
      <h4>Current production queue</h4>
      <div className="three-col">
        <Select
          label="Status filter"
          value={status}
          values={[
            "All",
            ...unique(value.orders.map((row) => title(row.status))),
          ]}
          set={setStatus}
        />
        <Select
          label="Priority filter"
          value={priority}
          values={[
            "All",
            ...unique(value.orders.map((row) => title(row.priority))),
          ]}
          set={setPriority}
        />
        <Select
          label="Format filter"
          value={format}
          values={[
            "All",
            ...unique(value.orders.map((row) => title(row.product_format))),
          ]}
          set={setFormat}
        />
      </div>
      {rows.length ? (
        <DataTable rows={rows} />
      ) : (
        <Info>
          No production orders yet. Add the first job in Production Orders.
        </Info>
      )}
      {value.orders.length ? (
        <>
          <h4>Queue actions</h4>
          <div className="two-col">
            <Select
              label="Order"
              value={orderId}
              values={value.orders.map((row) => row.id)}
              labels={Object.fromEntries(
                value.orders.map((row) => [
                  row.id,
                  `${row.order_number} — ${row.product_name}`,
                ]),
              )}
              set={setOrderId}
            />
            <Select
              label="New status"
              value={newStatus}
              values={[
                "Draft",
                "Scheduled",
                "In Progress",
                "On Hold",
                "Complete",
                "Cancelled",
              ]}
              set={setNewStatus}
            />
          </div>
          <div className="audit-actions">
            <button
              className="primary"
              onClick={() =>
                mutation.mutate({
                  path: `/api/v1/coman-parity/orders/${orderId}/status`,
                  body: {
                    status: newStatus.toLowerCase().replaceAll(" ", "_"),
                  },
                })
              }
            >
              Update status
            </button>
            <details className="streamlit-expander inline-popover">
              <summary>Duplicate recurring job</summary>
              <div className="streamlit-expander-body">
                <Text
                  label="New order number"
                  value={duplicate}
                  set={setDuplicate}
                />
                <button
                  className="secondary"
                  onClick={() =>
                    mutation.mutate({
                      path: `/api/v1/coman-parity/orders/${orderId}/duplicate`,
                      body: { new_order_number: duplicate },
                    })
                  }
                >
                  Create duplicate
                </button>
              </div>
            </details>
          </div>
        </>
      ) : null}
      <MutationState
        value={mutation}
        success={
          mutation.variables?.path.endsWith("/status")
            ? "Order status updated."
            : "Recurring job duplicated."
        }
      />
    </section>
  );
}

function NewJob({ value, onSaved }: { value: Workspace; onSaved: () => void }) {
  const [bulk, setBulk] = useState(10),
    [unit, setUnit] = useState("Pounds"),
    [loss, setLoss] = useState(5),
    [goal, setGoal] = useState("Maximum total profit"),
    [economics, setEconomics] = useState("Internal / owned product"),
    [labor, setLabor] = useState(22),
    [products, setProducts] = useState(OPTIMIZER_DEFAULTS),
    [selected, setSelected] = useState(0),
    [order, setOrder] = useState(blankOrder),
    [prefilled, setPrefilled] = useState(false);
  const request = {
    bulk_weight: bulk,
    bulk_unit: unit,
    expected_loss_pct: loss,
    optimization_goal: goal,
    labor_rate: labor,
    products,
  };
  const optimizer = useQuery({
    queryKey: ["coman-optimizer", request],
    queryFn: () =>
      apiPost<{
        usable_weight_g: number;
        rates_ready: boolean;
        recommendations: Recommendation[];
      }>("/api/v1/coman-parity/optimizer", request),
    retry: false,
  });
  const prefill = useMutation({
    mutationFn: () =>
      apiPost<Record<string, string | number>>(
        "/api/v1/coman-parity/optimizer/prefill",
        {
          recommendation: optimizer.data?.recommendations[selected],
          work_type_label: economics,
        },
      ),
    onSuccess: (row) => {
      setOrder({ ...blankOrder(), ...row, customer_id: "" });
      setPrefilled(true);
    },
  });
  const create = useMutation({
    mutationFn: () =>
      apiPost("/api/v1/coman-parity/orders", {
        ...order,
        work_type: order.work_type.toLowerCase(),
        product_format: order.product_format.toLowerCase(),
        customer_id:
          order.work_type === "External" ? order.customer_id || null : null,
        priority: order.priority.toLowerCase(),
        material_owner: order.material_owner.toLowerCase(),
        packaging_owner: order.packaging_owner.toLowerCase(),
      }),
    onSuccess: () => {
      setOrder(blankOrder());
      setPrefilled(false);
      onSaved();
    },
  });
  const recs = optimizer.data?.recommendations ?? [],
    totalProfit = sum(recs, "profit"),
    totalRevenue = sum(recs, "revenue"),
    totalLabor = sum(recs, "total_labor_hours"),
    allocated = sum(recs, "allocated_g");
  return (
    <section className="coman-workspace">
      <h4>Weight-based production recommendation</h4>
      <p>
        Enter the bulk available, then compare finished-product uses by
        contribution profit. Recommendations are advisory until you create a
        committed production order below.
      </p>
      <div className="four-col">
        <Num
          label="Available bulk weight"
          value={bulk}
          set={setBulk}
          step={1}
        />
        <Select
          label="Weight unit"
          value={unit}
          values={["Pounds", "Grams", "Kilograms"]}
          set={setUnit}
        />
        <Num
          label="Expected process loss %"
          value={loss}
          set={setLoss}
          max={50}
          step={0.5}
        />
        <Select
          label="Optimization goal"
          value={goal}
          values={["Maximum total profit", "Maximum profit per labor hour"]}
          set={setGoal}
        />
      </div>
      <div className="three-col">
        <Select
          label="Economics"
          value={economics}
          values={["Internal / owned product", "External co-man service"]}
          set={setEconomics}
        />
        <Num
          label="Loaded labor cost $/hour"
          value={labor}
          set={setLabor}
          step={1}
        />
        <Metric
          l="Usable weight after loss"
          v={`${(optimizer.data?.usable_weight_g ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} g`}
        />
      </div>
      <Info>
        {economics.startsWith("External")
          ? "For customer-owned bulk, set Bulk Cost $/g to $0 and enter your packaging/service fee as Revenue/Unit."
          : "For owned product, Revenue/Unit is expected wholesale or transfer revenue and Bulk Cost $/g is your cannabis cost basis."}
      </Info>
      <OptimizerTable rows={products} setRows={setProducts} />
      {optimizer.data && !optimizer.data.rates_ready ? (
        <Warn>
          Set all hand-labor rates in Resources for a complete profit
          recommendation. Missing rates currently contribute zero labor time.
        </Warn>
      ) : null}
      {recs.length ? (
        <>
          <div className="metrics four">
            <Metric l="Recommended Profit" v={money(totalProfit)} />
            <Metric
              l="Contribution Margin"
              v={`${(totalRevenue ? (totalProfit / totalRevenue) * 100 : 0).toFixed(1)}%`}
            />
            <Metric l="Labor Required" v={`${totalLabor.toFixed(1)} hr`} />
            <Metric l="Bulk Allocated" v={`${allocated.toFixed(1)} g`} />
          </div>
          <DataTable
            rows={recs.map((row, index) => ({
              Rank: index + 1,
              Product: row.product,
              Format: row.format,
              Units: row.units,
              "Bulk Grams": round(row.allocated_g),
              Cases: row.cases,
              Revenue: round2(row.revenue),
              "Total Cost": round2(row.total_cost),
              Profit: round2(row.profit),
              "Margin %": round(row.margin_pct),
              "Profit/Input Lb": round(row.profit_per_input_lb),
              "Profit/Labor Hr": round(row.profit_per_labor_hour),
              "Machine Hours": round(row.machine_hours),
              "Hand Labor Hours": round(row.hand_labor_hours),
            }))}
          />
          <p>
            Remaining usable bulk:{" "}
            {Math.max(
              0,
              (optimizer.data?.usable_weight_g ?? 0) - allocated,
            ).toFixed(1)}{" "}
            g. Use Max Allocation % to reserve demand or split bulk across
            products. Final case pack, case pack, and stickering are included
            from the facility&apos;s Resources rates.
          </p>
          <div className="two-col">
            <Select
              label="Recommendation to turn into a job"
              value={String(selected)}
              values={recs.map((_, index) => String(index))}
              labels={Object.fromEntries(
                recs.map((row, index) => [
                  String(index),
                  `#${index + 1} · ${row.product} · ${row.units.toLocaleString()} units · ${money(row.profit)} profit`,
                ]),
              )}
              set={(value) => setSelected(Number(value))}
            />
            <button className="primary" onClick={() => prefill.mutate()}>
              Build production order
            </button>
          </div>
        </>
      ) : (
        <Info>
          Enter bulk weight and at least one eligible product with a valid
          grams-per-unit value.
        </Info>
      )}
      <hr />
      <h4>Committed production order</h4>
      {prefilled ? (
        <div className="two-col">
          <Info>
            Optimizer recommendation loaded. Review the editable order details,
            select a customer for external work, then save.
          </Info>
          <button
            className="secondary"
            onClick={() => {
              setOrder(blankOrder());
              setPrefilled(false);
            }}
          >
            Clear prefill
          </button>
        </div>
      ) : (
        <p>
          Use this path when a customer or internal plan already requires a
          specific finished-unit quantity.
        </p>
      )}
      <OrderForm
        order={order}
        setOrder={setOrder}
        customers={value.customers}
        submit={() => create.mutate()}
      />
      <MutationState value={create} success="Production order was saved." />
    </section>
  );
}

function Schedule({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [crew, setCrew] = useState({
    work_date: today(),
    shift_name: "Day",
    available_people: 1,
    shift_hours: 8,
    notes: "",
  });
  const [orderId, setOrderId] = useState(
      value.orders.find(
        (row) => !["complete", "cancelled"].includes(row.status),
      )?.id ?? "",
    ),
    [machineId, setMachineId] = useState(value.machines[0]?.id ?? ""),
    [shift, setShift] = useState(8),
    [unitsCase, setUnitsCase] = useState(100);
  const save = useMutation({
    mutationFn: () => apiPost("/api/v1/coman-parity/crew", crew),
    onSuccess: () => {
      setCrew({
        work_date: today(),
        shift_name: "Day",
        available_people: 1,
        shift_hours: 8,
        notes: "",
      });
      onSaved();
    },
  });
  const order = value.orders.find((row) => row.id === orderId),
    machine = value.machines.find((row) => row.id === machineId);
  const openOrders = useMemo(
    () =>
      value.orders.filter(
        (row) => !["complete", "cancelled"].includes(row.status),
      ),
    [value.orders],
  );
  const capacity = useQuery({
    queryKey: ["coman-capacity", orderId, machineId, shift, unitsCase],
    enabled: !!order && !!machine,
    queryFn: () =>
      apiPost<{
        machine: Record<string, number>;
        hand: Record<string, number | string> | null;
        rates_ready: boolean;
      }>("/api/v1/coman-parity/capacity", {
        requested_units: order!.requested_units,
        effective_rate: machine!.effective_rate,
        crew_size: machine!.preferred_crew_size,
        setup_minutes: machine!.setup_minutes,
        cleanup_minutes: machine!.cleanup_minutes,
        shift_hours: shift,
        units_per_case: unitsCase,
      }),
  });
  return (
    <section className="coman-workspace">
      <h4>Crew availability</h4>
      <div className="four-col">
        <DateField
          label="Work date"
          value={crew.work_date}
          set={(v) => setCrew({ ...crew, work_date: v })}
        />
        <Select
          label="Shift"
          value={crew.shift_name}
          values={["Day", "Evening", "Night", "Weekend"]}
          set={(v) => setCrew({ ...crew, shift_name: v })}
        />
        <Num
          label="People available"
          value={crew.available_people}
          set={(v) => setCrew({ ...crew, available_people: v })}
          step={1}
        />
        <Num
          label="Shift hours"
          value={crew.shift_hours}
          set={(v) => setCrew({ ...crew, shift_hours: v })}
          min={1}
          step={0.5}
        />
      </div>
      <Text
        label="Crew notes"
        value={crew.notes}
        set={(v) => setCrew({ ...crew, notes: v })}
        placeholder="Callouts, training, restricted assignments"
      />
      <button className="primary" onClick={() => save.mutate()}>
        Save crew capacity
      </button>
      {value.crew.length ? (
        <DataTable
          rows={value.crew.map((row) => ({
            Date: row.work_date,
            Shift: row.shift_name,
            People: row.available_people,
            Hours: row.shift_hours,
            "Available Labor-Hours": row.available_people * row.shift_hours,
            Notes: row.notes,
          }))}
        />
      ) : null}
      <h4>Machine capacity estimate</h4>
      {!openOrders.length || !value.machines.length ? (
        <Info>
          Add at least one production order and one facility machine to
          calculate capacity.
        </Info>
      ) : (
        <>
          <div className="three-col">
            <Select
              label="Production order"
              value={orderId}
              values={openOrders.map((row) => row.id)}
              labels={Object.fromEntries(
                openOrders.map((row) => [
                  row.id,
                  `${row.order_number} — ${row.product_name} (${row.requested_units.toLocaleString()} units)`,
                ]),
              )}
              set={setOrderId}
            />
            <Select
              label="Facility machine"
              value={machineId}
              values={value.machines.map((row) => row.id)}
              labels={Object.fromEntries(
                value.machines.map((row) => [
                  row.id,
                  `${row.asset_code} — ${row.display_name}`,
                ]),
              )}
              set={setMachineId}
            />
            <Num
              label="Shift length (hours)"
              value={shift}
              set={setShift}
              min={1}
              step={0.5}
            />
          </div>
          {capacity.data ? (
            <>
              <div className="metrics four">
                <Metric
                  l="Machine Run"
                  v={`${Number(capacity.data.machine.run_hours).toFixed(1)} hr`}
                />
                <Metric
                  l="Elapsed Time"
                  v={`${Number(capacity.data.machine.elapsed_hours).toFixed(1)} hr`}
                />
                <Metric
                  l="Labor Required"
                  v={`${Number(capacity.data.machine.labor_hours).toFixed(1)} labor hr`}
                />
                <Metric
                  l="Shifts Required"
                  v={String(capacity.data.machine.shifts)}
                />
              </div>
              <p>
                This is a single-machine estimate using your observed rate.
                Labor routing for breakdown, weighing, tubing, stickering,
                casing, packing, QA, and sanitation comes next.
              </p>
              <h4>Required downstream hand labor</h4>
              <Num
                label="Finished units per final case"
                value={unitsCase}
                set={setUnitsCase}
                min={1}
                step={1}
              />
              {capacity.data.hand ? (
                <>
                  <div className="metrics four">
                    <Metric
                      l="Hand-Labor Elapsed"
                      v={`${Number(capacity.data.hand.elapsed_hours).toFixed(1)} hr`}
                    />
                    <Metric
                      l="Hand Labor Required"
                      v={`${Number(capacity.data.hand.labor_hours).toFixed(1)} labor hr`}
                    />
                    <Metric
                      l="Final Cases"
                      v={String(capacity.data.hand.cases)}
                    />
                    <Metric
                      l="Hand-Labor Bottleneck"
                      v={String(capacity.data.hand.bottleneck)}
                    />
                  </div>
                  <Info>
                    Estimated end-to-end completion time:{" "}
                    {(
                      Number(capacity.data.machine.elapsed_hours) +
                      Number(capacity.data.hand.elapsed_hours)
                    ).toFixed(1)}{" "}
                    hours, including the machine and required hand-labor stages.
                  </Info>
                  {value.crew.length ? (
                    (() => {
                      const available =
                        value.crew[0].available_people *
                        value.crew[0].shift_hours;
                      const required =
                        Number(capacity.data.machine.labor_hours) +
                        Number(capacity.data.hand.labor_hours);
                      return available >= required ? (
                        <Info>
                          Crew capacity check: {available.toFixed(1)}{" "}
                          labor-hours available; {required.toFixed(1)} required.
                        </Info>
                      ) : (
                        <Warn>
                          Crew shortage: {required.toFixed(1)} labor-hours
                          required versus {available.toFixed(1)} available (
                          {Math.abs(available - required).toFixed(1)} short).
                        </Warn>
                      );
                    })()
                  ) : (
                    <Warn>
                      Add crew availability above to check whether the scheduled
                      shift can support this job.
                    </Warn>
                  )}
                </>
              ) : (
                <Warn>
                  Configure all three observed rates in Hand Labor to include
                  downstream completion time.
                </Warn>
              )}
            </>
          ) : null}
        </>
      )}
      <MutationState value={save} success="Crew availability saved." />
    </section>
  );
}

function Resources({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [query, setQuery] = useState(""),
    [machine, setMachine] = useState({
      machine_model_id: value.machine_models[0]?.id ?? "",
      asset_code: "",
      display_name: value.machine_models[0]?.model ?? "",
      effective_rate: 100,
      preferred_crew_size: 1,
      setup_minutes: 30,
      cleanup_minutes: 30,
    }),
    [hand, setHand] = useState(value.hand_labor);
  const mutate = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object }) =>
      apiPost(path, body),
    onSuccess: (_result, variables) => {
      if (variables.path.endsWith("/machines")) {
        setMachine({
          machine_model_id: value.machine_models[0]?.id ?? "",
          asset_code: "",
          display_name: value.machine_models[0]?.model ?? "",
          effective_rate: 100,
          preferred_crew_size: 1,
          setup_minutes: 30,
          cleanup_minutes: 30,
        });
      }
      onSaved();
    },
  });
  const models = value.machine_models.filter((row) =>
    `${row.manufacturer} ${row.model} ${row.category}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <section className="coman-workspace">
      <h4>Facility equipment and observed rates</h4>
      <p>
        Published specifications are a starting reference. Effective rate should
        be what this facility can repeatedly achieve with its product,
        operators, setup, and quality requirements.
      </p>
      {!value.machine_models.length ? (
        <Warn>No machine benchmark models are loaded yet.</Warn>
      ) : null}
      {value.machine_models.length ? (
        <>
          <details className="streamlit-expander">
            <summary>Browse benchmark library</summary>
            <div className="streamlit-expander-body">
              <Text
                label="Search manufacturer, model, or category"
                value={query}
                set={setQuery}
                placeholder="Vape-Jet, Ishida, pre-roll, grinder…"
              />
              <DataTable
                rows={models.map((row) => ({
                  Manufacturer: row.manufacturer,
                  Model: row.model,
                  Category: title(row.category),
                  "Published Max": row.published_max_rate,
                  "Rate Unit": row.rate_unit,
                  "Planning Utilization %": row.planning_utilization_pct,
                  "Minimum Operators": row.published_min_operators,
                  "Manufacturer source": row.source_url,
                }))}
              />
            </div>
          </details>
          {value.machine_models.length ? (
            <p>
              Published maximum:{" "}
              {value.machine_models.find(
                (row) => row.id === machine.machine_model_id,
              )?.published_max_rate ?? 0}{" "}
              {value.machine_models.find(
                (row) => row.id === machine.machine_model_id,
              )?.rate_unit ?? "units/hour"}
              ; planning reference utilization:{" "}
              {value.machine_models.find(
                (row) => row.id === machine.machine_model_id,
              )?.planning_utilization_pct ?? 0}
              %
            </p>
          ) : null}
          <div className="three-col">
            <Select
              label="Machine model*"
              value={machine.machine_model_id}
              values={value.machine_models.map((row) => row.id)}
              labels={Object.fromEntries(
                value.machine_models.map((row) => [
                  row.id,
                  `${row.manufacturer} — ${row.model} (${row.category})`,
                ]),
              )}
              set={(id) => {
                const model = value.machine_models.find((row) => row.id === id);
                setMachine({
                  ...machine,
                  machine_model_id: id,
                  display_name: model?.model ?? "",
                });
              }}
            />
            <Text
              label="Asset code*"
              value={machine.asset_code}
              set={(v) => setMachine({ ...machine, asset_code: v })}
              placeholder="PR-01"
            />
            <Text
              label="Facility name*"
              value={machine.display_name}
              set={(v) => setMachine({ ...machine, display_name: v })}
            />
            <Num
              label="Observed effective rate (units/hour)*"
              value={machine.effective_rate}
              set={(v) => setMachine({ ...machine, effective_rate: v })}
              min={0.1}
              step={10}
            />
            <Num
              label="Preferred crew"
              value={machine.preferred_crew_size}
              set={(v) => setMachine({ ...machine, preferred_crew_size: v })}
              min={1}
              step={1}
            />
            <Num
              label="Setup minutes"
              value={machine.setup_minutes}
              set={(v) => setMachine({ ...machine, setup_minutes: v })}
              step={5}
            />
            <Num
              label="Cleanup minutes"
              value={machine.cleanup_minutes}
              set={(v) => setMachine({ ...machine, cleanup_minutes: v })}
              step={5}
            />
          </div>
          <button
            className="primary"
            onClick={() =>
              mutate.mutate({
                path: "/api/v1/coman-parity/machines",
                body: machine,
              })
            }
          >
            Add facility machine
          </button>
        </>
      ) : null}
      {value.machines.length ? (
        <DataTable
          rows={value.machines.map((row) => ({
            Asset: row.asset_code,
            Machine: row.display_name,
            Model:
              value.machine_models.find(
                (model) => model.id === row.machine_model_id,
              )?.model ?? "Unknown",
            "Observed Units/Hour": row.effective_rate,
            Crew: row.preferred_crew_size,
            "Setup Min": row.setup_minutes,
            "Cleanup Min": row.cleanup_minutes,
          }))}
        />
      ) : null}
      <hr />
      <h4>Required hand-labor area</h4>
      <p>
        Stickering, case packing, and final case packing are included for every
        facility. Enter repeatable per-person rates from your operation.
      </p>
      <div className="three-col">
        <Num
          label="Default hand-labor crew"
          value={hand.default_crew_size}
          set={(v) => setHand({ ...hand, default_crew_size: v })}
          min={1}
          step={1}
        />
        <Num
          label="Stickering units/person/hour*"
          value={hand.sticker_units_per_person_hour}
          set={(v) => setHand({ ...hand, sticker_units_per_person_hour: v })}
          step={10}
        />
        <Num
          label="Case-pack units/person/hour*"
          value={hand.case_pack_units_per_person_hour}
          set={(v) => setHand({ ...hand, case_pack_units_per_person_hour: v })}
          step={10}
        />
        <Num
          label="Final cases/person/hour*"
          value={hand.final_cases_per_person_hour}
          set={(v) => setHand({ ...hand, final_cases_per_person_hour: v })}
          step={1}
        />
        <Num
          label="Area setup minutes"
          value={hand.setup_minutes}
          set={(v) => setHand({ ...hand, setup_minutes: v })}
          step={5}
        />
        <Num
          label="Area cleanup minutes"
          value={hand.cleanup_minutes}
          set={(v) => setHand({ ...hand, cleanup_minutes: v })}
          step={5}
        />
      </div>
      <button
        className="primary"
        onClick={() =>
          mutate.mutate({ path: "/api/v1/coman-parity/hand-labor", body: hand })
        }
      >
        Save hand-labor rates
      </button>
      <MutationState
        value={mutate}
        success={
          mutate.variables?.path.endsWith("/machines")
            ? "Facility machine was added."
            : "Hand-labor rates were saved."
        }
      />
    </section>
  );
}

function InventoryBom({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [product, setProduct] = useState({
      sku: "",
      name: "",
      item_type: "cannabis",
      base_unit: "g",
      unit_cost: 0,
    }),
    [lot, setLot] = useState({
      product_id: value.products[0]?.id ?? "",
      lot_code: "",
      compliance_package_id: "",
      location_code: "UNASSIGNED",
      opening_quantity: 0,
      unit: value.products[0]?.base_unit ?? "g",
    }),
    [movement, setMovement] = useState({
      lot_id: value.lots[0]?.id ?? "",
      transaction_type: "receipt",
      quantity: 1,
      unit: "g",
      reason: "",
    }),
    [reservation, setReservation] = useState({
      production_order_id: value.orders[0]?.id ?? "",
      lot_id: value.lots[0]?.id ?? "",
      quantity: 1,
      unit: "g",
    }),
    [bom, setBom] = useState({
      output_product_id:
        value.products.find((row) =>
          ["wip", "finished_good"].includes(row.item_type),
        )?.id ?? "",
      output_quantity: 1,
      expected_loss_pct: 0,
      components: [] as {
        input_product_id: string;
        quantity: number;
        unit: string;
      }[],
    });
  const mutate = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object }) =>
      apiPost(path, body),
    onSuccess: (_result, variables) => {
      if (variables.path.endsWith("/products")) {
        setProduct({
          sku: "",
          name: "",
          item_type: "cannabis",
          base_unit: "g",
          unit_cost: 0,
        });
      } else if (variables.path.endsWith("/lots")) {
        setLot((current) => ({
          ...current,
          lot_code: "",
          compliance_package_id: "",
          location_code: "UNASSIGNED",
          opening_quantity: 0,
        }));
      } else if (variables.path.endsWith("/movements")) {
        setMovement((current) => ({ ...current, quantity: 1, reason: "" }));
      } else if (variables.path.endsWith("/reservations")) {
        setReservation((current) => ({ ...current, quantity: 1 }));
      }
      onSaved();
    },
  });
  const productById = Object.fromEntries(
    value.products.map((row) => [row.id, row]),
  );
  const reserved = value.reservations
    .filter((row) => row.status === "reserved")
    .reduce<
      Record<string, number>
    >((acc, row) => ({ ...acc, [row.lot_id]: (acc[row.lot_id] ?? 0) + row.quantity }), {});
  const openOrders = useMemo(
    () =>
      value.orders.filter(
        (row) => !["complete", "cancelled"].includes(row.status),
      ),
    [value.orders],
  );
  useEffect(() => {
    if (!lot.product_id && value.products[0]) {
      setLot((current) => ({
        ...current,
        product_id: value.products[0].id,
        unit: value.products[0].base_unit,
      }));
    }
    if (!movement.lot_id && value.lots[0]) {
      const source = value.products.find(
        (row) => row.id === value.lots[0].product_id,
      );
      setMovement((current) => ({
        ...current,
        lot_id: value.lots[0].id,
        unit: source?.base_unit ?? "g",
      }));
      setReservation((current) => ({
        ...current,
        lot_id: value.lots[0].id,
        unit: source?.base_unit ?? "g",
      }));
    }
    if (!reservation.production_order_id && openOrders[0]) {
      setReservation((current) => ({
        ...current,
        production_order_id: openOrders[0].id,
      }));
    }
    if (!bom.output_product_id) {
      const output = value.products.find((row) =>
        ["wip", "finished_good"].includes(row.item_type),
      );
      if (output) {
        setBom((current) => ({ ...current, output_product_id: output.id }));
      }
    }
  }, [
    bom.output_product_id,
    lot.product_id,
    movement.lot_id,
    openOrders,
    reservation.production_order_id,
    value.lots,
    value.products,
  ]);
  return (
    <section className="coman-workspace">
      <h4>Product and material control</h4>
      <p>
        Track cannabis, packaging, work-in-process, and finished goods by lot.
        Balances come from an append-only transaction ledger so production
        history remains auditable.
      </p>
      <div className="two-col">
        <details className="streamlit-expander" open={!value.products.length}>
          <summary>Add a product or material</summary>
          <div className="streamlit-expander-body">
            <Text
              label="SKU / item code*"
              value={product.sku}
              set={(v) => setProduct({ ...product, sku: v })}
            />
            <Text
              label="Product or material name*"
              value={product.name}
              set={(v) => setProduct({ ...product, name: v })}
            />
            <Select
              label="Item type"
              value={product.item_type}
              values={["cannabis", "packaging", "wip", "finished_good"]}
              labels={{
                cannabis: "Cannabis",
                packaging: "Packaging",
                wip: "Wip",
                finished_good: "Finished Good",
              }}
              set={(v) => setProduct({ ...product, item_type: v })}
            />
            <Select
              label="Base unit"
              value={product.base_unit}
              values={["g", "lb", "each", "case", "mL"]}
              set={(v) => setProduct({ ...product, base_unit: v })}
            />
            <Num
              label="Standard cost per base unit"
              value={product.unit_cost}
              set={(v) => setProduct({ ...product, unit_cost: v })}
              step={0.01}
            />
            <button
              className="primary"
              onClick={() =>
                mutate.mutate({
                  path: "/api/v1/coman-parity/products",
                  body: product,
                })
              }
            >
              Save product
            </button>
          </div>
        </details>
        <details
          className="streamlit-expander"
          open={Boolean(value.products.length) && !value.lots.length}
        >
          <summary>Receive a lot</summary>
          <div className="streamlit-expander-body">
            {!value.products.length ? (
              <Info>Add a product before receiving inventory.</Info>
            ) : (
              <>
                <Select
                  label="Product"
                  value={lot.product_id}
                  values={value.products.map((row) => row.id)}
                  labels={Object.fromEntries(
                    value.products.map((row) => [
                      row.id,
                      `${row.sku} — ${row.name}`,
                    ]),
                  )}
                  set={(id) =>
                    setLot({
                      ...lot,
                      product_id: id,
                      unit: productById[id]?.base_unit ?? "g",
                    })
                  }
                />
                <Text
                  label="Lot / batch code*"
                  value={lot.lot_code}
                  set={(v) => setLot({ ...lot, lot_code: v })}
                />
                <Text
                  label="Compliance package ID"
                  value={lot.compliance_package_id}
                  set={(v) => setLot({ ...lot, compliance_package_id: v })}
                />
                <Text
                  label="Storage location"
                  value={lot.location_code}
                  set={(v) => setLot({ ...lot, location_code: v })}
                />
                <Num
                  label="Quantity received"
                  value={lot.opening_quantity}
                  set={(v) => setLot({ ...lot, opening_quantity: v })}
                  step={1}
                />
                <button
                  className="primary"
                  onClick={() =>
                    mutate.mutate({
                      path: "/api/v1/coman-parity/lots",
                      body: lot,
                    })
                  }
                >
                  Receive lot
                </button>
              </>
            )}
          </div>
        </details>
      </div>
      <h4>On-hand inventory</h4>
      {value.lots.length ? (
        <DataTable
          rows={value.lots.map((row) => ({
            Lot: row.lot_code,
            Product: productById[row.product_id]?.name ?? "Unknown",
            SKU: productById[row.product_id]?.sku ?? "",
            Location: row.location_code,
            "On Hand": row.on_hand,
            Reserved: reserved[row.id] ?? 0,
            Available: row.on_hand - (reserved[row.id] ?? 0),
            Unit: productById[row.product_id]?.base_unit ?? "",
            Status: title(row.status),
            "Package ID": row.compliance_package_id,
          }))}
        />
      ) : (
        <Info>
          No inventory lots yet. Add a product and receive the first lot above.
        </Info>
      )}
      <div className="two-col">
        <div>
          <h5>Post inventory movement</h5>
          {!value.lots.length ? (
            <p>Receive a lot to post movements.</p>
          ) : (
            <>
              <Select
                label="Lot"
                value={movement.lot_id}
                values={value.lots.map((row) => row.id)}
                labels={Object.fromEntries(
                  value.lots.map((row) => [row.id, row.lot_code]),
                )}
                set={(id) =>
                  setMovement({
                    ...movement,
                    lot_id: id,
                    unit:
                      productById[
                        value.lots.find((row) => row.id === id)?.product_id ??
                          ""
                      ]?.base_unit ?? "g",
                  })
                }
              />
              <Select
                label="Movement"
                value={movement.transaction_type}
                values={[
                  "receipt",
                  "adjustment_in",
                  "adjustment_out",
                  "production_consume",
                  "production_output",
                  "waste",
                  "shipment",
                  "return",
                ]}
                labels={{
                  receipt: "Receipt",
                  adjustment_in: "Adjustment In",
                  adjustment_out: "Adjustment Out",
                  production_consume: "Production Consume",
                  production_output: "Production Output",
                  waste: "Waste",
                  shipment: "Shipment",
                  return: "Return",
                }}
                set={(v) => setMovement({ ...movement, transaction_type: v })}
              />
              <Num
                label="Quantity"
                value={movement.quantity}
                set={(v) => setMovement({ ...movement, quantity: v })}
                min={0.01}
                step={1}
              />
              <Text
                label="Reason / reference*"
                value={movement.reason}
                set={(v) => setMovement({ ...movement, reason: v })}
              />
              <button
                className="primary"
                onClick={() =>
                  mutate.mutate({
                    path: "/api/v1/coman-parity/movements",
                    body: movement,
                  })
                }
              >
                Post movement
              </button>
            </>
          )}
        </div>
        <div>
          <h5>Reserve material for a job</h5>
          {!openOrders.length || !value.lots.length ? (
            <p>An open production order and an available lot are required.</p>
          ) : (
            <>
              <Select
                label="Production order"
                value={reservation.production_order_id}
                values={openOrders.map((row) => row.id)}
                labels={Object.fromEntries(
                  openOrders.map((row) => [
                    row.id,
                    `${row.order_number} — ${row.product_name}`,
                  ]),
                )}
                set={(v) =>
                  setReservation({ ...reservation, production_order_id: v })
                }
              />
              <Select
                label="Material lot"
                value={reservation.lot_id}
                values={value.lots.map((row) => row.id)}
                labels={Object.fromEntries(
                  value.lots.map((row) => [row.id, row.lot_code]),
                )}
                set={(id) =>
                  setReservation({
                    ...reservation,
                    lot_id: id,
                    unit:
                      productById[
                        value.lots.find((row) => row.id === id)?.product_id ??
                          ""
                      ]?.base_unit ?? "g",
                  })
                }
              />
              <Num
                label="Quantity to reserve"
                value={reservation.quantity}
                set={(v) => setReservation({ ...reservation, quantity: v })}
                min={0.01}
                step={1}
              />
              <button
                className="primary"
                onClick={() =>
                  mutate.mutate({
                    path: "/api/v1/coman-parity/reservations",
                    body: reservation,
                  })
                }
              >
                Reserve material
              </button>
            </>
          )}
        </div>
      </div>
      <h4>Bill of materials</h4>
      {!value.products.some((row) =>
        ["wip", "finished_good"].includes(row.item_type),
      ) ||
      !value.products.some((row) =>
        ["cannabis", "packaging", "wip"].includes(row.item_type),
      ) ? (
        <Info>
          Add at least one finished-good or WIP product and one cannabis,
          packaging, or WIP component to build a BOM.
        </Info>
      ) : (
        <>
          <div className="three-col">
            <Select
              label="Finished product"
              value={bom.output_product_id}
              values={value.products
                .filter((row) =>
                  ["wip", "finished_good"].includes(row.item_type),
                )
                .map((row) => row.id)}
              labels={Object.fromEntries(
                value.products.map((row) => [
                  row.id,
                  `${row.sku} — ${row.name}`,
                ]),
              )}
              set={(v) => setBom({ ...bom, output_product_id: v })}
            />
            <Num
              label="Finished quantity"
              value={bom.output_quantity}
              set={(v) => setBom({ ...bom, output_quantity: v })}
              min={0.01}
              step={1}
            />
            <Num
              label="Expected process loss %"
              value={bom.expected_loss_pct}
              set={(v) => setBom({ ...bom, expected_loss_pct: v })}
              step={0.5}
            />
          </div>
          <ComponentEditor
            products={value.products.filter((row) =>
              ["cannabis", "packaging", "wip"].includes(row.item_type),
            )}
            rows={bom.components}
            setRows={(rows) => setBom({ ...bom, components: rows })}
          />
          <button
            className="primary"
            disabled={!bom.components.length}
            onClick={() =>
              mutate.mutate({ path: "/api/v1/coman-parity/boms", body: bom })
            }
          >
            Create BOM version
          </button>
        </>
      )}
      <details className="streamlit-expander">
        <summary>Inventory ledger</summary>
        <div className="streamlit-expander-body">
          {!value.transactions.length ? (
            <p>No ledger entries yet.</p>
          ) : (
            <DataTable
              rows={value.transactions.map((row) => ({
                Time: row.occurred_at,
                Lot:
                  value.lots.find((lot) => lot.id === row.lot_id)?.lot_code ??
                  row.lot_id,
                Movement: title(row.transaction_type),
                Quantity: row.quantity_delta,
                Unit: row.unit,
                Reason: row.reason,
                Reference: row.reference,
                Actor: row.actor,
              }))}
            />
          )}
        </div>
      </details>
      <MutationState
        value={mutate}
        success={
          {
            "/api/v1/coman-parity/products": "Product saved.",
            "/api/v1/coman-parity/lots":
              "Lot received and opening ledger entry posted.",
            "/api/v1/coman-parity/movements": "Inventory movement posted.",
            "/api/v1/coman-parity/reservations":
              "Material reserved for the job.",
            "/api/v1/coman-parity/boms": "BOM version created.",
          }[mutate.variables?.path ?? ""] ?? ""
        }
      />
    </section>
  );
}

function Customers({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: "",
    license_or_registration: "",
    contact_name: "",
    contact_email: "",
  });
  const save = useMutation({
    mutationFn: () => apiPost("/api/v1/coman-parity/customers", form),
    onSuccess: () => {
      setForm({
        name: "",
        license_or_registration: "",
        contact_name: "",
        contact_email: "",
      });
      onSaved();
    },
  });
  return (
    <section className="coman-workspace">
      <h4>Co-Man customers</h4>
      <p>
        Customers are only required when your facility packages product for
        another company.
      </p>
      <div className="two-col">
        <Text
          label="Company name*"
          value={form.name}
          set={(v) => setForm({ ...form, name: v })}
        />
        <Text
          label="License / registration"
          value={form.license_or_registration}
          set={(v) => setForm({ ...form, license_or_registration: v })}
        />
        <Text
          label="Contact name"
          value={form.contact_name}
          set={(v) => setForm({ ...form, contact_name: v })}
        />
        <Text
          label="Contact email"
          value={form.contact_email}
          set={(v) => setForm({ ...form, contact_email: v })}
        />
      </div>
      <button className="primary" onClick={() => save.mutate()}>
        Add customer
      </button>
      <DataTable
        rows={value.customers.map((row) => ({
          Company: row.name,
          License: row.license_or_registration,
          Contact: row.contact_name,
          Email: row.contact_email,
        }))}
      />
      <MutationState value={save} success="Customer was added." />
    </section>
  );
}

function Performance({
  value,
  onSaved,
}: {
  value: Workspace;
  onSaved: () => void;
}) {
  const [orderId, setOrderId] = useState(value.orders[0]?.id ?? "");
  const order = value.orders.find((row) => row.id === orderId);
  const [form, setForm] = useState({
    actual_units: order?.requested_units ?? 0,
    scrap_units: 0,
    rework_units: 0,
    actual_machine_hours: 0,
    actual_labor_hours: 0,
    notes: "",
  });
  const save = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/coman-parity/orders/${orderId}/actuals`, form),
    onSuccess: () => {
      setForm({
        actual_units: order?.requested_units ?? 0,
        scrap_units: 0,
        rework_units: 0,
        actual_machine_hours: 0,
        actual_labor_hours: 0,
        notes: "",
      });
      onSaved();
    },
  });
  const rows = value.actuals.map((row) => {
    const source = value.orders.find(
      (order) => order.id === row.production_order_id,
    );
    return {
      Order: source?.order_number ?? row.production_order_id,
      Product: source?.product_name ?? "Unknown",
      "Planned Units": source?.requested_units ?? 0,
      "Actual Units": row.actual_units,
      "Attainment %": source?.requested_units
        ? round((row.actual_units / source.requested_units) * 100)
        : 0,
      Scrap: row.scrap_units,
      Rework: row.rework_units,
      "Machine Hours": row.actual_machine_hours,
      "Labor Hours": row.actual_labor_hours,
      Completed: row.completed_at,
    };
  });
  const exportPdf = async () =>
    downloadBlob(
      await apiDownload("/api/v1/coman-parity/report.pdf"),
      `production_ops_coman_report_${today()}.pdf`,
    );
  return (
    <section className="coman-workspace">
      <h4>Record completed-job actuals</h4>
      {!value.orders.length ? (
        <Info>Create a production order before recording performance.</Info>
      ) : (
        <>
          <Select
            label="Production order"
            value={orderId}
            values={value.orders.map((row) => row.id)}
            labels={Object.fromEntries(
              value.orders.map((row) => [
                row.id,
                `${row.order_number} — ${row.product_name}`,
              ]),
            )}
            set={(id) => {
              setOrderId(id);
              const next = value.orders.find((row) => row.id === id);
              setForm({ ...form, actual_units: next?.requested_units ?? 0 });
            }}
          />
          <div className="three-col">
            <Num
              label="Good finished units"
              value={form.actual_units}
              set={(v) => setForm({ ...form, actual_units: v })}
              step={100}
            />
            <Num
              label="Scrap units"
              value={form.scrap_units}
              set={(v) => setForm({ ...form, scrap_units: v })}
              step={1}
            />
            <Num
              label="Rework units"
              value={form.rework_units}
              set={(v) => setForm({ ...form, rework_units: v })}
              step={1}
            />
            <Num
              label="Actual machine hours"
              value={form.actual_machine_hours}
              set={(v) => setForm({ ...form, actual_machine_hours: v })}
              step={0.25}
            />
            <Num
              label="Actual labor-hours"
              value={form.actual_labor_hours}
              set={(v) => setForm({ ...form, actual_labor_hours: v })}
              step={0.25}
            />
          </div>
          <Area
            label="Completion notes"
            value={form.notes}
            set={(v) => setForm({ ...form, notes: v })}
          />
          <button className="primary" onClick={() => save.mutate()}>
            Complete job and save actuals
          </button>
        </>
      )}{" "}
      {rows.length ? (
        <>
          <DataTable rows={rows} />
          <div className="metrics four">
            <Metric l="Completed Jobs" v={String(rows.length)} />
            <Metric
              l="Average Attainment"
              v={`${(sumRows(rows, "Attainment %") / rows.length).toFixed(1)}%`}
            />
            <Metric
              l="Total Scrap"
              v={sumRows(rows, "Scrap").toLocaleString()}
            />
            <Metric
              l="Actual Labor-Hours"
              v={sumRows(rows, "Labor Hours").toFixed(1)}
            />
          </div>
          <h4>Performance visuals</h4>
          <p>
            Output, attainment, and hours use the same orange, green, and blue
            accents as the rest of the app.
          </p>
          <div className="two-col">
            <GroupedBars
              title="Planned vs. actual output"
              rows={rows.map((row) => ({
                label: `${String(row.Order)} — ${String(row.Product)}`,
                first: Number(row["Planned Units"]),
                second: Number(row["Actual Units"]),
              }))}
              firstLabel="Planned Units"
              secondLabel="Actual Units"
            />
            <Bars
              title="Job attainment"
              rows={rows.map((row) => [
                `${String(row.Order)} — ${String(row.Product)}`,
                Number(row["Attainment %"]),
              ])}
            />
          </div>
          <GroupedBars
            title="Machine and labor hours"
            rows={rows.map((row) => ({
              label: `${String(row.Order)} — ${String(row.Product)}`,
              first: Number(row["Machine Hours"]),
              second: Number(row["Labor Hours"]),
            }))}
            firstLabel="Machine Hours"
            secondLabel="Labor Hours"
          />
        </>
      ) : null}
      <h4>Production Ops executive report</h4>
      <p>
        Exports the current Co-Man queue, completed-job performance, machines,
        crew capacity, and customers using the Production Ops report design.
      </p>
      <button className="primary" onClick={exportPdf}>
        Export Production Ops Report
      </button>
      <MutationState
        value={save}
        success="Actual performance saved and order marked complete."
      />
    </section>
  );
}

function ProductionControlDrawer({
  products,
  close,
}: {
  products: Product[];
  close: () => void;
}) {
  const client = useQueryClient();
  const queue = useQuery({
    queryKey: ["production-control-orders"],
    queryFn: ({ signal }) =>
      apiGet<ProductionQueueRow[]>("/api/v1/production/orders", signal),
  });
  const [orderId, setOrderId] = useState("");
  const detail = useQuery({
    queryKey: ["production-control-order", orderId],
    enabled: Boolean(orderId),
    queryFn: ({ signal }) =>
      apiGet<ProductionDetail>(`/api/v1/production/orders/${orderId}`, signal),
  });
  const [event, setEvent] = useState({
    event_type: "started",
    quantity: 0,
    labor_hours: 0,
    machine_hours: 0,
    notes: "",
  });
  const eligibleProducts = products.filter((row) =>
    ["cannabis", "wip", "finished_good"].includes(row.item_type),
  );
  const [output, setOutput] = useState({
    product_id: eligibleProducts[0]?.id ?? "",
    planned_quantity: 0,
  });
  const [outputId, setOutputId] = useState("");
  const selectedOutput = detail.data?.outputs.find(
    (row) => row.id === outputId,
  );
  const [actual, setActual] = useState(0);
  const [lotCode, setLotCode] = useState("");
  const [qa, setQa] = useState({ event_type: "sample", result: "pending" });
  const [cost, setCost] = useState({
    category: "material",
    amount_usd: 0,
    notes: "",
  });
  useEffect(() => {
    if (!orderId && queue.data?.[0]) setOrderId(queue.data[0].order_id);
  }, [orderId, queue.data]);
  useEffect(() => {
    if (!output.product_id && eligibleProducts[0]) {
      setOutput((current) => ({
        ...current,
        product_id: eligibleProducts[0].id,
      }));
    }
  }, [eligibleProducts, output.product_id]);
  useEffect(() => {
    const next = detail.data?.outputs[0];
    if (!outputId && next) {
      setOutputId(next.id);
      setActual(next.actual_quantity);
      setLotCode(`${detail.data?.order.order_number}-${next.position}`);
    }
  }, [detail.data, outputId]);
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["production-control-orders"] });
    client.invalidateQueries({
      queryKey: ["production-control-order", orderId],
    });
  };
  const action = useMutation({
    mutationFn: ({ path, body = {} }: { path: string; body?: object }) =>
      apiPost(path, body),
    onSuccess: refresh,
  });
  const rows = queue.data ?? [];
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={close}>
      <section
        className="modal wide production-control-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Production Control"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-heading">
          <div>
            <h2>Production Control</h2>
            <p>
              Plan, reserve, execute, QA and cost production from one queue.
            </p>
          </div>
          <button className="secondary" onClick={close}>
            Close
          </button>
        </div>
        {queue.isLoading ? (
          <div className="state">Loading production queue…</div>
        ) : null}
        {queue.isError ? (
          <div className="form-error">{queue.error.message}</div>
        ) : null}
        {!queue.isLoading && !rows.length ? (
          <Info>No production orders yet.</Info>
        ) : null}
        {rows.length ? (
          <>
            <div className="metrics four">
              <Metric
                l="Open"
                v={String(
                  rows.filter(
                    (row) => !["Complete", "Cancelled"].includes(row.Status),
                  ).length,
                )}
              />
              <Metric
                l="QA Holds"
                v={String(rows.filter((row) => row.QA === "HOLD").length)}
              />
              <Metric
                l="Planned Units"
                v={sumRows(rows, "Planned").toLocaleString()}
              />
              <Metric l="Tracked COGS" v={money(sumRows(rows, "COGS"))} />
            </div>
            <DataTable
              rows={rows.map(({ order_id: _orderId, ...row }) => row)}
            />
            <Select
              label="Open Production 360"
              value={orderId}
              values={rows.map((row) => row.order_id)}
              labels={Object.fromEntries(
                rows.map((row) => [
                  row.order_id,
                  `${row.Order} · ${row.Product} · ${row.Attention}`,
                ]),
              )}
              set={(id) => {
                setOrderId(id);
                setOutputId("");
              }}
            />
          </>
        ) : null}
        {detail.data ? (
          <>
            <h3>
              {detail.data.order.order_number} ·{" "}
              {detail.data.order.product_name}
            </h3>
            <div className="metrics four">
              <Metric
                l="Attainment"
                v={`${detail.data.attainment_pct.toFixed(1)}%`}
              />
              <Metric
                l="Reserved Lots"
                v={String(detail.data.reservations.length)}
              />
              <Metric l="Outputs" v={String(detail.data.outputs.length)} />
              <Metric l="COGS" v={money(detail.data.cogs.total ?? 0)} />
            </div>
            <details className="streamlit-expander">
              <summary>Reserve BOM materials</summary>
              <div className="streamlit-expander-body">
                {detail.data.requirements.length ? (
                  <DataTable rows={detail.data.requirements} />
                ) : (
                  <p>No active BOM requirements found.</p>
                )}
                <button
                  className="primary"
                  onClick={() =>
                    action.mutate({
                      path: `/api/v1/production/orders/${orderId}/reserve`,
                    })
                  }
                >
                  Reserve available lots
                </button>
              </div>
            </details>
            <details className="streamlit-expander">
              <summary>Record stage / actuals</summary>
              <div className="streamlit-expander-body">
                <Select
                  label="Event"
                  value={event.event_type}
                  values={[
                    "started",
                    "measurement",
                    "rework",
                    "waste",
                    "hold",
                    "release",
                    "completed",
                    "note",
                  ]}
                  set={(value) => setEvent({ ...event, event_type: value })}
                />
                <div className="three-col">
                  <Num
                    label="Qty"
                    value={event.quantity}
                    set={(value) => setEvent({ ...event, quantity: value })}
                    step={1}
                  />
                  <Num
                    label="Labor h"
                    value={event.labor_hours}
                    set={(value) => setEvent({ ...event, labor_hours: value })}
                    step={0.25}
                  />
                  <Num
                    label="Machine h"
                    value={event.machine_hours}
                    set={(value) =>
                      setEvent({ ...event, machine_hours: value })
                    }
                    step={0.25}
                  />
                </div>
                <Text
                  label="Note"
                  value={event.notes}
                  set={(value) => setEvent({ ...event, notes: value })}
                />
                <button
                  className="primary"
                  onClick={() =>
                    action.mutate({
                      path: `/api/v1/production/orders/${orderId}/events`,
                      body: {
                        ...event,
                        quantity: event.quantity || null,
                        labor_hours: event.labor_hours || null,
                        machine_hours: event.machine_hours || null,
                      },
                    })
                  }
                >
                  Record event
                </button>
              </div>
            </details>
            <details className="streamlit-expander">
              <summary>Outputs + QA</summary>
              <div className="streamlit-expander-body">
                {eligibleProducts.length ? (
                  <>
                    <Select
                      label="Output product"
                      value={output.product_id}
                      values={eligibleProducts.map((row) => row.id)}
                      labels={Object.fromEntries(
                        eligibleProducts.map((row) => [
                          row.id,
                          `${row.name} · ${row.sku}`,
                        ]),
                      )}
                      set={(value) =>
                        setOutput({ ...output, product_id: value })
                      }
                    />
                    <Num
                      label="Planned output"
                      value={output.planned_quantity}
                      set={(value) =>
                        setOutput({ ...output, planned_quantity: value })
                      }
                      step={1}
                    />
                    <button
                      className="secondary"
                      onClick={() => {
                        const product = eligibleProducts.find(
                          (row) => row.id === output.product_id,
                        );
                        action.mutate({
                          path: `/api/v1/production/orders/${orderId}/outputs`,
                          body: {
                            ...output,
                            label: product?.name ?? "",
                            unit: product?.base_unit ?? "unit",
                          },
                        });
                      }}
                    >
                      Add output
                    </button>
                  </>
                ) : null}
                {detail.data.outputs.length ? (
                  <>
                    <DataTable
                      rows={detail.data.outputs.map((row) => ({
                        Output: row.label,
                        Planned: row.planned_quantity,
                        Actual: row.actual_quantity,
                        Status: row.status,
                      }))}
                    />
                    <Select
                      label="Output"
                      value={outputId}
                      values={detail.data.outputs.map((row) => row.id)}
                      labels={Object.fromEntries(
                        detail.data.outputs.map((row) => [
                          row.id,
                          `#${row.position} ${row.label}`,
                        ]),
                      )}
                      set={(id) => {
                        const next = detail.data?.outputs.find(
                          (row) => row.id === id,
                        );
                        setOutputId(id);
                        setActual(next?.actual_quantity ?? 0);
                        setLotCode(
                          `${detail.data?.order.order_number}-${next?.position ?? 1}`,
                        );
                      }}
                    />
                    <Num label="Actual qty" value={actual} set={setActual} />
                    <Text
                      label="Output lot code"
                      value={lotCode}
                      set={setLotCode}
                    />
                    <button
                      className="secondary"
                      onClick={() =>
                        action.mutate({
                          path: `/api/v1/production/outputs/${outputId}/actual`,
                          body: { actual_quantity: actual, lot_code: lotCode },
                        })
                      }
                    >
                      Post actual to quarantine
                    </button>
                    <Select
                      label="QA action"
                      value={qa.event_type}
                      values={[
                        "sample",
                        "pass",
                        "fail",
                        "hold",
                        "retest",
                        "remediation",
                        "release",
                      ]}
                      set={(value) => setQa({ ...qa, event_type: value })}
                    />
                    <Select
                      label="Result"
                      value={qa.result}
                      values={["pending", "passed", "failed", "not_applicable"]}
                      set={(value) => setQa({ ...qa, result: value })}
                    />
                    <button
                      className="primary"
                      onClick={() =>
                        action.mutate({
                          path: `/api/v1/production/orders/${orderId}/qa`,
                          body: {
                            ...qa,
                            output_id: selectedOutput?.id ?? null,
                          },
                        })
                      }
                    >
                      Record QA
                    </button>
                  </>
                ) : null}
              </div>
            </details>
            <details className="streamlit-expander">
              <summary>Add COGS</summary>
              <div className="streamlit-expander-body">
                <Select
                  label="Category"
                  value={cost.category}
                  values={[
                    "material",
                    "labor",
                    "packaging",
                    "machine",
                    "overhead",
                    "waste",
                    "other",
                  ]}
                  set={(value) => setCost({ ...cost, category: value })}
                />
                <Num
                  label="Amount USD"
                  value={cost.amount_usd}
                  set={(value) => setCost({ ...cost, amount_usd: value })}
                  step={1}
                />
                <Text
                  label="Cost note"
                  value={cost.notes}
                  set={(value) => setCost({ ...cost, notes: value })}
                />
                <button
                  className="primary"
                  onClick={() =>
                    action.mutate({
                      path: `/api/v1/production/orders/${orderId}/costs`,
                      body: cost,
                    })
                  }
                >
                  Post cost
                </button>
              </div>
            </details>
            <MutationState value={action} success="" />
          </>
        ) : null}
      </section>
    </div>
  );
}

function OrderForm({
  order,
  setOrder,
  customers,
  submit,
}: {
  order: ReturnType<typeof blankOrder>;
  setOrder: (value: ReturnType<typeof blankOrder>) => void;
  customers: Customer[];
  submit: () => void;
}) {
  return (
    <form
      className="form-grid three"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Text
        label="Order number*"
        value={String(order.order_number)}
        set={(v) => setOrder({ ...order, order_number: v })}
        placeholder="COM-000001"
      />
      <Select
        label="Work type*"
        value={String(order.work_type)}
        values={["Internal", "External"]}
        set={(v) => setOrder({ ...order, work_type: v })}
      />
      <Num
        label="Requested units*"
        value={Number(order.requested_units)}
        set={(v) => setOrder({ ...order, requested_units: v })}
        min={1}
        step={100}
      />
      <Text
        label="Product name*"
        value={String(order.product_name)}
        set={(v) => setOrder({ ...order, product_name: v })}
        placeholder="House Flower 3.5g"
      />
      <Select
        label="Product format*"
        value={String(order.product_format)}
        values={FORMATS}
        set={(v) => setOrder({ ...order, product_format: v })}
      />
      <Text
        label="SKU"
        value={String(order.sku)}
        set={(v) => setOrder({ ...order, sku: v })}
      />
      <Select
        label="Customer* (external work)"
        disabled={order.work_type === "Internal"}
        value={String(order.customer_id)}
        values={["", ...customers.map((row) => row.id)]}
        labels={{
          "": "Select customer",
          ...Object.fromEntries(customers.map((row) => [row.id, row.name])),
        }}
        set={(v) => setOrder({ ...order, customer_id: v })}
      />
      <DateField
        label="Due date"
        value={String(order.due_date)}
        set={(v) => setOrder({ ...order, due_date: v })}
      />
      <Select
        label="Priority"
        value={String(order.priority)}
        values={["Normal", "High", "Rush", "Low"]}
        set={(v) => setOrder({ ...order, priority: v })}
      />
      <Text
        label="Source lot / METRC package"
        value={String(order.source_lot_reference)}
        set={(v) => setOrder({ ...order, source_lot_reference: v })}
      />
      <Select
        label="Bulk material owner"
        value={String(order.material_owner)}
        values={["Internal", "Customer"]}
        set={(v) => setOrder({ ...order, material_owner: v })}
      />
      <Select
        label="Packaging owner"
        value={String(order.packaging_owner)}
        values={["Internal", "Customer"]}
        set={(v) => setOrder({ ...order, packaging_owner: v })}
      />
      <Area
        label="Production notes"
        value={String(order.notes)}
        set={(v) => setOrder({ ...order, notes: v })}
        placeholder="Breakdown, weighing, tubing, stickering, casing, or special instructions"
      />
      <button className="primary" type="submit">
        Create production order
      </button>
    </form>
  );
}
function OptimizerTable({
  rows,
  setRows,
}: {
  rows: OptimizerRow[];
  setRows: (rows: OptimizerRow[]) => void;
}) {
  const cols = Object.keys(OPTIMIZER_LABELS) as (keyof OptimizerRow)[];
  const update = (
    i: number,
    key: keyof OptimizerRow,
    value: string | number | boolean,
  ) =>
    setRows(
      rows.map((row, index) => (index === i ? { ...row, [key]: value } : row)),
    );
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {cols.map((key) => (
                <th key={key}>{OPTIMIZER_LABELS[key]}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map((key) => (
                  <td key={key}>
                    {key === "eligible" ? (
                      <input
                        type="checkbox"
                        checked={row[key] as boolean}
                        onChange={(e) => update(i, key, e.target.checked)}
                      />
                    ) : key === "format" ? (
                      <select
                        value={String(row[key])}
                        onChange={(e) => update(i, key, e.target.value)}
                      >
                        {FORMATS.map((value) => (
                          <option key={value}>{value}</option>
                        ))}
                      </select>
                    ) : key === "product" ? (
                      <input
                        value={String(row[key])}
                        onChange={(e) => update(i, key, e.target.value)}
                      />
                    ) : (
                      <input
                        type="number"
                        step="any"
                        min={0}
                        max={key === "max_allocation_pct" ? 100 : undefined}
                        value={Number(row[key])}
                        onChange={(e) => update(i, key, Number(e.target.value))}
                      />
                    )}
                  </td>
                ))}
                <td>
                  <button
                    type="button"
                    className="table-row-action"
                    onClick={() =>
                      setRows(rows.filter((_, index) => index !== i))
                    }
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        className="secondary"
        onClick={() =>
          setRows([
            ...rows,
            optimizerRow("New product", "Other", 1, 0, 0, 0, 0, 0, 1, 1),
          ])
        }
      >
        Add row
      </button>
    </>
  );
}
function ComponentEditor({
  products,
  rows,
  setRows,
}: {
  products: Product[];
  rows: { input_product_id: string; quantity: number; unit: string }[];
  setRows: (
    rows: { input_product_id: string; quantity: number; unit: string }[],
  ) => void;
}) {
  return (
    <div>
      <label>
        Components
        <select
          multiple
          value={rows.map((row) => row.input_product_id)}
          onChange={(e) => {
            const ids = [...e.target.selectedOptions].map(
              (option) => option.value,
            );
            setRows(
              ids.map(
                (id) =>
                  rows.find((row) => row.input_product_id === id) ?? {
                    input_product_id: id,
                    quantity: 1,
                    unit:
                      products.find((product) => product.id === id)
                        ?.base_unit ?? "unit",
                  },
              ),
            );
          }}
        >
          {products.map((row) => (
            <option value={row.id} key={row.id}>
              {row.sku} — {row.name}
            </option>
          ))}
        </select>
      </label>
      <div className="three-col">
        {rows.map((row, index) => (
          <Num
            key={row.input_product_id}
            label={`${products.find((product) => product.id === row.input_product_id)?.sku} quantity (${row.unit})`}
            value={row.quantity}
            set={(v) =>
              setRows(
                rows.map((item, i) =>
                  i === index ? { ...item, quantity: v } : item,
                ),
              )
            }
          />
        ))}
      </div>
    </div>
  );
}
function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = rows.length ? Object.keys(rows[0]) : [];
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {cols.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((col) => (
                <td key={col}>
                  {typeof row[col] === "string" &&
                  String(row[col]).startsWith("http") ? (
                    <a href={String(row[col])} target="_blank" rel="noreferrer">
                      Open
                    </a>
                  ) : (
                    String(row[col] ?? "")
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="compact-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function Text({
  label,
  value,
  set,
  placeholder = "",
}: {
  label: string;
  value: string;
  set: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <Field label={label}>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => set(e.target.value)}
      />
    </Field>
  );
}
function Area({
  label,
  value,
  set,
  placeholder = "",
}: {
  label: string;
  value: string;
  set: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <Field label={label}>
      <textarea
        value={value}
        placeholder={placeholder}
        onChange={(e) => set(e.target.value)}
      />
    </Field>
  );
}
function Num({
  label,
  value,
  set,
  min = 0,
  max,
  step = "any",
}: {
  label: string;
  value: number;
  set: (v: number) => void;
  min?: number;
  max?: number;
  step?: number | "any";
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
      />
    </Field>
  );
}
function DateField({
  label,
  value,
  set,
}: {
  label: string;
  value: string;
  set: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <input type="date" value={value} onChange={(e) => set(e.target.value)} />
    </Field>
  );
}
function Select({
  label,
  value,
  values,
  labels = {},
  set,
  disabled = false,
}: {
  label: string;
  value: string;
  values: string[];
  labels?: Record<string, string>;
  set: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => set(e.target.value)}
      >
        {values.map((v) => (
          <option value={v} key={v}>
            {labels[v] ?? v}
          </option>
        ))}
      </select>
    </Field>
  );
}
function Metric({ l, v }: { l: string; v: string }) {
  return (
    <article className="metric">
      <span>{l}</span>
      <strong>{v}</strong>
    </article>
  );
}
function Info({ children }: { children: ReactNode }) {
  return <div className="info-banner">{children}</div>;
}
function Warn({ children }: { children: ReactNode }) {
  return <div className="warning-banner">{children}</div>;
}
function MutationState({
  value,
  success = "Saved.",
}: {
  value: { isError: boolean; error: Error | null; isSuccess: boolean };
  success?: string;
}) {
  return (
    <>
      {value.isError ? (
        <div className="form-error">{value.error?.message}</div>
      ) : null}
      {value.isSuccess && success ? (
        <div className="success-banner">{success}</div>
      ) : null}
    </>
  );
}
function Bars({
  title: chartTitle,
  rows,
}: {
  title: string;
  rows: [string, number][];
}) {
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <div className="chart-card">
      <h4>{chartTitle}</h4>
      <div className="simple-bars">
        {rows.map(([label, value]) => (
          <div className="simple-bar-row" key={label}>
            <span>{label}</span>
            <div>
              <i style={{ width: `${(Math.max(0, value) / max) * 100}%` }} />
            </div>
            <strong>{round(value)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
function GroupedBars({
  title: chartTitle,
  rows,
  firstLabel,
  secondLabel,
}: {
  title: string;
  rows: { label: string; first: number; second: number }[];
  firstLabel: string;
  secondLabel: string;
}) {
  const max = Math.max(1, ...rows.flatMap((row) => [row.first, row.second]));
  return (
    <div className="chart-card grouped-chart">
      <h4>{chartTitle}</h4>
      <div className="chart-legend">
        <span>{firstLabel}</span>
        <span>{secondLabel}</span>
      </div>
      {rows.map((row) => (
        <div className="grouped-bar-row" key={row.label}>
          <span>{row.label}</span>
          <div>
            <i style={{ width: `${(Math.max(0, row.first) / max) * 100}%` }} />
          </div>
          <div>
            <i style={{ width: `${(Math.max(0, row.second) / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
function orderFrame(row: Order, customers: Customer[]) {
  return {
    Order: row.order_number,
    Type: title(row.work_type),
    Customer:
      customers.find((customer) => customer.id === row.customer_id)?.name ??
      "Internal",
    Product: row.product_name,
    Format: row.product_format,
    Units: row.requested_units,
    Due: row.due_at?.slice(0, 10) ?? "Not set",
    Priority: title(row.priority),
    Status: title(row.status),
    "Source Lot": row.source_lot_reference,
  };
}
function title(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function unique(values: string[]) {
  return [...new Set(values)].sort();
}
function money(value: number) {
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
function round(value: number) {
  return Math.round(value * 10) / 10;
}
function round2(value: number) {
  return Math.round(value * 100) / 100;
}
function sum(rows: Recommendation[], key: keyof Recommendation) {
  return rows.reduce((total, row) => total + Number(row[key]), 0);
}
function sumRows(rows: Record<string, unknown>[], key: string) {
  return rows.reduce((total, row) => total + Number(row[key] ?? 0), 0);
}
