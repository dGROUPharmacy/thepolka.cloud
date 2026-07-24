(() => {
  const form = document.getElementById("mylm-form");
  const status = document.getElementById("mylm-status");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "Saving your pilot request...";
    const response = await fetch("/api/mylm/intake", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        email: document.getElementById("mylm-email").value,
        authored_email_count: document.getElementById("mylm-count").value,
        consent: document.getElementById("mylm-consent").checked,
      }),
    });
    const result = await response.json();
    status.textContent = response.ok ? result.message : result.error;
    if (response.ok) form.reset();
  });
})();
