(function () {
  const form = document.getElementById("annotation-form");
  const selectionList = document.getElementById("selection-list");
  const selectedCount = document.getElementById("selected-count");
  const saveButton = document.getElementById("save-button");
  const validationHint = document.getElementById("validation-hint");
  if (!form || !selectionList) return;

  const labelOptions = [
    ["same_story", "Same story"],
    ["related", "Related"],
    ["opposite", "Opposite / contradicting"],
    ["unrelated", "Unrelated"],
    ["unclear", "Unclear"],
  ];

  function selectedCards() {
    return Array.from(document.querySelectorAll(".candidate-card")).filter((card) =>
      card.classList.contains("is-selected"),
    );
  }

  function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function syncSelection() {
    const cards = selectedCards();
    selectionList.replaceChildren();
    selectedCount.textContent = cards.length;
    let missing = 0;

    cards.forEach((card) => {
      const id = card.dataset.articleId;
      const item = makeElement("div", "selection-card");
      const hiddenId = document.createElement("input");
      hiddenId.type = "hidden";
      hiddenId.name = "candidate_ids";
      hiddenId.value = id;
      item.appendChild(hiddenId);
      item.appendChild(makeElement("div", "selection-title", card.dataset.title));
      item.appendChild(makeElement("div", "selection-source", card.dataset.source));

      const select = document.createElement("select");
      select.name = `label_${id}`;
      select.className = "needs-label";
      const placeholder = new Option("Choose relationship…", "");
      select.add(placeholder);
      labelOptions.forEach(([value, label]) => select.add(new Option(label, value)));
      select.addEventListener("change", () => {
        select.classList.toggle("needs-label", !select.value);
        updateSaveState();
      });
      item.appendChild(select);

      const notes = document.createElement("textarea");
      notes.name = `notes_${id}`;
      notes.rows = 2;
      notes.placeholder = "Optional note";
      item.appendChild(notes);
      selectionList.appendChild(item);
    });

    if (!cards.length) selectionList.appendChild(makeElement("div", "empty-state compact", "Your selected pairs will appear here."));
    updateSaveState();
  }

  function updateSaveState() {
    const cards = selectedCards();
    const missing = Array.from(selectionList.querySelectorAll("select")).filter((select) => !select.value).length;
    selectedCount.textContent = cards.length;
    saveButton.disabled = cards.length === 0 || missing > 0;
    saveButton.textContent = cards.length ? `Save ${cards.length} pair${cards.length === 1 ? "" : "s"}` : "Save selected pairs";
    validationHint.hidden = missing === 0;
    validationHint.textContent = `${missing} selected pair${missing === 1 ? " needs" : "s need"} a label.`;
  }

  document.querySelectorAll(".candidate-toggle").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const selected = toggle.getAttribute("aria-pressed") === "true";
      toggle.setAttribute("aria-pressed", String(!selected));
      toggle.textContent = selected ? "Select" : "Selected";
      toggle.closest(".candidate-card")?.classList.toggle("is-selected", !selected);
      syncSelection();
    });
  });

  form.addEventListener("submit", (event) => {
    updateSaveState();
    if (saveButton.disabled) event.preventDefault();
  });
})();
