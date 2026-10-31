htmx.onLoad((content) => {
  // Drag-to-reorder lists: each [data-sortable] is an hx-post form triggered on "end".
  content.querySelectorAll("[data-sortable]").forEach((list) => {
    new Sortable(list, {
      animation: 150,
      handle: ".handle",
      ghostClass: "drag-ghost",
      onEnd: () => htmx.trigger(list, "end"),
    });
  });

  // Material form: only show the fields that matter for the chosen pricing type.
  content.querySelectorAll("#id_pricing_type").forEach((select) => {
    const show = () => {
      document.querySelectorAll("[data-for-pricing]").forEach((row) => {
        row.hidden = !row.dataset.forPricing.split(" ").includes(select.value);
      });
    };
    select.addEventListener("change", show);
    show();
  });

  // Material form: orders at cost have no pricing to set; lessons and orders aren't silver.
  content.querySelectorAll("#id_kind").forEach((select) => {
    const show = () => {
      document.querySelectorAll("[data-hide-for-kind]").forEach((el) => {
        el.hidden = el.dataset.hideForKind.split(" ").includes(select.value);
      });
    };
    select.addEventListener("change", show);
    show();
  });

  content.querySelectorAll("[data-check-group]").forEach(syncGroupTick);
});

// Choose silver page: a category tick-box ticks or unticks every material in it.
function syncGroupTick(groupBox) {
  const boxes = [...document.querySelectorAll(`[data-group="${groupBox.dataset.checkGroup}"]`)];
  const ticked = boxes.filter((b) => b.checked).length;
  groupBox.checked = ticked === boxes.length;
  groupBox.indeterminate = ticked > 0 && ticked < boxes.length;
}

document.addEventListener("change", (event) => {
  const target = event.target;
  if (target.matches("[data-check-group]")) {
    document.querySelectorAll(`[data-group="${target.dataset.checkGroup}"]`).forEach((b) => { b.checked = target.checked; });
  } else if (target.matches("[data-group]")) {
    syncGroupTick(document.querySelector(`[data-check-group="${target.dataset.group}"]`));
  }
});

// ---------- Class mode basket ----------
(() => {
  const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
  const form = () => document.getElementById("basket-form");
  const parseQty = (text) => {
    const n = parseFloat(String(text).replace(",", "."));
    return Number.isFinite(n) && n > 0 ? n : 0;
  };
  const tidy = (n) => String(Math.round(n * 100) / 100);

  function refresh() {
    const basket = form();
    if (!basket) return;
    const lines = [...basket.querySelectorAll(".basket-line")];
    let total = 0;
    lines.forEach((line) => {
      const qty = parseQty(line.querySelector("input").value);
      const lineTotal = Math.round(qty * parseFloat(line.dataset.price) * 100 + Number.EPSILON) / 100;
      total += lineTotal;
      line.querySelector(".line-total").textContent = qty ? gbp.format(lineTotal) : "–";
    });
    basket.querySelector("[data-basket-total]").textContent = gbp.format(total);
    basket.querySelector("[data-basket-count]").textContent = `${lines.length} item${lines.length === 1 ? "" : "s"}`;
    basket.querySelector("[data-basket-empty]").hidden = lines.length > 0;
    basket.querySelector("[data-basket-submit]").disabled = !lines.some((l) => parseQty(l.querySelector("input").value));
  }

  function add(tile) {
    const basket = form();
    const { id, name, price, unit, step } = tile.dataset;
    let line = basket.querySelector(`.basket-line[data-id="${CSS.escape(id)}"]`);
    if (line) {
      const input = line.querySelector("input");
      input.value = tidy(parseQty(input.value) + parseFloat(step));
    } else {
      line = document.getElementById("basket-line").content.firstElementChild.cloneNode(true);
      Object.assign(line.dataset, { id, price, step });
      line.querySelector(".line-name").textContent = name;
      line.querySelector(".line-unit").textContent = unit;
      const input = line.querySelector("input");
      input.name = `qty_${id}`;
      input.value = "1";
      basket.querySelector("#basket-lines").append(line);
      if (step !== "1" || "amount" in tile.dataset) {
        input.focus();
        input.select();
      }
    }
    tile.classList.remove("added");
    void tile.offsetWidth;
    tile.classList.add("added");
    refresh();
  }

  document.addEventListener("click", (event) => {
    const tile = event.target.closest("[data-add]");
    if (tile && form()) return add(tile);
    const line = event.target.closest(".basket-line");
    if (!line) return;
    if (event.target.closest(".remove")) {
      line.remove();
    } else if (event.target.closest("[data-delta]")) {
      const input = line.querySelector("input");
      const next = parseQty(input.value) + Number(event.target.closest("[data-delta]").dataset.delta) * parseFloat(line.dataset.step);
      if (next <= 0) line.remove();
      else input.value = tidy(next);
    }
    refresh();
  });

  document.addEventListener("input", (event) => {
    if (event.target.closest(".basket-line")) refresh();
  });

  // Enter in the search box shouldn't submit the basket.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches("[data-search]")) event.preventDefault();
  });
})();
