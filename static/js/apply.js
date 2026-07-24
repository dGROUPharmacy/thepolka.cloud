(() => {
  const input = document.getElementById("platform-filter");
  const cards = [...document.querySelectorAll(".apply-card")];
  const count = document.getElementById("platform-count");
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const show = card.dataset.search.toLowerCase().includes(query);
      card.hidden = !show;
      if (show) visible += 1;
    });
    count.textContent = `${visible} option${visible === 1 ? "" : "s"}`;
  });
})();
