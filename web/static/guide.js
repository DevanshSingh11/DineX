import { h, actions, button, field } from "./ui.js";

const examples = [
  "Show me vegetarian starters under ₹300",
  "What goes into paneer tikka?",
  "I’m allergic to peanuts. Show me desserts.",
];
const fileTypes = {
  m4a: "audio/m4a",
  mp4: "audio/mp4",
  wav: "audio/wav",
  mp3: "audio/mpeg",
  ogg: "audio/ogg",
  flac: "audio/flac",
  aac: "audio/aac",
  webm: "audio/webm",
};

export function createGuide({
  catalog,
  call,
  cash,
  onDish,
  onStaff,
  canOrder,
}) {
  const names = Object.fromEntries(
    catalog.allergen_options.map(({ id, name }) => [id, name]),
  );
  const format = (codes) => codes.map((id) => names[id] || id).join(", ");
  let draft = "",
    language = "en-IN",
    selected = new Set(),
    last = null,
    shown = 4;
  let activeMic = null,
    generation = 0,
    unresolvedRequest = "";
  function leave() {
    generation++;
    if (activeMic) {
      const mic = activeMic;
      activeMic = null;
      mic.abort();
    }
    window.speechSynthesis?.cancel();
  }

  function pane() {
    leave();
    const generationHere = generation;
    const live = () => generation === generationHere;
    const status = h("p", { class: "ai-status", role: "status" });
    const results = h("section", {
      class: "ai-results",
      "aria-label": "Menu matches",
    });
    const input = h("textarea", {
      name: "question",
      id: "ai-question",
      rows: 2,
      maxlength: 400,
      placeholder: "What sounds good, or what do you need to avoid?",
      value: draft,
    });
    const submit = h("button", { class: "btn", type: "submit" }, "Find dishes");
    const filterCount = h("summary", {});
    const filterPanel = h("details", { class: "ai-filters" }, filterCount);
    const checks = new Map();
    let busy = false;
    function syncFilters() {
      for (const [id, box] of checks) box.checked = selected.has(id);
      filterCount.textContent = selected.size
        ? "Allergy filters · " + format([...selected])
        : "Add allergy filters";
      if (unresolvedRequest)
        filterCount.textContent = "An ingredient needs a kitchen check";
    }
    function updateDraft(value) {
      draft = value;
      input.value = value;
      last = null;
      shown = 4;
      results.replaceChildren();
    }
    input.addEventListener("input", () => updateDraft(input.value));
    const filterGrid = h("div", { class: "ai-filter-grid" });
    for (const { id, name } of catalog.allergen_options) {
      const box = h("input", { type: "checkbox" });
      checks.set(id, box);
      box.addEventListener("change", () => {
        if (box.checked) selected.add(id);
        else selected.delete(id);
        if (!last?.answer.needs_confirmation) last = null;
        syncFilters();
        draw();
      });
      filterGrid.append(h("label", { class: "check" }, box, name));
    }
    filterPanel.append(
      filterGrid,
      button(
        "Clear filters",
        () => {
          selected.clear();
          last = null;
          unresolvedRequest = "";
          syncFilters();
          draw();
        },
        "btn quiet small",
      ),
    );
    syncFilters();

    async function find(confirmed) {
      const question =
        input.value.trim() || (selected.size ? "Show me dishes" : "");
      if (!question || busy) return;
      if (unresolvedRequest) {
        status.textContent =
          "Your earlier ingredient request still needs staff confirmation. Clear filters to start a new search.";
        draw();
        return;
      }
      busy = true;
      submit.disabled = true;
      input.readOnly = true;
      const askedWith = [...selected];
      status.textContent = "Checking the menu…";
      try {
        const answer = await call("assistant", {
          method: "POST",
          data: { question, avoid: askedWith, confirmed },
        });
        if (!live()) return;
        if (
          (input.value.trim() && input.value.trim() !== question) ||
          JSON.stringify([...selected]) !== JSON.stringify(askedWith)
        ) {
          status.textContent =
            "Your request changed. Choose Find dishes to search again.";
          return;
        }
        last = { question, answer };
        if (answer.unresolved) unresolvedRequest = question;
        shown = 4;
        selected = new Set(answer.avoid);
        syncFilters();
        status.textContent = answer.needs_confirmation
          ? "Check your allergy filters below."
          : answer.items.length +
            (answer.items.length === 1 ? " menu match." : " menu matches.");
        draw();
      } catch (error) {
        if (live()) status.textContent = error.message;
      } finally {
        busy = false;
        submit.disabled = false;
        input.readOnly = false;
      }
    }
    function card(row) {
      const recorded = row.recipe_status !== "unreviewed";
      const dish = button("View dish", () => onDish(row.id), "btn light small");
      dish.disabled = !canOrder();
      return h(
        "article",
        { class: "ai-dish" },
        h(
          "div",
          { class: "split" },
          h("h3", {}, row.name),
          h("strong", {}, cash(row.price)),
        ),
        h("p", { class: "muted" }, row.category + " · " + row.dietary),
        h("p", {}, row.ingredients || "Ingredients haven’t been recorded."),
        h(
          "small",
          {},
          recorded
            ? (row.recipe_status === "sample"
                ? "Sample recipe"
                : "Kitchen recipe") +
                " · Declared allergens: " +
                (format(row.allergens) || "none listed") +
                " · Possible traces: " +
                (format(row.may_contain) || "none recorded")
            : "Allergen record awaiting kitchen review.",
        ),
        dish,
      );
    }
    function draw() {
      results.replaceChildren();
      if (!last && unresolvedRequest) {
        results.append(
          h(
            "p",
            { class: "ai-caution" },
            "The kitchen still needs to check your earlier request.",
          ),
          button(
            "Ask the kitchen",
            () =>
              onStaff("Please check these ingredients: " + unresolvedRequest),
            "btn light small",
          ),
        );
        return;
      }
      if (!last) return;
      const { answer, question } = last;
      results.append(
        h(
          "h2",
          {},
          answer.needs_confirmation
            ? "Check your filters"
            : answer.items.length
              ? "From the menu"
              : "About your request",
        ),
        h("p", {}, answer.message),
      );
      if (answer.needs_confirmation) {
        results.append(
          h(
            "p",
            { class: "ai-selection" },
            format([...selected]) || "Choose your filters above.",
          ),
          button("Use these allergy filters", () => find(true)),
        );
      }
      if (answer.preparation_note)
        results.append(
          h("p", { class: "ai-caution" }, answer.preparation_note),
        );
      if (answer.ask_staff)
        results.append(
          button(
            "Ask the kitchen",
            () =>
              onStaff(
                "Allergy / ingredients: " +
                  (selected.size ? format([...selected]) + ". " : "") +
                  question,
              ),
            "btn light small",
          ),
        );
      if (answer.items.length) {
        results.append(
          h(
            "div",
            { class: "ai-dish-list" },
            answer.items.slice(0, shown).map(card),
          ),
        );
        if (shown < answer.items.length)
          results.append(
            button(
              "Show more (" + (answer.items.length - shown) + ")",
              () => {
                shown += 6;
                draw();
              },
              "btn light",
            ),
          );
      }
      if ("speechSynthesis" in window && window.SpeechSynthesisUtterance) {
        results.append(
          button(
            "Read answer aloud",
            () => {
              window.speechSynthesis.cancel();
              const spoken = [
                answer.message,
                answer.preparation_note,
                answer.items
                  .slice(0, 4)
                  .map((i) => i.name)
                  .join(", "),
              ]
                .filter(Boolean)
                .join(" ");
              const speech = new SpeechSynthesisUtterance(spoken);
              speech.lang = "en-IN";
              window.speechSynthesis.speak(speech);
            },
            "btn quiet small",
          ),
        );
      }
      const source =
        answer.mode === "Gemini" ? "Gemini · restaurant menu" : answer.mode;
      results.append(h("small", { class: "muted" }, source));
    }
    const voice = h("div", { class: "ai-voice" });
    const Recognizer =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    const secure = window.isSecureContext ?? location.protocol === "https:";
    if (Recognizer && secure) {
      const lang = field("Speech language", "speech_language", {
        choices: [
          ["en-IN", "English (India)"],
          ["hi-IN", "हिन्दी"],
        ],
        value: language,
      });
      lang.onchange = () => {
        language = lang.querySelector("select").value;
      };
      const speak = button(
        "Speak",
        () => {
          if (activeMic) {
            activeMic.stop();
            return;
          }
          const mic = new Recognizer();
          mic.lang = language;
          mic.interimResults = false;
          mic.continuous = false;
          let delivered = false;
          mic.onresult = (e) => {
            if (!live()) return;
            const transcript = Array.from(e.results)
              .map((r) => r[0].transcript)
              .join(" ")
              .trim();
            if (!transcript || transcript.length > 400) {
              status.textContent = "Try a shorter request or type it.";
              return;
            }
            updateDraft(transcript);
            delivered = true;
            status.textContent =
              "Check the words, especially food names, then choose Find dishes.";
            input.focus();
          };
          mic.onerror = (e) => {
            if (!live()) return;
            delivered = true;
            status.textContent =
              e.error === "not-allowed"
                ? "Microphone access was declined. Type or use keyboard dictation."
                : "Speech recognition is unavailable. Use keyboard dictation or type your request.";
          };
          mic.onend = () => {
            if (!live()) return;
            activeMic = null;
            speak.textContent = "Speak";
            speak.setAttribute("aria-pressed", "false");
            if (!delivered)
              status.textContent =
                "No words captured. Try again or type your request.";
          };
          mic.start();
          activeMic = mic;
          speak.textContent = "Stop listening";
          speak.setAttribute("aria-pressed", "true");
          status.textContent = "Listening…";
        },
        "btn light",
      );
      speak.setAttribute("aria-pressed", "false");
      voice.append(
        actions(speak, lang),
        h(
          "small",
          { class: "muted" },
          "Live dictation uses your browser’s speech service.",
        ),
      );
    } else {
      voice.append(
        h(
          "p",
          { class: "muted" },
          "To speak here, tap the microphone on your phone keyboard and dictate into the question box.",
        ),
      );
    }
    if (catalog.guide.gemini) {
      const picker = h("input", {
        type: "file",
        accept: "audio/*,.m4a,.webm",
        "aria-label": "Choose audio recording",
      });
      const capture = h("input", {
        type: "file",
        accept: "audio/*",
        capture: "user",
        hidden: true,
      });
      let clip;
      const sendClip = button(
        "Transcribe with Gemini",
        async () => {
          const file = clip;
          if (!file) return;
          if (file.size > 4 * 1024 * 1024) {
            status.textContent = "Choose a voice note smaller than 4 MB.";
            return;
          }
          status.textContent = "Transcribing your voice note…";
          try {
            const media =
              fileTypes[file.name.split(".").pop().toLowerCase()] || file.type;
            const result = await call("assistant/transcribe", {
              method: "POST",
              bytes: file,
              contentType: media,
            });
            if (live()) {
              updateDraft(result.transcript);
              input.focus();
              status.textContent =
                "Check the transcript, especially allergies, then choose Find dishes.";
            }
          } catch (error) {
            if (live()) status.textContent = error.message;
          }
        },
        "btn light small",
      );
      const row = h("div", { hidden: true }, sendClip);
      const chosen = h("small", { class: "muted" });
      function selectClip(event) {
        clip = event.target.files[0];
        chosen.textContent = clip ? clip.name : "";
        row.hidden = !clip;
      }
      picker.onchange = capture.onchange = selectClip;
      voice.append(
        h(
          "details",
          { class: "ai-clip", open: !(Recognizer && secure) },
          h("summary", {}, "Use a voice note"),
          h(
            "p",
            {},
            "Record on your phone or choose an audio file (up to 4 MB). Transcribe sends it to Google Gemini.",
          ),
          button(
            "Record a voice note",
            () => capture.click(),
            "btn light small",
          ),
          capture,
          picker,
          chosen,
          row,
        ),
      );
    }
    const form = h(
      "form",
      { class: "ai-composer" },
      h("label", { for: "ai-question" }, "Your question"),
      input,
      voice,
      filterPanel,
      catalog.guide.external &&
        h(
          "small",
          { class: "muted" },
          catalog.guide.gemini
            ? "Gemini can interpret your menu request. Only the restaurant’s menu supplies dish details."
            : "Your menu request may be sent to the restaurant’s AI provider.",
        ),
      actions(submit),
      status,
    );
    form.onsubmit = (e) => {
      e.preventDefault();
      if (!input.value.trim() && !selected.size) {
        input.focus();
        status.textContent = "Enter a question or choose an allergy filter.";
        return;
      }
      find(false);
    };
    draw();
    return h(
      "div",
      { class: "ai-page stack" },
      h(
        "header",
        { class: "section-head" },
        h("h1", {}, "DineX AI"),
        h(
          "p",
          {},
          "Find a dish at " +
            catalog.restaurant.name +
            " by name, price, ingredients or allergy.",
        ),
      ),
      form,
      h(
        "div",
        { class: "ai-examples", "aria-label": "Example questions" },
        examples.map((q) =>
          button(
            q,
            () => {
              updateDraft(q);
              input.focus();
            },
            "chip",
          ),
        ),
      ),
      results,
    );
  }
  return { pane, leave };
}
