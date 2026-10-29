(() => {
  const input = document.getElementById("company-search");
  const panel = document.getElementById("suggestions");
  if (!input || !panel) return;

  const form = input.form;
  const submit = form.querySelector("button[type='submit']");
  const status = document.getElementById("search-status");
  let active = -1;
  let timer;
  let controller;
  let requestId = 0;

  function hideSuggestions() {
    panel.hidden = true;
    panel.replaceChildren();
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function cancelSuggestions() {
    clearTimeout(timer);
    if (controller) controller.abort();
    requestId += 1;
    hideSuggestions();
  }

  function setLoading(loading) {
    submit.disabled = loading;
    submit.textContent = loading ? "Researching…" : "Research";
    form.setAttribute("aria-busy", String(loading));
    if (status) status.hidden = !loading;
  }

  function renderSuggestions(items) {
    hideSuggestions();
    if (!Array.isArray(items) || !items.length) return;
    items.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-item";
      button.id = `company-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = item.symbol ? `${item.name} (${item.symbol})` : item.name;
      button.addEventListener("click", () => {
        const query = item.symbol || item.name;
        input.value = item.name;
        cancelSuggestions();
        setLoading(true);
        window.location.assign(`/search?q=${encodeURIComponent(query)}`);
      });
      panel.appendChild(button);
    });
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  form.addEventListener("submit", () => {
    cancelSuggestions();
    setLoading(true);
  });

  input.addEventListener("input", () => {
    cancelSuggestions();
    const query = input.value.trim();
    if (!query) return;
    const id = requestId;
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const response = await fetch(`/api/suggest?q=${encodeURIComponent(query)}`, {signal: controller.signal});
        if (!response.ok) throw new Error("Suggestions unavailable");
        const items = await response.json();
        if (id === requestId && input.value.trim() === query) renderSuggestions(items);
      } catch (error) {
        if (id === requestId && error.name !== "AbortError") hideSuggestions();
      }
    }, 180);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      cancelSuggestions();
      return;
    }
    const buttons = Array.from(panel.querySelectorAll(".suggestion-item"));
    if (panel.hidden || !buttons.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      buttons[active].click();
      return;
    } else return;
    buttons.forEach((button, index) => {
      button.classList.toggle("active", index === active);
      button.setAttribute("aria-selected", String(index === active));
    });
    input.setAttribute("aria-activedescendant", buttons[active].id);
  });

  document.addEventListener("click", (event) => {
    if (!input.contains(event.target) && !panel.contains(event.target)) cancelSuggestions();
  });

  // Browsers can restore the disabled button when returning from a report.
  window.addEventListener("pageshow", () => {
    cancelSuggestions();
    setLoading(false);
  });
})();
