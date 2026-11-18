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
  uploadField,
  currOptions,
  empty,
  toast,
  link,
} from "./ui.js";
const req = (p, opt) => api("restaurant/" + p, opt);
const roles = ["Owner", "Admin", "Manager", "Kitchen", "Staff"];
const dest = {
  Profile: "profile",
  Branding: "profile",
  Categories: "menu",
  Menu: "menu",
  Tables: "tables",
  "QR codes": "tables",
  Staff: "staff",
  "Operational settings": "profile",
};
function progress(tasks, go, rights) {
  const entries = Object.entries(tasks),
    done = entries.filter(([, x]) => x).length;
  return section(
    "Restaurant setup",
    rights.includes("profile") &&
      button("Open setup guide", () => go("onboarding"), "btn light"),
    h(
      "div",
      { class: "progress-head" },
      h("strong", {}, done + " of " + entries.length + " complete"),
      h("progress", {
        max: entries.length,
        value: done,
        "aria-label": "Onboarding progress",
      }),
    ),
    h(
      "div",
      { class: "setup-grid" },
      entries.map(([name, yes]) =>
        rights.includes(dest[name])
          ? button(
              (yes ? "✓ " : "○ ") + name,
              () => go(dest[name]),
              "setup-step",
            )
          : h("span", { class: "setup-step" }, (yes ? "✓ " : "○ ") + name),
      ),
    ),
  );
}
function groupsEditor(groups) {
  const rows = h("div", { class: "stack" });
  const cards = [];
  function addGroup(g = {}) {
    const name = field("Group name", "group_name", {
      value: g.name,
      required: true,
      placeholder: "e.g. Portion",
    });
    const min = field("Minimum selections", "group_min", {
      type: "number",
      value: g.minimum ?? 0,
      min: 0,
      max: 30,
      required: true,
    });
    const max = field("Maximum selections", "group_max", {
      type: "number",
      value: g.maximum ?? 1,
      min: 1,
      max: 30,
      required: true,
    });
    const list = h("div", { class: "stack tight" });
    const options = [];
    function addOption(o = {}) {
      const n = field("Option name", "option_name", {
        value: o.name,
        required: true,
      });
      const delta = field("Extra price", "option_price", {
        type: "number",
        step: "0.01",
        min: 0,
        value: (o.price || 0) / 100,
        required: true,
      });
      const row = h(
        "div",
        { class: "option-row" },
        n,
        delta,
        button("Remove", () => row.remove(), "btn quiet small"),
      );
      list.append(row);
      options.push(() =>
        row.isConnected
          ? {
              name: n.querySelector("input").value,
              price: asMinor(delta.querySelector("input").value),
            }
          : null,
      );
    }
    (g.options || [{}]).forEach(addOption);
    const wrap = h(
      "fieldset",
      { class: "group-card" },
      h("legend", {}, "Customization group"),
      name,
      grid(min, max),
      list,
      actions(
        button("Add option", () => addOption(), "btn light small"),
        button("Remove group", () => wrap.remove(), "btn quiet small"),
      ),
    );
    rows.append(wrap);
    cards.push(() =>
      wrap.isConnected
        ? {
            name: name.querySelector("input").value,
            minimum: +min.querySelector("input").value,
            maximum: +max.querySelector("input").value,
            options: options.map((fn) => fn()).filter(Boolean),
          }
        : null,
    );
  }
  groups.forEach(addGroup);
  return [
    stack(
      rows,
      button("Add customization group", () => addGroup(), "btn light"),
    ),
    () => cards.map((fn) => fn()).filter(Boolean),
  ];
}
function itemEditor(item, cats, save, allergenOptions) {
  if (!cats.length) {
    toast("Create a category first.", true);
    return;
  }
  const g = groupsEditor(item.groups || []);
  const checks = (label, key) =>
    h(
      "fieldset",
      { class: "group-card" },
      h("legend", {}, label),
      h(
        "div",
        { class: "ai-filter-grid" },
        allergenOptions.map((a) =>
          field(a.name, key + "_" + a.id, {
            type: "checkbox",
            value: (item[key] || []).includes(a.id),
          }),
        ),
      ),
    );
  const picked = (data, key) =>
    allergenOptions.filter((a) => data[key + "_" + a.id]).map((a) => a.id);
  editor(
    item.id ? "Edit dish" : "Add a dish",
    [
      grid(
        field("Dish name", "name", { required: true, value: item.name }),
        field("Category", "category_id", {
          choices: cats.map((c) => [c.id, c.name]),
          value: item.category_id,
        }),
      ),
      grid(
        field("Price", "price", {
          type: "number",
          step: "0.01",
          min: 0,
          value: (item.price || 0) / 100,
          required: true,
        }),
        field("Preparation time (minutes)", "minutes", {
          type: "number",
          min: 0,
          max: 600,
          value: item.minutes || 0,
        }),
      ),
      field("Description", "description", {
        type: "textarea",
        value: item.description,
      }),
      field("Ingredients", "ingredients", {
        type: "textarea",
        value: item.ingredients,
      }),
      h(
        "details",
        { class: "ai-filters" },
        h("summary", {}, "Recipe and allergen record"),
        checks("Contains, including garnishes and all options", "allergens"),
        checks("May contain or shared preparation", "may_contain"),
        field("Recipe review", "recipe_status", {
          choices: [
            ["unreviewed", "Awaiting kitchen review"],
            [
              "reviewed",
              "Kitchen checked the ingredients, options and possible traces",
            ],
            ...(item.recipe_status === "sample"
              ? [["sample", "Illustrative demo recipe"]]
              : []),
          ],
          value: item.recipe_status || "unreviewed",
        }),
      ),
      field("Dietary indicator", "dietary", {
        choices: ["unspecified", "vegetarian", "vegan", "non-vegetarian"],
        value: item.dietary,
      }),
      uploadField("Dish image", "image", item.image),
      actions(
        field("Available", "available", {
          type: "checkbox",
          value: item.available ?? true,
        }),
        field("Featured", "featured", {
          type: "checkbox",
          value: item.featured,
        }),
        field("Archive", "archived", {
          type: "checkbox",
          value: item.archived,
        }),
      ),
      g[0],
    ],
    (d) =>
      save(
        item.id ? "items/" + item.id : "items",
        {
          name: d.name,
          category_id: +d.category_id,
          price: asMinor(d.price),
          minutes: +d.minutes,
          description: d.description,
          ingredients: d.ingredients,
          allergens: picked(d, "allergens"),
          may_contain: picked(d, "may_contain"),
          recipe_status: d.recipe_status,
          dietary: d.dietary,
          image: d.image,
          available: !!d.available,
          featured: !!d.featured,
          archived: !!d.archived,
          groups: g[1](),
        },
        item.id ? "PUT" : "POST",
      ),
    item.id ? "Save dish" : "Create dish",
  );
}
function teamForm(s, me, save) {
  const choices =
    me.role === "Owner"
      ? roles
      : roles.filter((r) => !["Owner", "Admin"].includes(r));
  const role = field("Role", "role", { choices, value: s.role || "Staff" });
  const extras = h("div", { class: "stack tight" });
  function grants() {
    const value = role.querySelector("select").value;
    extras.replaceChildren(
      ...(value === "Manager"
        ? ["payment", "adjust"]
        : value === "Staff"
          ? ["payment"]
          : []
      ).map((k) =>
        field(
          k === "payment" ? "Can confirm payment receipt" : "Can adjust a bill",
          k,
          { type: "checkbox", value: (s.grants || []).includes(k) },
        ),
      ),
    );
  }
  role.querySelector("select").onchange = grants;
  grants();
  editor(
    s.id ? "Manage " + s.name : "Add team member",
    [
      !s.id &&
        grid(
          field("Name", "name", { required: true }),
          field("Email", "email", { type: "email", required: true }),
        ),
      !s.id &&
        field("Initial password", "password", {
          type: "password",
          required: true,
          minlength: 12,
        }),
      role,
      extras,
      s.id &&
        field("Account active", "active", {
          type: "checkbox",
          value: s.active,
        }),
    ],
    (d) => {
      const body = {
        role: d.role,
        grants: ["payment", "adjust"].filter((k) => d[k]),
      };
      if (s.id) body.active = !!d.active;
      else
        Object.assign(body, {
          name: d.name,
          email: d.email,
          password: d.password,
        });
      return save(
        s.id ? "staff/" + s.id : "staff",
        body,
        s.id ? "PUT" : "POST",
      );
    },
  );
}
export async function managementPage(page, { user, refresh, go }) {
  const cur = user.restaurant.currency;
  const save = async (path, data, method = "PUT") => {
    await req(path, { method, data });
    await refresh();
    toast("Saved.");
  };
  if (page === "onboarding") return guidedPage({ user, refresh, go });
  if (page === "overview") {
    const d = await req("overview"),
      c = d.counts;
    return [
      title(
        "Service overview",
        new Intl.DateTimeFormat("en", {
          dateStyle: "full",
          timeZone: d.restaurant.timezone,
        }).format(new Date()),
      ),
      metrics([
        ["Orders today", d.daily.orders],
        ["Today's paid sales", money(d.daily.paid, cur)],
        ["Active orders", c.active],
        ["Pending bill requests", c.bills],
      ]),
      grid(
        section(
          "Order activity",
          kv([
            ["All orders", c.total],
            ["New", c.new],
            ["Ready", c.ready],
            ["Completed", c.completed],
          ]),
        ),
        section(
          "Today's payments",
          kv(
            Object.entries(d.daily.methods).map(([k, v]) => [
              human(k),
              money(v, cur),
            ]),
          ),
        ),
      ),
      progress(d.onboarding, go, user.permissions),
      grid(
        section(
          "Tables",
          table(
            ["Table", "Activity", "Open bills"],
            d.tables.map((t) => [
              t.name,
              badge(t.occupied ? "occupied" : "available"),
              t.checkout_requests,
            ]),
            "Create tables to track activity.",
          ),
        ),
        section(
          "Popular dishes today",
          table(
            ["Dish", "Quantity"],
            Object.entries(d.daily.popular),
            "Placed orders will appear here.",
          ),
        ),
      ),
      section(
        "Recent activity",
        table(
          ["When", "Action", "Record"],
          d.recent.map((a) => [
            stamp(a.created, d.restaurant.timezone),
            human(a.action),
            a.entity,
          ]),
        ),
      ),
    ];
  }
  if (page === "profile") {
    const r = await req("profile");
    return [
      title("Restaurant settings"),
      progress(r.onboarding, go, user.permissions),
      section(
        "Restaurant profile",
        form(
          [
            grid(
              field("Restaurant name", "name", {
                value: r.name,
                required: true,
              }),
              field("Contact number", "contact", {
                value: r.contact,
                type: "tel",
              }),
            ),
            field("Description", "description", {
              type: "textarea",
              value: r.description,
            }),
            grid(
              ...[
                "address",
                "city",
                "region",
                "country",
                "cuisine",
                "hours",
              ].map((k) => field(human(k), k, { value: r[k] })),
            ),
            h("h3", {}, "Branding"),
            grid(
              uploadField("Logo", "logo", r.logo),
              uploadField("Cover image", "cover", r.cover),
            ),
            h("h3", {}, "Operational settings"),
            grid(
              field("Currency", "currency", {
                value: r.currency,
                choices: currOptions,
              }),
              field("Time zone", "timezone", {
                value: r.timezone,
                required: true,
              }),
              field("Order prefix", "prefix", {
                value: r.prefix,
                required: true,
              }),
              field("Tax (%)", "tax_bps", {
                type: "number",
                min: 0,
                max: 100,
                step: "0.01",
                value: r.tax_bps / 100,
              }),
              field("Service charge (%)", "charge_bps", {
                type: "number",
                min: 0,
                max: 100,
                step: "0.01",
                value: r.charge_bps / 100,
              }),
            ),
          ],
          (d) =>
            save("profile", {
              ...d,
              tax_bps: asMinor(d.tax_bps),
              charge_bps: asMinor(d.charge_bps),
            }),
        ),
      ),
    ];
  }
  if (page === "menu") {
    const m = await req("menu"),
      cats = m.categories;
    const catEditor = (c = {}) =>
      editor(
        c.id ? "Edit category" : "Add category",
        [
          field("Category name", "name", { value: c.name, required: true }),
          field("Active", "active", {
            type: "checkbox",
            value: c.active ?? true,
          }),
        ],
        (d) =>
          save(
            c.id ? "categories/" + c.id : "categories",
            { name: d.name, active: !!d.active },
            c.id ? "PUT" : "POST",
          ),
      );
    const search = field("Search dishes", "search", { type: "search" }),
      category = field("Filter category", "category", {
        choices: [["", "All categories"], ...cats.map((c) => [c.id, c.name])],
      }),
      list = h("div", {});
    function filter() {
      const q = search.querySelector("input").value.toLowerCase(),
        cid = category.querySelector("select").value;
      const matches = m.items.filter(
        (i) =>
          i.name.toLowerCase().includes(q) && (!cid || i.category_id === +cid),
      );
      list.replaceChildren(
        table(
          ["Dish", "Category", "Price", "State", "Action"],
          matches.map((i) => [
            i.name,
            cats.find((c) => c.id === i.category_id)?.name,
            money(i.price, cur),
            badge(
              i.archived
                ? "archived"
                : i.available
                  ? "available"
                  : "unavailable",
            ),
            button(
              "Edit dish",
              () => itemEditor(i, cats, save, m.allergen_options),
              "btn light small",
            ),
          ]),
          "No dishes match this view.",
        ),
      );
    }
    search.oninput = filter;
    category.onchange = filter;
    filter();
    return [
      title("Menu & categories"),
      section(
        "Dishes",
        actions(
          button("Add dish", () =>
            itemEditor({}, cats, save, m.allergen_options),
          ),
          button("Add category", () => catEditor(), "btn light"),
        ),
        grid(search, category),
        list,
      ),
      section(
        "Categories",
        table(
          ["Name", "State", "Action"],
          cats.map((c) => [
            c.name,
            badge(c.active ? "active" : "archived"),
            button("Edit", () => catEditor(c), "btn light small"),
          ]),
          "Add the first menu category.",
        ),
      ),
    ];
  }
  if (page === "tables") {
    const list = await req("tables");
    function tableEdit(t = {}) {
      editor(
        t.id ? "Manage " + t.name : "Create table",
        [
          field("Table name", "name", { required: true, value: t.name }),
          field("Active", "active", {
            type: "checkbox",
            value: t.active ?? true,
          }),
          field("Archived", "archived", {
            type: "checkbox",
            value: t.archived,
          }),
        ],
        (d) =>
          save(
            t.id ? "tables/" + t.id : "tables",
            { name: d.name, active: !!d.active, archived: !!d.archived },
            t.id ? "PUT" : "POST",
          ),
      );
    }
    async function showQR(t) {
      const data = await req("tables/" + t.id + "/qr", { method: "POST" });
      modal(
        t.name + " QR code",
        stack(
          h("img", { class: "qr", alt: "Scannable table QR", src: data.image }),
          h("p", {}, "Print this code for guests at " + t.name + "."),
          actions(
            h(
              "a",
              {
                class: "btn",
                href: data.image,
                download: "DineX-table-" + t.id + ".png",
              },
              "Download PNG",
            ),
            h(
              "a",
              {
                class: "btn light",
                href: data.url,
                target: "_blank",
                rel: "noopener noreferrer",
              },
              "Open guest menu",
            ),
          ),
        ),
      );
    }
    function credential(t, action) {
      editor(
        action === "revoke" ? "Revoke table QR" : "Generate new QR",
        [
          h(
            "p",
            {},
            "Previously printed codes for " +
              t.name +
              " will stop accepting new visits.",
          ),
        ],
        () => save("tables/" + t.id + "/credential", { action }, "POST"),
        "Confirm",
      );
    }
    return [
      title("Tables & QR"),
      section(
        "Dining room",
        button("Create table", () => tableEdit()),
        table(
          ["Table", "State", "Orders / bills", "Actions"],
          list.map((t) => [
            t.name,
            badge(
              t.archived
                ? "archived"
                : !t.active
                  ? "inactive"
                  : t.occupied
                    ? "occupied"
                    : "available",
            ),
            t.active_orders + " / " + t.checkout_requests,
            actions(
              button("Manage", () => tableEdit(t), "btn quiet small"),
              t.active &&
                t.qr_enabled &&
                button("Show QR", () => showQR(t), "btn light small"),
              t.active &&
                button(
                  "Regenerate",
                  () => credential(t, "rotate"),
                  "btn quiet small",
                ),
              t.active &&
                t.qr_enabled &&
                button(
                  "Revoke",
                  () => credential(t, "revoke"),
                  "btn quiet small",
                ),
            ),
          ]),
          "Create a table to generate its QR code.",
        ),
      ),
    ];
  }
  const staff = await req("staff");
  return [
    title("Team"),
    section(
      "Restaurant accounts",
      button("Add team member", () => teamForm({}, user, save)),
      table(
        ["Name", "Email", "Role", "Access", "Action"],
        staff.map((s) => [
          s.name,
          s.email,
          s.role,
          badge(s.active ? "active" : "inactive"),
          user.role === "Owner" || !["Owner", "Admin"].includes(s.role)
            ? button("Manage", () => teamForm(s, user, save), "btn light small")
            : "Owner managed",
        ]),
      ),
    ),
  ];
}

async function guidedPage(ctx) {
  const { user, refresh, go } = ctx;
  const r = await req("profile");
  const steps = [
    "Profile",
    "Branding",
    "Categories",
    "Menu",
    "Tables",
    "QR codes",
    "Staff",
    "Operational settings",
  ];
  const key = "dinex.setup." + user.restaurant.id;
  const first = steps.findIndex((s) => !r.onboarding[s]);
  const saved = sessionStorage.getItem(key);
  const index =
    saved === null
      ? Math.max(0, first)
      : Math.max(0, Math.min(7, Number(saved) || 0));
  const step = steps[index];
  const jump = (i) => {
    sessionStorage.setItem(key, String(i));
    return refresh();
  };
  const controls = actions(
    index > 0 && button("Previous step", () => jump(index - 1), "btn light"),
    index < 7
      ? button("Next step", () => jump(index + 1), "btn light")
      : button("Return to overview", () => go("overview"), "btn light"),
  );
  let content;
  if (["Profile", "Branding", "Operational settings"].includes(step)) {
    let inputs;
    if (step === "Branding")
      inputs = [
        uploadField("Logo", "logo", r.logo),
        uploadField("Cover image", "cover", r.cover),
      ];
    if (step === "Profile")
      inputs = [
        ...[
          "name",
          "contact",
          "address",
          "city",
          "region",
          "country",
          "cuisine",
          "hours",
        ].map((k) =>
          field(human(k), k, {
            value: r[k],
            required: ["name", "contact", "address", "city"].includes(k),
          }),
        ),
        field("Description", "description", {
          type: "textarea",
          value: r.description,
        }),
      ];
    if (step === "Operational settings")
      inputs = [
        field("Currency", "currency", {
          choices: currOptions,
          value: r.currency,
        }),
        field("Time zone", "timezone", { value: r.timezone, required: true }),
        field("Order prefix", "prefix", { value: r.prefix, required: true }),
        ...["tax_bps", "charge_bps"].map((k) =>
          field(k === "tax_bps" ? "Tax (%)" : "Service charge (%)", k, {
            type: "number",
            min: 0,
            max: 100,
            step: "0.01",
            value: r[k] / 100,
            required: true,
          }),
        ),
      ];
    content = section(
      step,
      form(
        inputs,
        async (d) => {
          const { id, slug, onboarding, ...profile } = r;
          if (step === "Operational settings") {
            d.tax_bps = asMinor(d.tax_bps);
            d.charge_bps = asMinor(d.charge_bps);
          }
          await req(
            "profile?review_settings=" + (step === "Operational settings"),
            { method: "PUT", data: { ...profile, ...d } },
          );
          await refresh();
          toast("Setup saved.");
        },
        "Save " + step.toLowerCase(),
      ),
    );
  } else if (step === "Categories") {
    const m = await req("menu");
    content = section(
      "Menu categories",
      form(
        [field("Category name", "name", { required: true })],
        async (d) => {
          await req("categories", { method: "POST", data: d });
          await refresh();
        },
        "Create category",
      ),
      table(
        ["Category", "State"],
        m.categories.map((c) => [
          c.name,
          badge(c.active ? "active" : "archived"),
        ]),
      ),
    );
  } else {
    const destination = dest[step];
    const nodes = await managementPage(destination, ctx);
    content = nodes[1];
  }
  const selector = field("Setup step", "step", {
    choices: steps.map((s, i) => [
      i,
      i + 1 + ". " + s + (r.onboarding[s] ? " · complete" : ""),
    ]),
    value: index,
  });
  selector.onchange = () =>
    jump(Number(selector.querySelector("select").value));
  return [
    title("Restaurant setup"),
    h(
      "div",
      { class: "progress-head" },
      selector,
      badge(r.onboarding[step] ? "complete" : "unfinished"),
    ),
    content,
    controls,
  ];
}
