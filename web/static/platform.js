import {
  h,
  title,
  grid,
  stack,
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
  human,
  badge,
  stamp,
  registrationFields,
  registrationData,
  toast,
  empty,
} from "./ui.js";

const p = (path, opt) => api("platform/" + path, opt);
export async function platformPage(page, { refresh, go }) {
  const save = async (path, data, method = "PUT") => {
    await p(path, { method, data });
    await refresh();
    toast("Saved.");
  };
  const addRestaurant = () =>
    editor(
      "Create a restaurant",
      registrationFields(),
      (d) => save("restaurants", registrationData(d), "POST"),
      "Create restaurant",
    );
  async function details(id) {
    const [r, plans] = await Promise.all([p("restaurants/" + id), p("plans")]);
    let dlg;
    const statusChoices = [
      "active",
      "suspended",
      "deactivated",
      ...(r.status === "pending" ? ["rejected"] : []),
    ];
    dlg = modal(
      r.name,
      stack(
        kv([
          ["Slug", r.slug],
          ["Owner", r.owner_name],
          ["Email", r.owner_email],
          ["Contact", r.contact || "—"],
          ["Location", [r.city, r.country].filter(Boolean).join(", ") || "—"],
          ["Orders", r.orders],
          ["Active tables", r.active_tables],
          ["Active staff", r.active_staff],
          ["Current status", badge(r.status)],
        ]),
        section(
          "Restaurant access",
          form(
            [
              field("Set status", "status", {
                choices: statusChoices,
                value: statusChoices.includes(r.status) ? r.status : "active",
              }),
            ],
            async (d) => {
              await save("restaurants/" + id + "/state", d);
              dlg.close();
            },
            r.status === "pending" ? "Review registration" : "Update status",
          ),
        ),
        section(
          "Plan assignment",
          form(
            [
              field("Plan", "plan_id", {
                choices: plans.map((x) => [x.id, x.name]),
                value: r.plan_id,
              }),
              field("Subscription record", "subscription", {
                choices: ["unbilled", "trial", "active", "paused"],
                value: r.subscription,
              }),
            ],
            async (d) => {
              await save("restaurants/" + id + "/plan", {
                ...d,
                plan_id: Number(d.plan_id),
              });
              dlg.close();
            },
            "Assign plan",
          ),
        ),
      ),
    );
  }
  if (["overview", "restaurants"].includes(page)) {
    const d = await p("overview");
    const records =
      page === "overview"
        ? d.restaurants.filter((x) => x.status === "pending")
        : d.restaurants;
    return [
      title(page === "overview" ? "Platform overview" : "Restaurants"),
      page === "overview" &&
        metrics([
          ["Restaurants", d.counts.restaurants],
          ["Active", d.counts.active],
          ["Awaiting approval", d.counts.pending],
          ["Orders placed", d.counts.orders],
        ]),
      section(
        page === "overview"
          ? "Registrations awaiting review"
          : "Registered restaurants",
        button("Create restaurant", addRestaurant),
        table(
          ["Restaurant", "Location", "State", "Action"],
          records.map((r) => [
            r.name,
            r.city || "—",
            badge(r.status),
            button("Review", () => details(r.id), "btn light small"),
          ]),
          "No registrations here.",
        ),
      ),
    ].filter(Boolean);
  }
  if (page === "policy") {
    const d = await p("overview");
    return [
      title("Registration settings"),
      section(
        "Approval policy",
        form(
          [
            field("Require platform approval for new restaurants", "approval", {
              type: "checkbox",
              value: d.approval,
            }),
          ],
          (x) => save("policy", { approval: !!x.approval }),
        ),
      ),
    ];
  }
  if (page === "plans") {
    const plans = await p("plans");
    const create = () =>
      editor(
        "Create plan",
        [
          field("Plan name", "name", { required: true }),
          grid(
            field("Active table limit", "max_tables", {
              type: "number",
              min: 1,
              max: 1000,
              value: 100,
              required: true,
            }),
            field("Active staff limit", "max_staff", {
              type: "number",
              min: 1,
              max: 500,
              value: 50,
              required: true,
            }),
          ),
          field("Trial days", "trial_days", {
            type: "number",
            min: 0,
            max: 365,
            value: 0,
          }),
          field("Analytics", "analytics", { type: "checkbox", value: true }),
          field("Menu assistant", "assistant", {
            type: "checkbox",
            value: true,
          }),
        ],
        (d) =>
          save(
            "plans",
            {
              ...d,
              max_tables: +d.max_tables,
              max_staff: +d.max_staff,
              trial_days: +d.trial_days,
              analytics: !!d.analytics,
              assistant: !!d.assistant,
            },
            "POST",
          ),
        "Create plan",
      );
    return [
      title("Plans & limits", "Assign a plan from the restaurant detail view."),
      section(
        "Available plans",
        button("Create plan", create),
        table(
          ["Plan", "Tables", "Staff", "Trial", "Entitlements"],
          plans.map((x) => [
            x.name,
            x.max_tables,
            x.max_staff,
            x.trial_days + " days",
            [x.analytics && "Analytics", x.assistant && "Menu assistant"]
              .filter(Boolean)
              .join(", ") || "Core operations",
          ]),
        ),
      ),
    ];
  }
  if (page === "accounts") {
    const users = await p("accounts");
    return [
      title("Platform accounts"),
      section(
        "Administrators",
        button("Add administrator", () =>
          editor(
            "Add administrator",
            [
              field("Name", "name", { required: true }),
              field("Email", "email", { required: true, type: "email" }),
              field("Password", "password", {
                type: "password",
                required: true,
                minlength: 12,
              }),
            ],
            (d) => save("accounts", d, "POST"),
            "Create account",
          ),
        ),
        table(
          ["Name", "Email", "Status", "Action"],
          users.map((u) => [
            u.name,
            u.email,
            badge(u.active ? "active" : "inactive"),
            button(
              u.active ? "Deactivate" : "Activate",
              () =>
                editor(
                  "Change account access",
                  [h("p", {}, "Update access for " + u.email + "?")],
                  () => save("accounts/" + u.id, { active: !u.active }),
                  "Confirm",
                ),
              "btn light small",
            ),
          ]),
        ),
      ),
    ];
  }
  const logs = await p("audit");
  return [
    title("Platform audit log"),
    section(
      "Recent activity",
      table(
        ["Time", "Tenant", "Actor", "Action", "Record"],
        logs.map((x) => [
          stamp(x.created),
          x.tenant ?? "Platform",
          x.actor,
          human(x.action),
          x.entity,
        ]),
      ),
    ),
  ];
}
