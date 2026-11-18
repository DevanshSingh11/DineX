export const root = document.getElementById("app");
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked") node[k] = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const child of children.flat(Infinity))
    if (child !== null && child !== undefined && child !== false)
      node.append(child);
  return node;
}
export const brand = () =>
  h(
    "a",
    { class: "brand", href: "/", "aria-label": "DineX home" },
    h("span", { class: "brandmark", "aria-hidden": "true" }),
    "Dine",
    h("span", { class: "brandx" }, "X"),
  );
export const stack = (...nodes) => h("div", { class: "stack" }, nodes);
export const actions = (...nodes) => h("div", { class: "actions" }, nodes);
export const grid = (...nodes) => h("div", { class: "grid" }, nodes);
export const title = (heading, sub = "") =>
  h(
    "div",
    { class: "section-head" },
    h("h1", {}, heading),
    sub && h("p", {}, sub),
  );
export const section = (label, ...nodes) =>
  h("section", { class: "panel" }, h("h2", {}, label), nodes);
export const empty = (msg) => h("p", { class: "empty" }, msg);
export const link = (label, url, cls = "btn light") =>
  h("a", { class: cls, href: url }, label);
export const human = (v) =>
  String(v ?? "")
    .replaceAll("_", " ")
    .replaceAll(".", " · ")
    .replace(/^./, (c) => c.toUpperCase());
export const badge = (v) =>
  h(
    "span",
    { class: "badge s-" + String(v).replace(/[^a-z0-9_-]/gi, "") },
    human(v),
  );
export const money = (n, cur = "INR") =>
  new Intl.NumberFormat("en", { style: "currency", currency: cur }).format(
    Number(n) / 100,
  );
export const stamp = (n, zone) =>
  new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: zone,
  }).format(new Date(n * 1000));
export function asMinor(value) {
  const s = String(value).trim();
  if (!/^\d+(\.\d{1,2})?$/.test(s))
    throw Error("Enter an amount with up to two decimal places.");
  const [whole, fraction = ""] = s.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}
export async function api(
  path,
  { method = "GET", data, token, bytes, contentType } = {},
) {
  const headers = { "X-DineX": "1" };
  if (token) headers.Authorization = "Bearer " + token;
  if (data !== undefined) headers["Content-Type"] = "application/json";
  if (bytes)
    headers["Content-Type"] = contentType || "application/octet-stream";
  let res;
  try {
    res = await fetch("/api/" + path, {
      method,
      headers,
      body: bytes || (data === undefined ? undefined : JSON.stringify(data)),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw Error("Connection interrupted. Check your connection and retry.");
  }
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = Error(payload.detail || "Request failed. Try again.");
    e.status = res.status;
    throw e;
  }
  return payload;
}
let toastTimer;
export function toast(msg, isError = false) {
  const node = document.getElementById("toast");
  node.textContent = msg;
  node.className = isError ? "show bad" : "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.className = ""), 6000);
}
export function button(label, fn, cls = "btn") {
  const b = h("button", { type: "button", class: cls }, label);
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await fn();
    } catch (e) {
      toast(e.message, true);
    } finally {
      b.disabled = false;
    }
  });
  return b;
}
export function field(label, name, opt = {}) {
  const { type = "text", value = "", choices, help, ...rest } = opt;
  let input;
  if (choices) {
    input = h(
      "select",
      { name, ...rest },
      choices.map((x) => {
        const pair = Array.isArray(x) ? x : [x, human(x)];
        return h("option", { value: pair[0] }, pair[1]);
      }),
    );
    if (value !== "") input.value = String(value);
  } else if (type === "textarea")
    input = h("textarea", { name, rows: 3, value, ...rest });
  else
    input = h("input", {
      type,
      name,
      value: type === "checkbox" ? undefined : value,
      checked: type === "checkbox" && !!value,
      ...rest,
    });
  if (type === "checkbox")
    return h("label", { class: "check" }, input, h("span", {}, label));
  return h(
    "label",
    { class: "field" },
    h("span", {}, label),
    input,
    help && h("small", {}, help),
  );
}
export function form(contents, submit, label = "Save changes") {
  const error = h("p", { class: "form-error", role: "alert", hidden: true });
  const send = h("button", { class: "btn", type: "submit" }, label);
  const f = h(
    "form",
    { class: "stack" },
    contents,
    error,
    h("div", { class: "actions" }, send),
  );
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (send.disabled) return;
    send.disabled = true;
    error.hidden = true;
    try {
      await submit(Object.fromEntries(new FormData(f)), f);
    } catch (ex) {
      error.textContent = ex.message;
      error.hidden = false;
    } finally {
      send.disabled = false;
    }
  });
  return f;
}
export function modal(label, content) {
  const d = h("dialog", { class: "dialog", "aria-label": label });
  const close = () => d.close();
  d.append(
    h(
      "div",
      { class: "dialog-head" },
      h("h2", {}, label),
      button("Close", close, "btn quiet"),
    ),
    content,
  );
  document.body.append(d);
  d.addEventListener("close", () => d.remove(), { once: true });
  d.showModal();
  return d;
}
export function editor(label, contents, submit, ok = "Save changes") {
  let d;
  d = modal(
    label,
    form(
      contents,
      async (data, f) => {
        await submit(data, f);
        d.close();
      },
      ok,
    ),
  );
  return d;
}
export function table(headers, body, none = "Nothing here yet.") {
  if (!body.length) return empty(none);
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          headers.map((x) => h("th", { scope: "col" }, x)),
        ),
      ),
      h(
        "tbody",
        {},
        body.map((row) =>
          h(
            "tr",
            {},
            row.map((x) => h("td", {}, x)),
          ),
        ),
      ),
    ),
  );
}
export function metrics(entries) {
  return h(
    "div",
    { class: "metrics" },
    entries.map(([name, value]) =>
      h(
        "div",
        { class: "metric" },
        h("span", {}, name),
        h("strong", {}, String(value)),
      ),
    ),
  );
}
export const currOptions = [
  "INR",
  "USD",
  "GBP",
  "EUR",
  "AUD",
  "CAD",
  "AED",
  "SGD",
].map((c) => [c, c]);
export const safeNumber = (value) => Number(value || 0);
export function uploadField(label, name, value = "") {
  const url = field(label, name, {
    value,
    placeholder: "HTTPS image URL or upload below",
  });
  const upload = h("input", {
    type: "file",
    accept: "image/png,image/jpeg,image/webp",
    "aria-label": "Upload " + label,
  });
  const status = h(
    "small",
    { role: "status" },
    "JPEG, PNG or WebP · up to 3 MiB",
  );
  upload.onchange = async () => {
    const file = upload.files[0];
    if (!file) return;
    const f = upload.closest("form");
    const getSubmit = () => f?.querySelector('button[type="submit"]');
    if (file.size > 3145728) {
      upload.value = "";
      status.textContent = "Choose a smaller image.";
      return;
    }
    upload.disabled = true;
    if (getSubmit()) getSubmit().disabled = true;
    try {
      status.textContent = "Uploading…";
      const x = await api("restaurant/images", { method: "POST", bytes: file });
      url.querySelector("input").value = x.url;
      status.textContent = "Image uploaded.";
    } catch (e) {
      status.textContent = e.message;
    } finally {
      upload.disabled = false;
      if (getSubmit()) getSubmit().disabled = false;
    }
  };
  return h("div", { class: "stack tight" }, url, upload, status);
}
export const kv = (values) =>
  h(
    "dl",
    { class: "facts" },
    values.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]),
  );
export function orderLines(lines, currency) {
  return h(
    "ul",
    { class: "ticket-lines" },
    lines.map((l) =>
      h(
        "li",
        {},
        h("strong", {}, l.quantity + " × " + l.name),
        currency &&
          h(
            "span",
            { class: "line-money" },
            money(l.quantity * l.unit_price, currency),
          ),
        l.selections.length > 0 &&
          h(
            "small",
            {},
            l.selections.map((s) => s.group + " · " + s.name).join(", "),
          ),
        l.note && h("em", {}, l.note),
        l.available === false && badge("now unavailable"),
      ),
    ),
  );
}
export const totals = (b) =>
  kv([
    ["Subtotal", money(b.subtotal, b.currency)],
    ...(b.tax ? [["Tax", money(b.tax, b.currency)]] : []),
    ...(b.charges ? [["Service charge", money(b.charges, b.currency)]] : []),
    ...(b.adjustment
      ? [["Added charge", money(b.adjustment, b.currency)]]
      : []),
    ...(b.discount ? [["Discount", "−" + money(b.discount, b.currency)]] : []),
    ["Total", money(b.total, b.currency)],
  ]);
export function registrationFields() {
  return [
    grid(
      field("Restaurant name", "name", { required: true }),
      field("Restaurant slug", "slug", {
        required: true,
        pattern: "[a-z0-9]+(-[a-z0-9]+)*",
        minlength: 2,
        help: "Use this name to sign in.",
      }),
    ),
    grid(
      field("Owner name", "owner_name", { required: true }),
      field("Owner email", "owner_email", { type: "email", required: true }),
    ),
    grid(
      field("Owner password", "password", {
        type: "password",
        required: true,
        minlength: 12,
        autocomplete: "new-password",
      }),
      field("Contact number", "contact", { type: "tel", required: true }),
    ),
    grid(
      field("Street address", "address", { required: true }),
      field("City", "city", { required: true }),
      field("State or region", "region"),
      field("Country", "country", { required: true }),
    ),
    h(
      "details",
      {},
      h("summary", {}, "Menu identity and operating defaults"),
      h(
        "div",
        { class: "stack inset" },
        field("Description", "description", { type: "textarea" }),
        grid(
          field("Cuisine", "cuisine"),
          field("Opening hours", "hours"),
          field("Logo URL", "logo", { type: "url" }),
          field("Restaurant image URL", "cover", { type: "url" }),
        ),
        grid(
          field("Initial tables", "table_count", {
            type: "number",
            min: 0,
            max: 100,
            value: 0,
          }),
          field("Order prefix", "prefix", {
            value: "DX",
            required: true,
            maxlength: 8,
          }),
          field("Currency", "currency", { choices: currOptions }),
          field("Time zone", "timezone", {
            value: "Asia/Kolkata",
            required: true,
          }),
        ),
      ),
    ),
  ];
}
export function registrationData(d) {
  return { ...d, table_count: Number(d.table_count || 0) };
}
