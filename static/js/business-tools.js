(() => {
  const money = value => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number.isFinite(value) ? value : 0);
  const percent = value => `${(Number.isFinite(value) ? value : 0).toFixed(1)}%`;
  const number = (card, name) => Number(card.querySelector(`[name="${name}"]`).value) || 0;

  const calculate = {
    rate(card) {
      const total = number(card, "income") + number(card, "expenses");
      const hours = number(card, "hours") * number(card, "weeks");
      const rate = hours ? total / hours : 0;
      return [money(rate), `${money(total)} target across ${hours.toLocaleString()} billable hours.`];
    },
    roi(card) {
      const setup = number(card, "setup");
      const annualCost = setup + number(card, "monthly") * 12;
      const annualValue = number(card, "saved") * number(card, "value") * 12;
      const roi = annualCost ? ((annualValue - annualCost) / annualCost) * 100 : 0;
      const payback = annualValue > number(card, "monthly") * 12 ? setup / ((annualValue / 12) - number(card, "monthly")) : 0;
      return [percent(roi), `${money(annualValue)} annual value; ${payback > 0 ? `${payback.toFixed(1)}-month` : "no"} estimated payback.`];
    },
    ads(card) {
      const impressions = number(card, "impressions");
      const clicks = number(card, "clicks");
      const spend = number(card, "spend");
      const conversions = number(card, "conversions");
      const ctr = impressions ? (clicks / impressions) * 100 : 0;
      const cpc = clicks ? spend / clicks : 0;
      const cpa = conversions ? spend / conversions : 0;
      return [percent(ctr), `${money(cpc)} per click; ${money(cpa)} per conversion.`];
    },
    cloud(card) {
      const monthly = ["compute", "database", "storage", "other"].reduce((sum, name) => sum + number(card, name), 0);
      return [money(monthly * 12), `${money(monthly)} per month before usage spikes, support, and tax.`];
    }
  };

  document.querySelectorAll("[data-tool]").forEach(card => {
    const update = () => {
      const [result, detail] = calculate[card.dataset.tool](card);
      card.querySelector("[data-result]").textContent = result;
      card.querySelector("[data-detail]").textContent = detail;
    };
    card.addEventListener("input", update);
    update();
  });
})();
