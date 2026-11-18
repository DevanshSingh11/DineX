// Exercise the shipped browser modules against a real, disposable FastAPI server.
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { JSDOM, CookieJar, VirtualConsole } from "jsdom";
import { build } from "esbuild";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const { origin, password } = JSON.parse(input);
const assets = fileURLToPath(new URL("../../web/static/", import.meta.url));
const jar = new CookieJar(),
  pages = [],
  bundles = new Map(),
  errors = [];
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, description) {
  const until = Date.now() + 6500;
  while (Date.now() < until) {
    if (check()) return;
    await pause(15);
  }
  throw Error("Timed out waiting for " + description + ". " + errors.join(" "));
}
async function open(path, module, jarHere = jar) {
  const url = new URL(path, origin);
  const html = await (await fetch(url)).text();
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(e.message));
  const dom = new JSDOM(html, {
    url: url.href,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    cookieJar: jarHere,
    virtualConsole,
  });
  const w = dom.window,
    doc = w.document;
  pages.push(w);
  // jsdom supplies DOM behavior. Bridge its missing dialog, clone and Fetch APIs.
  w.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  w.HTMLDialogElement.prototype.close = function () {
    this.open = false;
    this.dispatchEvent(new w.Event("close"));
  };
  w.structuredClone = structuredClone;
  w.fetch = async (path, opt = {}) => {
    const target = new URL(path, url);
    const cookie = jarHere.getCookieStringSync(target.href);
    const headers = { ...opt.headers, origin };
    if (cookie) headers.Cookie = cookie;
    const res = await fetch(target, { ...opt, headers });
    for (const c of res.headers.getSetCookie())
      jarHere.setCookieSync(c, target.href);
    return res;
  };
  if (!bundles.has(module)) {
    const b = await build({
      entryPoints: [assets + module + ".js"],
      bundle: true,
      platform: "browser",
      format: "iife",
      write: false,
      logLevel: "silent",
    });
    bundles.set(module, b.outputFiles[0].text);
  }
  w.eval(bundles.get(module));
  const live = () => doc.querySelector("dialog[open]") || doc;
  const find = (selector, txt) =>
    Array.from(live().querySelectorAll(selector)).find(
      (el) => el.textContent.trim() === txt,
    );
  const api = {
    doc,
    w,
    button: async (text) => {
      await until(
        () => find("button", text) && !find("button", text).disabled,
        "button " + text,
      );
      find("button", text).click();
      await pause(35);
    },
    heading: async (text) =>
      until(() => find("h1,h2,h3", text), "heading " + text),
    text: async (text) =>
      until(
        () => doc.body.textContent.includes(text),
        "visible content " + text,
      ),
    fields: (values) => {
      for (const [k, v] of Object.entries(values)) {
        const el = live().querySelector('[name="' + k + '"]');
        assert(el, "missing field " + k);
        if (el.type === "checkbox") el.checked = !!v;
        else el.value = String(v);
        el.dispatchEvent(new w.Event("input", { bubbles: true }));
        el.dispatchEvent(new w.Event("change", { bubbles: true }));
      }
    },
    link: async (text) => {
      const a = find("a", text);
      assert(a, "missing nav link " + text);
      a.click();
      await pause(50);
    },
    close: async () =>
      until(() => !doc.querySelector("dialog[open]"), "dialog close"),
    goto: async (hash) => {
      w.location.hash = hash;
      await pause(30);
    },
  };
  return api;
}
try {
  const reg = await open("/register", "register");
  reg.fields({
    name: "Acacia Kitchen",
    slug: "acacia",
    owner_name: "Test owner",
    owner_email: "owner@example.test",
    password,
    address: "Market street",
    city: "Pune",
    country: "India",
    contact: "0000000000",
  });
  await reg.button("Register restaurant");
  await reg.heading("Registration received");
  const plat = await open("/platform", "workspace");
  await plat.heading("Welcome back.");
  plat.fields({ email: "operator@example.test", password });
  await plat.button("Sign in");
  await plat.heading("Platform overview");
  await plat.button("Review");
  await plat.heading("Acacia Kitchen");
  plat.fields({ status: "active" });
  await plat.button("Review registration");
  await plat.close();
  for (const [hash, heading] of [
    ["plans", "Plans & limits"],
    ["accounts", "Platform accounts"],
    ["policy", "Registration settings"],
    ["audit", "Platform audit log"],
  ]) {
    await plat.goto(hash);
    await plat.heading(heading);
  }

  const staff = await open("/restaurant", "workspace");
  await staff.heading("Welcome back.");
  staff.fields({ slug: "acacia", email: "owner@example.test", password });
  await staff.button("Sign in");
  await staff.heading("Service overview");
  await staff.goto("onboarding");
  await staff.heading("Restaurant setup");
  staff.fields({ step: 2 });
  await staff.heading("Menu categories");
  staff.fields({ name: "Supper" });
  await staff.button("Create category");
  await staff.text("Supper");
  await staff.goto("menu");
  await staff.heading("Menu & categories");
  await staff.button("Add dish");
  await staff.heading("Add a dish");
  staff.fields({
    name: "Cumin cauliflower",
    price: "280.00",
    dietary: "vegetarian",
    ingredients: "Cauliflower, cumin",
  });
  await staff.button("Add customization group");
  staff.fields({
    group_name: "Portion",
    group_min: 1,
    group_max: 1,
    option_name: "Large",
    option_price: "45.00",
  });
  await staff.button("Create dish");
  await staff.close();
  await staff.text("Cumin cauliflower");
  await staff.goto("tables");
  await staff.heading("Tables & QR");
  await staff.button("Create table");
  staff.fields({ name: "Courtyard" });
  await staff.button("Save changes");
  await staff.close();
  await staff.button("Show QR");
  await staff.heading("Courtyard QR code");
  const url = staff.doc.querySelector('dialog a[target="_blank"]').href;
  const png = staff.doc.querySelector("dialog img").src;
  const qr = await staff.w.fetch(png);
  assert.equal(qr.status, 200);
  assert.equal(qr.headers.get("content-type"), "image/png");
  await staff.button("Close");
  await staff.goto("staff");
  await staff.heading("Team");
  await staff.button("Add team member");
  staff.fields({
    name: "Line cook",
    email: "cook@example.test",
    password,
    role: "Kitchen",
  });
  await staff.button("Save changes");
  await staff.close();
  await staff.text("Line cook");
  await staff.goto("profile");
  await staff.heading("Restaurant settings");
  staff.fields({
    logo: "https://example.test/logo.png",
    tax_bps: "0",
    charge_bps: "0",
  });
  await staff.button("Save changes");
  await staff.text("8 of 8 complete");

  const guest = await open(url, "guest", new CookieJar());
  await guest.heading("The menu");
  await guest.button("Customize");
  await guest.heading("Cumin cauliflower");
  guest.doc.querySelector('dialog input[type="radio"]').click();
  guest.fields({ quantity: 2, note: "Sauce on side" });
  await guest.button("Add to cart");
  await guest.button("Cart (2)");
  await guest.text("₹650.00");
  await guest.button("Place order");
  await guest.heading("Your orders & bill");
  await guest.button("Request bill / checkout");
  await guest.button("Confirm bill request");
  await guest.text("Checkout requested — waiting for staff.");
  await guest.button("DineX AI");
  guest.fields({ question: "vegetarian dishes" });
  await guest.button("Find dishes");
  await guest.text("local menu guide");
  await guest.button("Service");
  guest.fields({ kind: "water", note: "Two glasses" });
  await guest.button("Send request");
  await guest.text("Open");

  const kitchen = await open("/kitchen", "workspace", new CookieJar());
  await kitchen.heading("Welcome back.");
  kitchen.fields({ slug: "acacia", email: "cook@example.test", password });
  await kitchen.button("Sign in");
  await kitchen.heading("Kitchen display");
  await kitchen.text("Sauce on side");
  for (const stage of ["accepted", "preparing", "ready", "served"])
    await kitchen.button("Mark " + stage);
  await staff.goto("service");
  await staff.heading("Service requests");
  await staff.button("Accept");
  await staff.button("Resolve");
  await staff.goto("checkout");
  await staff.heading("Checkout / bill requests");
  for (const action of [
    "Accept request",
    "Prepare bill",
    "Await payment",
    "Record payment",
    "Complete checkout",
  ]) {
    await staff.button("View bill");
    await staff.heading("Bill #1");
    if (action === "Prepare bill")
      staff.fields({ discount: "10.00", reason: "Courtesy" });
    if (action === "Record payment")
      staff.fields({ method: "cash", confirmed: true });
    await staff.button(action);
    await staff.close();
  }
  await guest.button("Orders & bill");
  await guest.text("Checkout completed. Thank you for visiting.");
  await staff.goto("reports");
  await staff.heading("Restaurant reports");
  await staff.text("₹640.00");
  await staff.goto("tables");
  await staff.heading("Tables & QR");
  await staff.text("Available");
  assert.deepEqual(errors, []);
  console.log(
    "DOM journey passed: approval, eight setup steps, menu, staff, QR, guest cart, tracking, service, guide, kitchen, discounted bill, manual receipt, release and reporting.",
  );
} finally {
  for (const page of pages) page.close();
}
