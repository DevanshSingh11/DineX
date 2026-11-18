import {
  root,
  title,
  section,
  form,
  registrationFields,
  registrationData,
  api,
  link,
  h,
} from "./ui.js";
root.replaceChildren(
  title(
    "Register a restaurant",
    "Create your restaurant workspace and its first owner account.",
  ),
  section(
    "Restaurant details",
    form(
      registrationFields(),
      async (data) => {
        const r = await api("register", {
          method: "POST",
          data: registrationData(data),
        });
        root.replaceChildren(
          title(
            r.status === "active"
              ? "Your restaurant is ready"
              : "Registration received",
          ),
          section(
            r.slug,
            h(
              "p",
              {},
              r.status === "active"
                ? "Sign in with the owner account to set up your menu and tables."
                : "Your platform administrator will review your registration. Use your restaurant slug and owner account to sign in after approval.",
            ),
            link("Restaurant sign in", "/restaurant", "btn"),
          ),
        );
      },
      "Register restaurant",
    ),
  ),
);
