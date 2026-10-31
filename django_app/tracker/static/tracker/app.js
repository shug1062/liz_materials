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
});
