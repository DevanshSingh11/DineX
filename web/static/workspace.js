import {
  root,
  h,
  brand,
  stack,
  actions,
  link,
  form,
  field,
  api,
  toast,
  button,
  editor,
  title,
} from "./ui.js";
import { platformPage } from "./platform.js";
import { managementPage } from "./management.js";
import { operationsPage } from "./operations.js";

const isPlatform = location.pathname === "/platform";
const kitchenOnly = location.pathname === "/kitchen";
const realm = isPlatform ? "platform" : "restaurant";
const names = {
  overview: "Overview",
  onboarding: "Setup guide",
  profile: "Restaurant settings",
  menu: "Menu & categories",
  tables: "Tables & QR",
  staff: "Team",
  orders: "Orders",
  kitchen: "Kitchen display",
  checkout: "Bill requests",
  service: "Service requests",
  reports: "Reports",
  audit: "Audit log",
  restaurants: "Restaurants",
  plans: "Plans & limits",
  accounts: "Platform accounts",
  policy: "Registration settings",
};
let user,
  main,
  nav,
  billLink,
  banner,
  soundButton,
  current = "",
  version = 0,
  lastPending = null,
  lastAlerts = {},
  audioContext = null,
  inFlight = false;

function playAlert(kind = "order") {
  if (localStorage.getItem("dinex.alert-sounds") !== "on" || !audioContext) return;
  const now = audioContext.currentTime;
  const notes = kind === "service" ? [660, 880] : kind === "bill" ? [520, 780] : [740, 980];
  notes.forEach((frequency, index) => {
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, now + index * 0.13);
    gain.gain.exponentialRampToValueAtTime(0.12, now + index * 0.13 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.13 + 0.16);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now + index * 0.13);
    oscillator.stop(now + index * 0.13 + 0.17);
  });
}
function soundControl() {
  const enabled = localStorage.getItem("dinex.alert-sounds") === "on";
  soundButton = button(enabled ? "Sound on" : "Sound off", async () => {
    const turnOn = localStorage.getItem("dinex.alert-sounds") !== "on";
    if (turnOn) {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (Audio) { audioContext ||= new Audio(); await audioContext.resume(); }
      localStorage.setItem("dinex.alert-sounds", "on");
      playAlert();
    } else localStorage.setItem("dinex.alert-sounds", "off");
    soundButton.textContent = turnOn ? "Sound on" : "Sound off";
    soundButton.setAttribute("aria-pressed", String(turnOn));
  }, "btn light small sound-toggle");
  soundButton.setAttribute("aria-pressed", String(enabled));
  return soundButton;
}

export function signIn() {
  user = null;
  current = "";
  document.title =
    (isPlatform ? "Platform" : kitchenOnly ? "Kitchen" : "Restaurant") +
    " sign in · DineX";
  const name = isPlatform
    ? "Platform console"
    : kitchenOnly
      ? "Kitchen display"
      : "Restaurant workspace";
  const contents = [
    !isPlatform &&
      field("Restaurant slug", "slug", {
        required: true,
        autocomplete: "organization",
        autocapitalize: "none",
      }),
    field("Email", "email", {
      required: true,
      type: "email",
      autocomplete: "username",
    }),
    field("Password", "password", {
      required: true,
      type: "password",
      autocomplete: "current-password",
    }),
  ];
  root.replaceChildren(
    h(
      "main",
      { class: "signin" },
      h(
        "section",
        { class: "signin-copy" },
        brand(),
        h(
          "div",
          {},
          h("p", { class: "eyebrow" }, name),
          title("Welcome back."),
          form(
            contents,
            async (data) => {
              await api(realm + "/login", { method: "POST", data });
              await start();
            },
            "Sign in",
          ),
          !isPlatform && link("Register a restaurant", "/register", "textlink"),
        ),
      ),
      h("div", { class: "signin-photo", "aria-hidden": "true" }),
    ),
  );
}
function allowed() {
  if (isPlatform)
    return ["overview", "restaurants", "plans", "accounts", "policy", "audit"];
  const list = [
    "overview",
    "orders",
    "kitchen",
    "checkout",
    "service",
    "menu",
    "tables",
    "staff",
    "reports",
    "onboarding",
    "profile",
    "audit",
  ];
  return list.filter(
    (x) =>
      (user.permissions.includes(x) ||
        (x === "onboarding" && user.permissions.includes("profile"))) &&
      (!kitchenOnly || x === "kitchen"),
  );
}
function selected() {
  const query = location.hash.slice(1);
  return allowed().includes(query) ? query : allowed()[0];
}
async function render({ quiet = false } = {}) {
  const page = selected();
  if (!page || !main) return;
  current = page;
  const revision = ++version;
  nav.querySelectorAll("a").forEach((a) => {
    if (a.hash === "#" + page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (!quiet)
    main.replaceChildren(
      h(
        "p",
        { class: "loading", role: "status" },
        "Loading " + names[page].toLowerCase() + "…",
      ),
    );
  const refresh = () => render({ quiet: true });
  const ctx = {
    user,
    refresh,
    go: (key) => {
      location.hash = key;
    },
    page,
  };
  try {
    let nodes;
    if (isPlatform) nodes = await platformPage(page, ctx);
    else if (
      ["overview", "onboarding", "profile", "menu", "tables", "staff"].includes(
        page,
      )
    )
      nodes = await managementPage(page, ctx);
    else nodes = await operationsPage(page, ctx);
    if (revision === version) {
      main.replaceChildren(...nodes);
      document.title = names[page] + " · DineX";
    }
  } catch (e) {
    if (revision !== version) return;
    if (e.status === 401) {
      signIn();
      return;
    }
    if (!quiet)
      main.replaceChildren(
        title(names[page]),
        h("p", { class: "form-error", role: "alert" }, e.message),
        button("Retry", () => render()),
      );
    else toast(e.message, true);
  }
}
async function checkBills() {
  if (!billLink) return;
  const { count, latest } = await api("restaurant/bills/pending-count");
  billLink.querySelector("span").textContent = String(count);
  banner.hidden = !count;
  banner.textContent =
    count +
    " pending bill " +
    (count === 1 ? "request" : "requests") +
    " · Open checkout";
  if (lastPending !== null && latest > lastPending) {
    toast("New bill request received.");
    playAlert("bill");
  }
  lastPending = latest;
}
async function monitorAlerts() {
  if (isPlatform) return;
  const permissions = user.permissions || [];
  const sources = [
    permissions.includes("orders")
      ? ["orders", "restaurant/orders?limit=50", "order"]
      : permissions.includes("kitchen")
        ? ["kitchen", "restaurant/kitchen", "order"]
        : null,
    permissions.includes("service") ? ["service", "restaurant/services", "service"] : null,
  ].filter(Boolean);
  for (const [key, path, sound] of sources) {
    const rows = await api(path);
    const ids = new Set(rows.map((row) => row.id));
    if (lastAlerts[key] && [...ids].some((id) => !lastAlerts[key].has(id))) {
      toast(sound === "service" ? "New service request received." : "New order received.");
      playAlert(sound);
    }
    lastAlerts[key] = ids;
  }
}
async function poll() {
  if (!user || !main || document.hidden || inFlight) return;
  inFlight = true;
  try {
    if (!isPlatform) { await checkBills(); await monitorAlerts(); }
    const editing =
      !!document.querySelector("dialog[open]") ||
      /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (
      !editing &&
      ["orders", "checkout", "service", "kitchen", "overview"].includes(current)
    )
      await render({ quiet: true });
  } catch (e) {
    if (e.status === 401) signIn();
    else toast(e.message, true);
  } finally {
    inFlight = false;
  }
}
async function start() {
  try {
    user = await api(isPlatform ? "platform/overview" : "restaurant/me");
  } catch (e) {
    if (e.status === 401) {
      signIn();
      return;
    }
    root.replaceChildren(
      title("Workspace unavailable", e.message),
      button("Retry", start),
    );
    return;
  }
  const navItems = allowed();
  if (!navItems.length) {
    root.replaceChildren(
      title("Kitchen access required"),
      link("Open restaurant workspace", "/restaurant"),
    );
    return;
  }
  const workspace = isPlatform ? "Platform console" : user.restaurant.name;
  nav = h("nav", { class: "side-nav", "aria-label": "Workspace navigation" });
  billLink = null;
  soundButton = null;
  lastPending = null;
  lastAlerts = {};
  for (const item of navItems) {
    const a = h("a", { href: "#" + item }, names[item]);
    if (item === "checkout") {
      billLink = a;
      a.append(h("span", { class: "nav-count" }, "0"));
    }
    nav.append(a);
  }
  const signout = button(
    "Sign out",
    async () => {
      await api(realm + "/logout", { method: "POST" });
      signIn();
    },
    "nav-out",
  );
  const side = h(
    "aside",
    { class: "sidebar" },
    brand(),
    h(
      "div",
      { class: "side-identity" },
      h("small", {}, isPlatform ? "Administration" : "Restaurant"),
      h("strong", {}, workspace),
    ),
    nav,
    h(
      "div",
      { class: "side-foot" },
      h("strong", {}, isPlatform ? user.user.name : user.name),
      h("small", {}, isPlatform ? "Platform Super Admin" : user.role),
      button(
        "Change password",
        () =>
          editor(
            "Change password",
            [
              field("Current password", "current", {
                type: "password",
                required: true,
                autocomplete: "current-password",
              }),
              field("New password", "replacement", {
                type: "password",
                required: true,
                minlength: 12,
                autocomplete: "new-password",
              }),
            ],
            async (data) => {
              await api(realm + "/password", { method: "POST", data });
              signIn();
              toast("Password changed. Sign in again.");
            },
            "Change password",
          ),
        "nav-out",
      ),
      signout,
    ),
  );
  main = h("main", { class: "workspace-content", id: "main-panel" });
  banner = h("a", {
    href: "#checkout",
    class: "notify",
    hidden: true,
    role: "status",
  });
  root.replaceChildren(
    h("a", { class: "skip", href: "#main-panel" }, "Skip to content"),
    h(
      "div",
      { class: "workspace" + (kitchenOnly ? " kitchen-space" : "") },
      side,
      h(
        "div",
        { class: "workspace-body" },
        h(
          "header",
          { class: "work-head" },
          h(
            "span",
            {},
            isPlatform
              ? "DineX Platform"
              : kitchenOnly
                ? "Kitchen service"
                : "Restaurant operations",
          ),
          h("strong", {}, workspace),
          !isPlatform && soundControl(),
        ),
        banner,
        main,
      ),
    ),
  );
  await render();
  if (!isPlatform) { await checkBills(); await monitorAlerts(); }
}
window.addEventListener("hashchange", () => {
  if (user) render();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) poll();
});
setInterval(poll, 5000);
start();
