import {
  h,
  title,
  grid,
  stack,
  actions,
  metrics,
  section,
  table,
  field,
  form,
  api,
  button,
  editor,
  modal,
  kv,
  badge,
  human,
  stamp,
  money,
  asMinor,
  orderLines,
  totals,
  empty,
  toast,
} from "./ui.js";

const req = (p, opt) => api("restaurant/" + p, opt);
const kitchenNext = {
  received: "accepted",
  accepted: "preparing",
  preparing: "ready",
  ready: "served",
};
const billNext = {
  pending: "accepted",
  accepted: "prepared",
  prepared: "awaiting_payment",
  awaiting_payment: "paid",
  paid: "completed",
};
const billLabels = {
  accepted: "Accept request",
  prepared: "Prepare bill",
  awaiting_payment: "Await payment",
  paid: "Record payment",
  completed: "Complete checkout",
};
const cursors = { orders: [null], checkout: [null] };
function pageQuery(page, status) {
  const params = new URLSearchParams({ limit: "25" });
  const before = cursors[page].at(-1);
  if (before) params.set("before", before);
  if (status && status !== "all") params.set("status", status);
  return "?" + params.toString();
}
function pageControls(page, list, refresh) {
  return actions(
    cursors[page].length > 1 &&
      button(
        "Newer records",
        () => {
          cursors[page].pop();
          return refresh();
        },
        "btn light small",
      ),
    list.length === 25 &&
      button(
        "Older records",
        () => {
          cursors[page].push(list.at(-1).id);
          return refresh();
        },
        "btn light small",
      ),
  );
}
let billFilter = "all",
  kitchenFilter = "all",
  range = { start: "", end: "" };
function values(title, data, fmt = String) {
  return section(
    title,
    table(
      ["Name", "Value"],
      Object.entries(data).map(([k, v]) => [human(k), fmt(v)]),
      "No activity in this period.",
    ),
  );
}
export async function operationsPage(page, { user, refresh }) {
  const cur = user.restaurant.currency,
    zone = user.restaurant.timezone,
    rights = user.permissions;
  const change = async (path, data, method = "PUT") => {
    await req(path, { method, data });
    await refresh();
    toast("Updated.");
  };
  if (page === "kitchen") {
    const list = await req("kitchen");
    const choose = field("Preparation stage", "stage", {
      choices: ["all", "received", "accepted", "preparing", "ready", "served"],
      value: kitchenFilter,
    });
    choose.onchange = () => {
      kitchenFilter = choose.querySelector("select").value;
      refresh();
    };
    const tickets = list.filter(
      (o) => kitchenFilter === "all" || o.status === kitchenFilter,
    );
    return [
      title("Kitchen display", "Kitchen accounts can see and update kitchen tickets only."),
      choose,
      tickets.length
        ? h(
            "div",
            { class: "tickets" },
            tickets.map((o) =>
              h(
                "article",
                { class: "ticket" },
                h(
                  "div",
                  { class: "split" },
                  h("h2", {}, o.number),
                  badge(o.status),
                ),
                h(
                  "p",
                  { class: "muted" },
                  o.table +
                    " · " +
                    Math.max(
                      0,
                      Math.floor((Date.now() / 1000 - o.created) / 60),
                    ) +
                    " min ago",
                ),
                orderLines(o.lines),
                kitchenNext[o.status] &&
                  button(
                    "Mark " + kitchenNext[o.status],
                    () =>
                      change("orders/" + o.id + "/status", {
                        status: kitchenNext[o.status],
                      }),
                    "btn wide",
                  ),
              ),
            ),
          )
        : empty("No kitchen tickets at this stage."),
    ];
  }
  if (page === "orders") {
    const list = await req("orders" + pageQuery(page));
    function view(o) {
      let d;
      d = modal(
        o.number,
        stack(
          h("p", { class: "muted" }, o.table + " · " + stamp(o.created, zone)),
          badge(o.status),
          orderLines(o.lines, cur),
          totals(o),
          section(
            "Order history",
            kv(o.history.map((s) => [human(s.status), stamp(s.created, zone)])),
          ),
          actions(
            o.status === "ready" &&
              button("Mark served", async () => {
                await change("orders/" + o.id + "/status", {
                  status: "served",
                });
                d.close();
              }),
            rights.includes("checkout") &&
              !o.bill_id &&
              !["cancelled", "completed"].includes(o.status) &&
              button("Request bill for this visit", async () => {
                await change("orders/" + o.id + "/bill", undefined, "POST");
                d.close();
              }),
            rights.includes("kitchen") &&
              ["received", "accepted"].includes(o.status) &&
              !o.bill_id &&
              button(
                "Cancel order",
                () => {
                  d.close();
                  editor(
                    "Cancel " + o.number,
                    [field("Reason", "reason", { required: true })],
                    (x) =>
                      change("orders/" + o.id + "/status", {
                        status: "cancelled",
                        reason: x.reason,
                      }),
                    "Cancel order",
                  );
                },
                "btn light",
              ),
          ),
        ),
      );
    }
    return [
      title("Orders"),
      section(
        "Order register",
        table(
          ["Order", "Table", "Placed", "Kitchen stage", "Total", "Action"],
          list.map((o) => [
            o.number,
            o.table,
            stamp(o.created, zone),
            badge(o.status),
            money(o.total, cur),
            button("View", () => view(o), "btn light small"),
          ]),
          "Guest orders will appear here.",
        ),
        pageControls(page, list, refresh),
      ),
    ];
  }
  if (page === "checkout") {
    const bills = await req("bills" + pageQuery(page, billFilter));
    const stages = [
      "all",
      "pending",
      "accepted",
      "prepared",
      "awaiting_payment",
      "paid",
      "completed",
      "cancelled",
    ];
    const filter = field("Checkout status", "status", {
      choices: stages,
      value: billFilter,
    });
    filter.onchange = () => {
      cursors.checkout = [null];
      billFilter = filter.querySelector("select").value;
      refresh();
    };
    function details(b) {
      let d;
      const next = billNext[b.status];
      const move = async (data) => {
        await change("bills/" + b.id, data);
        d.close();
      };
      const nodes = [
        h(
          "div",
          { class: "split" },
          h("p", {}, b.table + " · Visit " + b.visit_id),
          badge(b.status),
        ),
        kv([
          ["Requested", stamp(b.created, zone)],
          ["Assigned staff", b.assigned || "Unassigned"],
          ["Payment", human(b.payment_status)],
        ]),
        ...b.orders.map((o) =>
          section(o.number, orderLines(o.lines, b.currency)),
        ),
        totals(b),
        b.reason && h("p", {}, "Adjustment note · " + b.reason),
        b.cancel_reason && h("p", {}, "Cancellation · " + b.cancel_reason),
        b.payment &&
          kv([
            ["Payment method", human(b.payment.method)],
            ["Reference", b.payment.reference || "—"],
          ]),
      ];
      if (next === "prepared" && rights.includes("adjust")) {
        nodes.push(
          form(
            [
              grid(
                field("Extra charge", "charge", {
                  type: "number",
                  min: 0,
                  step: "0.01",
                  value: 0,
                }),
                field("Discount", "discount", {
                  type: "number",
                  min: 0,
                  step: "0.01",
                  value: 0,
                }),
              ),
              field("Adjustment reason", "reason"),
            ],
            (x) =>
              move({
                status: next,
                adjustment: asMinor(x.charge),
                discount: asMinor(x.discount),
                reason: x.reason,
              }),
            billLabels[next],
          ),
        );
      } else if (next === "paid" && rights.includes("payment")) {
        nodes.push(
          form(
            [
              field("Payment method", "method", {
                choices: [
                  ["cash", "Cash"],
                  ["upi", "UPI"],
                  ["card", "Card"],
                ],
              }),
              field("Payment reference", "reference"),
              field("I have confirmed receipt of this payment", "confirmed", {
                type: "checkbox",
                required: true,
              }),
            ],
            (x) =>
              move({
                status: next,
                method: x.method,
                reference: x.reference,
                confirmed: !!x.confirmed,
              }),
            billLabels[next],
          ),
        );
      } else if (next === "paid")
        nodes.push(
          h(
            "p",
            { class: "notice" },
            "A team member with payment permission must confirm receipt.",
          ),
        );
      else if (next)
        nodes.push(button(billLabels[next], () => move({ status: next })));
      if (
        ["pending", "accepted", "prepared", "awaiting_payment"].includes(
          b.status,
        )
      ) {
        nodes.push(
          h(
            "details",
            {},
            h("summary", {}, "Cancel bill request"),
            form(
              [field("Cancellation reason", "reason", { required: true })],
              (x) => move({ status: "cancelled", reason: x.reason }),
              "Cancel request",
            ),
          ),
        );
      }
      d = modal("Bill #" + b.id, stack(...nodes));
    }
    const filtered = bills.filter(
      (b) => billFilter === "all" || b.status === billFilter,
    );
    return [
      title("Checkout / bill requests", "Move bills forward from this list. Open a bill only for payment confirmation or details."),
      filter,
      section(
        "Table bills",
        table(
          [
            "Table / visit",
            "Orders",
            "Requested",
            "Bill",
            "Payment",
            "Total",
            "Action",
          ],
          filtered.map((b) => [
            b.table + " / " + b.visit_id,
            b.orders.map((o) => o.number).join(", "),
            stamp(b.created, zone),
            badge(b.status),
            badge(b.payment_status),
            money(b.total, b.currency),
            actions(
              button("View bill", () => details(b), "btn quiet small"),
              billNext[b.status] === "paid"
                ? button("Record payment", () => details(b), "btn small")
                : billNext[b.status]
                  ? button(
                      billLabels[billNext[b.status]],
                      () => change("bills/" + b.id, { status: billNext[b.status] }),
                      "btn small",
                    )
                  : "—",
            ),
          ]),
          "No bill requests at this stage.",
        ),
        pageControls(page, bills, refresh),
      ),
    ];
  }
  if (page === "service") {
    const list = await req("services");
    return [
      title("Service requests"),
      section(
        "Floor queue",
        table(
          ["Table", "Request", "Note", "Time", "State", "Action"],
          list.map((s) => [
            s.table,
            human(s.kind),
            s.note || "—",
            stamp(s.created, zone),
            badge(s.status),
            s.status === "resolved"
              ? "—"
              : button(
                  s.status === "open" ? "Accept" : "Resolve",
                  () =>
                    change("services/" + s.id, {
                      status: s.status === "open" ? "accepted" : "resolved",
                    }),
                  "btn light small",
                ),
          ]),
          "No service requests yet.",
        ),
      ),
    ];
  }
  if (page === "reports") {
    const params = new URLSearchParams(
      Object.entries(range).filter(([, v]) => v),
    );
    const d = await req("reports?" + params.toString());
    const active = d.days.filter((x) => x.orders || x.paid),
      max = Math.max(1, ...active.map((x) => x.orders));
    return [
      title(
        "Restaurant reports",
        "Sales use the payment receipt date in " + zone + ".",
      ),
      form(
        [
          grid(
            field("From", "start", {
              type: "date",
              required: true,
              value: d.from,
            }),
            field("Through", "end", {
              type: "date",
              required: true,
              value: d.to,
            }),
          ),
        ],
        async (x) => {
          range = x;
          await refresh();
        },
        "Apply dates",
      ),
      metrics([
        ["Gross order value", money(d.gross, cur)],
        ["Paid revenue", money(d.paid, cur)],
        ["Pending bills", money(d.pending_payments, cur)],
        ["Average order value", money(d.average, cur)],
      ]),
      section(
        "Orders by date",
        table(
          ["Date", "Volume", "Orders", "Paid revenue"],
          active.map((x) => [
            x.date,
            h("progress", {
              max,
              value: x.orders,
              "aria-label": x.orders + " orders",
            }),
            x.orders,
            money(x.paid, cur),
          ]),
          "No order or payment activity in this period.",
        ),
      ),
      grid(
        values("Popular dishes · units", d.popular),
        values("Category sales before charges", d.categories, (n) =>
          money(n, cur),
        ),
        values("Peak ordering hours", d.hours),
        values("Table activity", d.tables),
        values("Service requests", d.service),
        values("Checkout stages", d.checkout),
        values("Payment methods", d.methods, (n) => money(n, cur)),
        section(
          "Order counts",
          kv([
            ["Valid orders", d.orders],
            ["Cancelled", d.cancelled_orders],
          ]),
        ),
      ),
    ];
  }
  const log = await req("audit");
  return [
    title("Restaurant audit log"),
    section(
      "Recent activity",
      table(
        ["When", "Actor", "Action", "Record", "Detail"],
        log.map((a) => [
          stamp(a.created, zone),
          a.actor,
          human(a.action),
          a.entity,
          a.detail || "—",
        ]),
      ),
    ),
  ];
}
