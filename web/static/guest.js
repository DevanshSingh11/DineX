import { createGuide } from "./guide.js";
import {
  root,
  h,
  stack,
  actions,
  grid,
  section,
  table,
  form,
  field,
  button,
  modal,
  editor,
  empty,
  api,
  title,
  badge,
  human,
  money,
  stamp,
  kv,
  orderLines,
  totals,
  toast,
} from "./ui.js";

const [, , slug, tableId] = location.pathname.split("/");
const sessionKey = "dinex.visit." + slug + "." + tableId;
let token = sessionStorage.getItem(sessionKey) || "",
  catalog,
  state,
  cart = [],
  pending = null,
  pane = "menu",
  search = "",
  category = "all",
  view,
  nav,
  cartDock,
  meta,
  storeKey = "",
  refreshing = false,
  guide,
  serviceDraft = "";
const call = (p, opt = {}) => api("guest/" + p, { ...opt, token });
const cash = (n) => money(n, catalog.restaurant.currency);
function persist() {
  sessionStorage.setItem(storeKey, JSON.stringify({ cart, pending }));
}
function key() {
  return Array.from(crypto.getRandomValues(new Uint8Array(18)), (v) =>
    v.toString(16).padStart(2, "0"),
  ).join("");
}
function itemById(id) {
  return catalog.items.find((i) => i.id === id);
}
function openBill() {
  return state.bills.find((b) => b.status !== "cancelled");
}
function allowEdit() {
  if (pending)
    throw Error("Retry the pending submission before editing your cart.");
}
function unitPrice(i, ids) {
  if (!i) return 0;
  return (
    i.price +
    i.groups
      .flatMap((g) => g.options)
      .filter((o) => ids.includes(o.id))
      .reduce((sum, o) => sum + o.price, 0)
  );
}
function billEstimate() {
  const r = catalog.restaurant;
  const subtotal = cart.reduce(
    (sum, l) => sum + unitPrice(itemById(l.item_id), l.options) * l.quantity,
    0,
  );
  const portion = (bps) =>
    Number((BigInt(subtotal) * BigInt(bps) + 5000n) / 10000n);
  const tax = portion(r.tax_bps),
    charges = portion(r.charge_bps);
  return {
    subtotal,
    tax,
    charges,
    total: subtotal + tax + charges,
    currency: r.currency,
  };
}
function switchTo(next) {
  if (pane === "assistant") guide?.leave();
  pane = next;
  render();
  document.documentElement.scrollTop = 0;
}
function ingredientLabels(ids) {
  return catalog.allergen_options
    .filter((a) => ids.includes(a.id))
    .map((a) => a.name)
    .join(", ");
}
function itemDialog(i, index = -1) {
  allowEdit();
  const old = cart[index] || { options: [], quantity: 1, note: "" },
    groups = [];
  const choices = i.groups.map((g) => {
    const controls = g.options.map((o) => {
      const type = g.maximum === 1 && g.minimum > 0 ? "radio" : "checkbox";
      const input = h("input", {
        type,
        name: "g" + g.id,
        value: o.id,
        checked: old.options.includes(o.id),
      });
      groups.push({ g, o, input });
      return h(
        "label",
        { class: "option" },
        input,
        h("span", {}, o.name),
        o.price > 0 && h("small", {}, "+" + cash(o.price)),
      );
    });
    return h(
      "fieldset",
      { class: "group-card" },
      h("legend", {}, g.name),
      h(
        "p",
        { class: "muted" },
        g.minimum === g.maximum
          ? "Choose " + g.minimum
          : "Choose " + g.minimum + "–" + g.maximum,
      ),
      controls,
    );
  });
  const qty = field("Quantity", "quantity", {
    type: "number",
    min: 1,
    max: 50,
    value: old.quantity,
    required: true,
  });
  const cost = h("strong", { class: "item-cost" });
  const contents = stack(
    i.image && h("img", { class: "detail-img", src: i.image, alt: i.name }),
    i.description && h("p", {}, i.description),
    i.ingredients &&
      h("p", { class: "muted" }, "Ingredients · " + i.ingredients),
    i.recipe_status &&
      h(
        "small",
        { class: "muted" },
        i.recipe_status === "unreviewed"
          ? "Ask staff for the current allergen record."
          : (i.recipe_status === "sample"
              ? "Sample recipe"
              : "Kitchen recipe") +
              " · Declared allergens: " +
              (ingredientLabels(i.allergens) || "none listed") +
              " · Possible traces: " +
              (ingredientLabels(i.may_contain) || "none recorded"),
      ),
    choices,
    qty,
    field("Kitchen instructions", "note", { value: old.note, maxlength: 220 }),
    cost,
  );
  function displayCost() {
    cost.textContent =
      "Line total · " +
      cash(
        unitPrice(
          i,
          groups.filter((x) => x.input.checked).map((x) => x.o.id),
        ) * Number(qty.querySelector("input").value),
      );
  }
  contents.oninput = displayCost;
  displayCost();
  editor(
    i.name,
    [contents],
    async (d) => {
      const options = groups.filter((x) => x.input.checked).map((x) => x.o.id);
      for (const g of i.groups) {
        const n = g.options.filter((o) => options.includes(o.id)).length;
        if (n < g.minimum || n > g.maximum)
          throw Error("Check your choices for " + g.name + ".");
      }
      const line = {
        item_id: i.id,
        options,
        quantity: Number(d.quantity),
        note: d.note,
      };
      if (index < 0) cart.push(line);
      else cart[index] = line;
      persist();
      render();
      toast(index < 0 ? "Added to cart." : "Cart updated.");
    },
    index < 0 ? "Add to cart" : "Update cart",
  );
}
function menuPage() {
  const r = catalog.restaurant;
  const find = field("Search the menu", "find", {
    type: "search",
    placeholder: "Dish, ingredient or dietary preference",
    value: search,
  });
  const cat = h("div", { class: "chips", "aria-label": "Menu categories" });
  const items = h("div", { class: "dish-grid" });
  const more = h("div", { class: "actions" });
  let visible = 12;
  function draw() {
    cat.replaceChildren(
      ...[
        ["all", "All dishes"],
        ["featured", "Featured"],
        ...catalog.categories.map((c) => [String(c.id), c.name]),
      ].map(([id, name]) => {
        const b = button(
          name,
          () => {
            category = id;
            visible = 12;
            draw();
          },
          "chip" + (category === id ? " selected" : ""),
        );
        b.setAttribute("aria-pressed", String(category === id));
        return b;
      }),
    );
    const q = search.trim().toLowerCase();
    const list = catalog.items
      .filter(
        (i) =>
          (category === "all" ||
            (category === "featured" && i.featured) ||
            String(i.category_id) === category) &&
          (!q ||
            [i.name, i.description, i.ingredients, i.dietary]
              .join(" ")
              .toLowerCase()
              .includes(q)),
      )
      .sort((a, b) => Number(b.featured) - Number(a.featured));
    items.replaceChildren(
      ...(list.length
        ? list.slice(0, visible).map((i) => {
            const tags = [
              i.featured && "Featured",
              i.dietary !== "unspecified" && human(i.dietary),
              i.minutes > 0 && i.minutes + " min",
            ].filter(Boolean);
            const add = button(
              "Customize",
              () => itemDialog(i),
              "btn light small",
            );
            add.disabled =
              !i.available || !catalog.can_order || !!openBill() || !!pending;
            return h(
              "article",
              { class: "dish" + (i.image ? " with-photo" : "") },
              i.image &&
                h("img", { src: i.image, alt: i.name, loading: "lazy" }),
              h(
                "div",
                { class: "dish-body" },
                tags.length > 0 &&
                  h("p", { class: "dish-tags" }, tags.join(" · ")),
                h("h3", {}, i.name),
                i.description && h("p", {}, i.description),
                h(
                  "div",
                  { class: "split" },
                  h("strong", {}, cash(i.price)),
                  i.available ? add : badge("unavailable"),
                ),
              ),
            );
          })
        : [empty("No dishes match this selection.")]),
    );
    more.replaceChildren();
    if (list.length > visible) {
      more.append(
        h("small", {}, visible + " of " + list.length + " dishes"),
        button(
          "Show more dishes",
          () => {
            visible += 12;
            draw();
          },
          "btn light",
        ),
      );
    }
  }
  find.oninput = () => {
    search = find.querySelector("input").value;
    visible = 12;
    draw();
  };
  draw();
  return stack(
    r.cover &&
      h("img", { class: "cover", alt: r.name + " restaurant", src: r.cover }),
    h(
      "div",
      { class: "section-head" },
      h("p", { class: "eyebrow" }, r.cuisine || "Table menu"),
      h("h1", {}, "The menu"),
      r.description && h("p", {}, r.description),
      r.hours && h("small", {}, "Hours · " + r.hours),
    ),
    !catalog.can_order &&
      h(
        "p",
        { class: "notice" },
        "Scan a current table QR to start a new order.",
      ),
    openBill() &&
      h("p", { class: "notice" }, "Your bill is available in Orders & bill."),
    catalog.guide.enabled &&
      h(
        "div",
        { class: "ai-invite" },
        h(
          "div",
          {},
          h("strong", {}, "DineX AI"),
          h("p", {}, "Tell me what you’d like, or what you need to avoid."),
        ),
        button("Ask DineX AI", () => switchTo("assistant"), "btn"),
      ),
    find,
    cat,
    items,
    more,
  );
}
async function submitOrder() {
  if (!cart.length && !pending) return;
  if (!pending) {
    pending = { request_key: key(), lines: structuredClone(cart) };
    persist();
  }
  try {
    const o = await call("orders", { method: "POST", data: pending });
    cart = [];
    pending = null;
    persist();
    pane = "orders";
    await refreshState();
    render();
    toast("Order " + o.number + " received.");
  } catch (e) {
    if (e.status && e.status >= 400 && e.status < 500 && e.status !== 429) {
      pending = null;
      persist();
      catalog = await call("menu");
    }
    render();
    throw e;
  }
}
function cartPage() {
  const lines = cart.map((l, index) => {
    const i = itemById(l.item_id),
      price = unitPrice(i, l.options),
      selected =
        i?.groups.flatMap((g) =>
          g.options
            .filter((o) => l.options.includes(o.id))
            .map(
              (o) =>
                g.name +
                " · " +
                o.name +
                (o.price ? " (+" + cash(o.price) + ")" : ""),
            ),
        ) || [];
    function quantity(n) {
      allowEdit();
      l.quantity += n;
      if (l.quantity <= 0) cart.splice(index, 1);
      if (l.quantity > 50) l.quantity = 50;
      persist();
      render();
    }
    return h(
      "article",
      { class: "cart-line" },
      h(
        "div",
        {},
        h("h3", {}, i?.name || "Unavailable dish"),
        h("p", { class: "muted" }, selected.join(", ")),
        l.note && h("small", {}, l.note),
      ),
      h("strong", {}, cash(price * l.quantity)),
      actions(
        button("−", () => quantity(-1), "btn light small"),
        h("span", { "aria-label": "Quantity" }, String(l.quantity)),
        button("+", () => quantity(1), "btn light small"),
        i && button("Edit", () => itemDialog(i, index), "btn quiet small"),
        button(
          "Remove",
          () => {
            allowEdit();
            cart.splice(index, 1);
            persist();
            render();
          },
          "btn quiet small",
        ),
      ),
    );
  });
  return stack(
    title("Your cart", catalog.table.name),
    lines.length ? section("Items", lines) : empty("Your cart is empty."),
    lines.length || pending
      ? section(
          "Order total",
          totals(billEstimate()),
          pending &&
            h(
              "p",
              { class: "notice" },
              "Your last submission needs confirmation. Retrying uses the same order reference.",
            ),
          button(pending ? "Retry submission" : "Place order", submitOrder),
        )
      : button("Browse menu", () => switchTo("menu")),
  );
}
function orderPage() {
  const r = catalog.restaurant,
    b = openBill();
  function request() {
    editor(
      "Request your bill",
      [
        h(
          "p",
          {},
          "Staff will prepare one bill for all the open orders on this visit. Further orders will pause while the bill is open.",
        ),
      ],
      async () => {
        await call("bills", { method: "POST" });
        await refreshState();
        toast("Bill requested. Waiting for staff.");
      },
      "Confirm bill request",
    );
  }
  const descriptions = {
    pending: "Checkout requested — waiting for staff.",
    accepted: "Staff accepted your bill request.",
    prepared: "Your bill is ready.",
    awaiting_payment: "Awaiting payment at the restaurant.",
    paid: "Payment received.",
    completed: "Checkout completed. Thank you for visiting.",
    cancelled: "This bill request was cancelled.",
  };
  function billCard(x) {
    return section(
      "Bill #" + x.id,
      h("p", { class: "notice" }, descriptions[x.status]),
      kv([
        ["Payment", human(x.payment_status)],
        ["Orders", x.orders.map((o) => o.number).join(", ")],
      ]),
      totals(x),
      x.reason && h("p", {}, "Adjustment · " + x.reason),
      x.cancel_reason && h("p", {}, x.cancel_reason),
      x.payment &&
        h(
          "p",
          {},
          "Received by " +
            human(x.payment.method) +
            " · " +
            stamp(x.payment.created, r.timezone),
        ),
    );
  }
  return stack(
    title("Your orders & bill", catalog.table.name),
    !b &&
      state.orders.some(
        (o) => !["completed", "cancelled"].includes(o.status),
      ) &&
      button("Request bill / checkout", request),
    state.bills.map(billCard),
    state.orders.length
      ? state.orders.map((o) =>
          section(
            o.number,
            h(
              "div",
              { class: "split" },
              badge(o.status),
              h("small", {}, stamp(o.created, r.timezone)),
            ),
            orderLines(o.lines, r.currency),
            totals(o),
            h(
              "ol",
              { class: "timeline" },
              o.history.map((x) =>
                h(
                  "li",
                  {},
                  h("strong", {}, human(x.status)),
                  h("small", {}, stamp(x.created, r.timezone)),
                ),
              ),
            ),
          ),
        )
      : empty("Orders placed on this visit will appear here."),
  );
}
function servicePage() {
  const kind = field("Request", "kind", {
    value: serviceDraft ? "ingredient_check" : "waiter",
    choices: [
      ["waiter", "Call a waiter"],
      ["water", "Water"],
      ["cutlery", "Cutlery"],
      ["assistance", "Assistance"],
      ["ingredient_check", "Check ingredients with the kitchen"],
      ["issue", "Report an issue"],
    ],
  });
  const note = field("Additional details", "note", {
    maxlength: serviceDraft ? 800 : 220,
    value: serviceDraft,
  });
  kind.onchange = () => {
    note.querySelector("input").maxLength =
      kind.querySelector("select").value === "ingredient_check" ? 800 : 220;
  };
  return stack(
    title("Table service", catalog.table.name),
    state.closed
      ? empty("This visit is closed. Scan the table code for a new visit.")
      : section(
          "Request assistance",
          form(
            [kind, note],
            async (d) => {
              await call("services", { method: "POST", data: d });
              serviceDraft = "";
              await refreshState();
              render();
              toast("Service requested.");
            },
            "Send request",
          ),
        ),
    section(
      "Your requests",
      table(
        ["Request", "Status", "Time"],
        state.services.map((s) => [
          human(s.kind),
          badge(s.status),
          stamp(s.created, catalog.restaurant.timezone),
        ]),
        "No requests on this visit.",
      ),
    ),
  );
}
function render() {
  if (!catalog || !state) return;
  nav.replaceChildren(
    ...[
      ["menu", "Menu"],
      ...(catalog.guide.enabled ? [["assistant", "DineX AI"]] : []),
      ["cart", "Cart (" + cart.reduce((n, l) => n + l.quantity, 0) + ")"],
      ["orders", "Orders & bill"],
      ["service", "Service"],
    ].map(([k, v]) => {
      const b = button(
        v,
        () => switchTo(k),
        "chip" + (pane === k ? " selected" : ""),
      );
      if (pane === k) b.setAttribute("aria-current", "page");
      return b;
    }),
  );
  view.replaceChildren(
    {
      menu: menuPage,
      cart: cartPage,
      orders: orderPage,
      service: servicePage,
      assistant: () => guide.pane(),
    }[pane](),
  );
  const quantity = cart.reduce((n, line) => n + line.quantity, 0);
  cartDock.replaceChildren();
  if (quantity && pane !== "cart") {
    cartDock.append(
      button(
        "View cart · " +
          quantity +
          " item" +
          (quantity === 1 ? "" : "s") +
          " · " +
          cash(billEstimate().total),
        () => switchTo("cart"),
        "btn guest-cart-button",
      ),
    );
  }
}
async function refreshState() {
  const previous = state;
  state = await call("state");
  if (
    pane === "orders" ||
    (pane === "service" &&
      JSON.stringify(previous?.services) !== JSON.stringify(state.services) &&
      !view.contains(document.activeElement))
  )
    render();
}
async function start() {
  try {
    const code = location.hash.slice(1);
    if (code) {
      const response = await call("enter/" + encodeURIComponent(slug), {
        method: "POST",
        data: { table_id: Number(tableId), credential: code },
      });
      token = response.token;
      sessionStorage.setItem(sessionKey, token);
      history.replaceState(null, "", location.pathname);
    }
    if (!token)
      throw Error(
        "Scan the QR code on your table to open the restaurant menu.",
      );
    [catalog, state] = await Promise.all([call("menu"), call("state")]);
    if (catalog.guide.enabled) {
      guide = createGuide({
        catalog,
        call,
        cash,
        onDish: (id) => {
          const item = itemById(id);
          if (item) itemDialog(item);
        },
        onStaff: (note) => {
          serviceDraft = note;
          switchTo("service");
        },
        canOrder: () =>
          catalog.can_order && !openBill() && !pending && !state.closed,
      });
    }
    storeKey = sessionKey + ".cart." + catalog.visit_id;
    try {
      const old = JSON.parse(sessionStorage.getItem(storeKey) || "{}");
      cart = old.cart || [];
      pending = old.pending || null;
    } catch {
      cart = [];
    }
    if (pending) pane = "cart";
    else if (state.orders.length) pane = "orders";
    const r = catalog.restaurant;
    meta = h(
      "header",
      { class: "guest-top" },
      r.logo
        ? h("img", { class: "rest-logo", src: r.logo, alt: "" })
        : h("span", { class: "brandmark", "aria-hidden": "true" }),
      h("div", {}, h("strong", {}, r.name), h("small", {}, catalog.table.name)),
      h("span", { class: "powered" }, "DineX"),
    );
    nav = h("nav", { class: "guest-nav", "aria-label": "Table navigation" });
    view = h("div", { class: "guest-content" });
    cartDock = h("div", { class: "guest-cart-dock", "aria-live": "polite" });
    root.replaceChildren(meta, nav, view, cartDock);
    document.title = r.name + " · " + catalog.table.name;
    render();
  } catch (e) {
    root.replaceChildren(
      h(
        "div",
        { class: "form-page" },
        title("Table access", e.message),
        button("Try again", start, "btn light"),
      ),
    );
  }
}
setInterval(async () => {
  if (
    !state ||
    document.hidden ||
    refreshing ||
    document.querySelector("dialog[open]")
  )
    return;
  refreshing = true;
  try {
    await refreshState();
  } catch (e) {
    toast(e.message, true);
  } finally {
    refreshing = false;
  }
}, 5000);
start();

window.addEventListener("pagehide", () => guide?.leave());
