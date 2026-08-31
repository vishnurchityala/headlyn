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

(function () {
  const reviewList = document.getElementById("review-list");
  const labelFilter = document.getElementById("review-label-filter");
  const sortSelect = document.getElementById("review-sort");
  const searchInput = document.getElementById("review-search");
  const reviewCount = document.getElementById("review-count");
  const emptyState = document.getElementById("review-empty");
  if (!reviewList || !labelFilter || !sortSelect || !searchInput) return;

  const rows = Array.from(reviewList.querySelectorAll(".review-row"));
  const labelOrder = ["same_story", "related", "opposite", "unrelated", "unclear"];

  function renderReview() {
    const selectedLabel = labelFilter.value;
    const search = searchInput.value.trim().toLowerCase();
    const visibleRows = rows.filter((row) => {
      const matchesLabel = selectedLabel === "all" || row.dataset.label === selectedLabel;
      const matchesSearch = !search || (row.dataset.search || "").includes(search);
      return matchesLabel && matchesSearch;
    });
    const sortValue = sortSelect.value;
    visibleRows.sort((left, right) => {
      if (sortValue !== "updated") {
        if (left.dataset.label !== right.dataset.label) {
          const leftPriority = left.dataset.label === sortValue ? 0 : 1;
          const rightPriority = right.dataset.label === sortValue ? 0 : 1;
          if (leftPriority !== rightPriority) return leftPriority - rightPriority;
          return labelOrder.indexOf(left.dataset.label) - labelOrder.indexOf(right.dataset.label);
        }
      }
      return (right.dataset.updated || "").localeCompare(left.dataset.updated || "");
    });

    visibleRows.forEach((row) => reviewList.appendChild(row));
    rows.forEach((row) => { row.hidden = !visibleRows.includes(row); });
    if (emptyState) emptyState.hidden = visibleRows.length !== 0;
    if (reviewCount) reviewCount.textContent = visibleRows.length;
  }

  [labelFilter, sortSelect].forEach((control) => control.addEventListener("change", renderReview));
  searchInput.addEventListener("input", renderReview);
  document.querySelectorAll("[data-review-label]").forEach((button) => {
    button.addEventListener("click", () => {
      labelFilter.value = button.dataset.reviewLabel;
      renderReview();
    });
  });
  renderReview();
})();
